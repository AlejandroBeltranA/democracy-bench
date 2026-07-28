"""Q2 Stage-2 v7.2 promotion gate — frozen by `paper/Q2_STAGE2_HOSTED_DESIGN.md`.

Implements the five frozen mechanisms that decide whether an open-weight candidate endpoint
may be promoted, whether a completed run may emit a headline, and how its uncertainty is
computed:

1. **Full-grid cost projection** (S-F5 / R-V7-2 / C2) — the documented-tokenizer projection
   over all 528 rendered requests with a fixed 10% safety margin. NOT `per-call cost x 13,200`.
   The 240 smoke draws are counted ONCE (they are already the first five draws of 48 of the
   528 coordinates); adding them on top is the double-count bug this module refuses to have.
2. **Deterministic endpoint promotion walk** (v7 promotion rule, R-V7-1, R-V7-5, C1) — walk
   the FROZEN fallback sequence in order and promote the FIRST endpoint satisfying
   (a) exact-envelope HTTP 200 with the frozen provider-audit proof, (b) demonstrably honored
   reasoning-off, and (c) a fitting full-grid projection. If none passes, the model is a
   capability/budget exclusion: there is NO reduced-cell and NO reduced-S substitute.
3. **Retry policy** (C3 / R-V7-5) — five attempts = one initial + four retries; exponential
   backoff base 2 s capped at 60 s; `Retry-After` honored only when the resulting wait plus
   the next attempt fit inside the 10-minute per-request window; hard parameter/data-policy
   4xx skips immediately; a 429 is transient, not a capability result; `is_byok == true` is an
   availability failure.
4. **Full-run completeness gate** (R-V7-3) — exactly 11 cells, 12 probes, 4 unique orders,
   25 attempted draws per order, no duplicate or unexpected coordinates, >= 20/25 parseable
   per order and >= 0.95 parseable overall. Any failure => incomplete model, NO headline.
5. **Nested bootstrap** (C4) — 2,000 percentile replicates, seed 0; resample the 12 probes
   with pairing preserved, then resample within each selected probe-cell-order coordinate
   exactly the observed number of valid draws; reconstruct the four order-balanced
   distributions, protective masses, and all eight frozen contrasts inside every replicate.

NETWORK: none. Every seam that would touch the network or the wall clock (`Tokenizer`,
`EndpointProbe`, `Sender`, `Sleeper`, `Clock`) is an injected callable, so the whole module is
exercised offline. Endpoint probe RESULTS arrive as injected data; this module never issues a
request and never downloads a tokenizer. The C2 serialization helpers (`load_chat_template`,
`load_vendor_encoder`, `load_pinned_tokenizer`) read ALREADY-COMMITTED local files and verify
them against the pinned SHA-256s in the endpoint snapshot; they never fetch, and an
unverifiable file is a hard error. The vendor-encoder backend imports a pinned, hash-verified
stdlib-only module by path and calls one function in it; its bytes are checked BEFORE import.

Frozen structure (cells, probes, orders, contrasts, protective mass) is INHERITED from the
frozen local/Stage-2 modules rather than restated here.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, NoReturn, Optional, Sequence

import numpy as np

from alignment import drift
from alignment.q1_channel import WILLIAMS_ORDERS_4
from alignment.q2_hosted import HOSTED_CELLS, cid_for
from alignment.q2_v7 import envelope
# The frozen outcome-blinding interlock lives in `alignment.q2_v7.interlock`; it is
# re-exported here because the promotion decision this module produces is decision (a) of
# that interlock, and because `gate_view` is the blinded report of a GATE run.
from alignment.q2_v7.interlock import (  # noqa: F401
    FundingRecord,
    HeadlineBlocked,
    InterlockState,
    PromotionRecord,
    assert_outcome_blinded,
    blinding_interlock,
    gate_view,
    interlock_state,
    record_funding,
    record_promotion,
    require_headline_permitted,
)

ROOT = Path(__file__).resolve().parents[3]
ENDPOINT_SNAPSHOT = ROOT / "out" / "q2_stage2_endpoint_snapshot" / "manifest.json"


# =======================================================================================
# Errors — every failure mode is fail-closed and loud.
# =======================================================================================

class GateError(RuntimeError):
    """Base for every v7.2 gate failure."""


class SpecViolation(GateError):
    """A caller asked for something the frozen v7.2 spec forbids."""


class IncompleteModel(GateError):
    """The full-run completeness gate failed; no headline estimand may be emitted."""


class MissingChatTemplate(GateError):
    """The frozen C2 method needs the pinned chat serialization and it is not available.

    Raised when a projection would have to fall back to the fixed-overhead heuristic — either
    because the model's pinned assets carry no exact serialization at all, or because a caller
    asked for the exact serialization of a request that carries no structured messages.

    A model may reach the exact serialization by EITHER pinned route: a published Jinja chat
    template (Qwen3.5-397B-A17B), or the vendor's own published prompt encoder pinned under
    signed amendment AMD-V72-01 (DeepSeek-V4-Pro, whose pinned revision publishes no template
    at all: `tokenizer_config.chat_template` is null and the repo carries no
    `chat_template.jinja`). Neither route present => this error.

    This is deliberately NOT recoverable by a default argument. Frozen C2 says the pinned
    tokenizer is applied to "the exact serialized system+user messages as sent"; substituting
    a per-message constant is a different method and needs a signed pre-outcome design
    amendment before any projection built from it may authorize spend.
    """


# =======================================================================================
# Frozen constants
# =======================================================================================

# --- design geometry (inherited; restated only as derived counts) ---
CELL_IDS: tuple[str, ...] = tuple(cid_for(pk, ga) for pk, ga in HOSTED_CELLS)
N_CELLS_REQUIRED = 11
N_PROBES_REQUIRED = 12
N_ORDERS_REQUIRED = len(WILLIAMS_ORDERS_4)          # 4
N_OPTIONS = len(WILLIAMS_ORDERS_4[0])               # 4 displayed options per probe
DRAWS_PER_COORDINATE = 25                           # S=100 per probe-cell == 25 x 4 orders
N_COORDINATES = N_CELLS_REQUIRED * N_PROBES_REQUIRED * N_ORDERS_REQUIRED   # 528
DRAWS_PER_MODEL = N_COORDINATES * DRAWS_PER_COORDINATE                     # 13,200

# --- smoke (counted ONCE; already inside the 13,200) ---
SMOKE_COORDINATES = 48
SMOKE_DRAWS_PER_COORDINATE = 5
SMOKE_DRAWS_PER_MODEL = SMOKE_COORDINATES * SMOKE_DRAWS_PER_COORDINATE     # 240
ADDITIONAL_DRAWS_AFTER_SMOKE = DRAWS_PER_MODEL - SMOKE_DRAWS_PER_MODEL     # 12,960

# --- C2 full-grid cost method ---
INPUT_TOKEN_SAFETY_MARGIN = 1.10        # fixed 10% margin bounding tokenizer-vs-provider drift
_MARGIN_RATIO = (11, 10)                # the same margin as an exact rational (see below)
MAX_TOKENS = 4                          # frozen envelope cap
MIN_COMPLETION_ALLOWANCE = MAX_TOKENS   # allowance is never below the configured cap
GLOBAL_STUDY_STOP = 8.50                # USD; all paid Q2 spend counts against this (R-V7-6)

# --- C3 retry policy ---
MAX_ATTEMPTS = 5                        # one initial attempt + four retries
MAX_RETRIES = MAX_ATTEMPTS - 1
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 60.0
REQUEST_WINDOW_S = 600.0                # 10-minute per-request window

# --- R-V7-3 completeness gate ---
MIN_PARSEABLE_PER_ORDER = 20            # >= 20/25 in EVERY order
MIN_PARSEABLE_OVERALL = 0.95

# --- C4 nested bootstrap ---
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 0
PERCENTILE_LOW = 2.5
PERCENTILE_HIGH = 97.5

# --- frozen panel and fallback sequences ---
# v7 "Panel and execution order (frozen)": Qwen primary, DeepSeek independent replication.
PANEL_ORDER: tuple[str, ...] = ("qwen/qwen3.5-397b-a17b", "deepseek/deepseek-v4-pro")

# v7 "Exact endpoints" (Sol AGREED). Prices are recorded, never used to reorder.
FALLBACK_SEQUENCES: Mapping[str, tuple[str, ...]] = {
    "qwen/qwen3.5-397b-a17b": ("alibaba", "digitalocean", "streamlake", "parasail/fp8"),
    "deepseek/deepseek-v4-pro": ("deepseek", "fireworks", "novita/fp8", "parasail/fp8",
                                 "streamlake/fp8"),
}
FALLBACK_SEQUENCE = FALLBACK_SEQUENCES        # singular alias; same frozen mapping

# The v7 "Removed: eight-cell fallback and S-reduction" clause, made executable.
REDUCED_DESIGNS_RETIRED = True


def reduced_design_substitute(*_args, **_kwargs) -> NoReturn:
    """There is NO reduced-cell / reduced-S substitute. v7 retired the R-H8/v6 eight-cell
    (9,600) branch, the cost-only 11-vs-8 inclusion rule, and sub-decisions S1/S2. A model
    runs the complete 11-cell, 13,200-call design or it is reported as an exclusion."""
    raise SpecViolation(
        "v7 retired the eight-cell branch and reduced-S: a model runs the complete 11-cell "
        "13,200-call design or is reported as a capability/budget exclusion"
    )


# =======================================================================================
# 1. Full-grid cost projection  (S-F5 / R-V7-2 / C2)
# =======================================================================================

Tokenizer = Callable[[str], int]
"""Injectable seam: the pinned official tokenizer as a pure `str -> int` token counter.

C2 pins `repo_id` + exact `revision` + tokenizer-file SHA-256s in the committed endpoint
snapshot. This module never downloads one; the caller supplies the callable (or builds a
`PinnedTokenizer` from the committed local files with `load_pinned_tokenizer`).
"""

Messages = Sequence[Mapping[str, Any]]

#: The pinned Qwen template file, as named in `manifest.json["tokenizers"][...]["files"]`.
CHAT_TEMPLATE_FILENAME = "chat_template.jinja"

#: Frozen C2 serialization keywords. `add_generation_prompt=True` is the "as sent" assistant
#: turn. `enable_thinking` is deliberately LEFT UNDEFINED, which is what the published
#: template does by default (`apply_chat_template` with no extra kwargs). For the pinned Qwen
#: template the alternative (`enable_thinking=False`, which emits an empty `<think></think>`
#: block) adds exactly 2 tokens per request; that difference is inside the frozen 10% margin,
#: which for a ~161-token request is ~16 tokens.
GENERATION_PROMPT = True

#: The two places a Hugging Face repo may publish a chat template, in the order C2 reads them.
_TEMPLATE_SOURCES = (CHAT_TEMPLATE_FILENAME, "tokenizer_config.chat_template")


@dataclass(frozen=True)
class ChatTemplate:
    """The pinned Jinja chat template, with its identity, applied to structured messages.

    `render` is the exact serialization frozen C2 requires: roles, turn delimiters, special
    tokens and the generation prompt, produced by the model's OWN published template rather
    than by a per-message constant. The rendering environment mirrors the reference
    implementation: an immutable sandbox with `trim_blocks`/`lstrip_blocks` enabled, the
    `loopcontrols` extension, a `tojson` filter and a `raise_exception` global.
    """
    source: str                 # "chat_template.jinja" | "tokenizer_config.chat_template"
    text: str
    sha256: str
    origin: str = ""            # the local path the template was read from (evidence only)

    @classmethod
    def from_text(cls, text: str, *, source: str, origin: str = "") -> "ChatTemplate":
        return cls(source=source, text=text,
                   sha256=hashlib.sha256(text.encode()).hexdigest(), origin=origin)

    def identity(self) -> dict:
        return {"template_source": self.source, "template_sha256": self.sha256,
                "template_origin": self.origin,
                "add_generation_prompt": GENERATION_PROMPT}

    def _compiled(self):
        cached = _TEMPLATE_CACHE.get(self.sha256)
        if cached is None:
            cached = _compile_chat_template(self.text)
            _TEMPLATE_CACHE[self.sha256] = cached
        return cached

    def render(self, messages: Messages,
               *, add_generation_prompt: bool = GENERATION_PROMPT) -> str:
        """The exact serialized request string the pinned tokenizer is applied to."""
        msgs = [dict(m) for m in messages]
        if not msgs:
            raise SpecViolation("cannot serialize an empty message list")
        return self._compiled().render(messages=msgs,
                                       add_generation_prompt=bool(add_generation_prompt))


_TEMPLATE_CACHE: dict[str, Any] = {}


def _compile_chat_template(text: str):
    """Compile the pinned template with the reference chat-template environment.

    Jinja2 is already present in the environment; it is imported lazily so that importing this
    module never depends on it, and so the failure names the missing package precisely.
    """
    try:
        import jinja2                                          # noqa: F401
        from jinja2.ext import loopcontrols
        from jinja2.sandbox import ImmutableSandboxedEnvironment
    except ImportError as exc:                                  # pragma: no cover
        raise MissingChatTemplate(
            "the pinned chat template cannot be rendered because jinja2 is unavailable "
            f"({exc}); frozen C2 has no fallback that does not require a signed amendment"
        ) from None

    def _raise_exception(message: str) -> NoReturn:
        raise SpecViolation(f"pinned chat template refused these messages: {message}")

    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True,
                                        extensions=[loopcontrols])
    env.globals["raise_exception"] = _raise_exception
    env.filters["tojson"] = lambda value, **kw: json.dumps(value, **kw)
    return env.from_string(text)


def load_chat_template(directory: Path | str, *, allow_missing: bool = False,
                       model: str = "") -> Optional[ChatTemplate]:
    """Read the pinned chat template out of a LOCAL committed tokenizer directory.

    Reads `chat_template.jinja` when present, otherwise `tokenizer_config.json`'s
    `chat_template` field. Never fetches anything. When neither exists the model has no
    published serialization at the pinned revision and frozen C2 cannot be executed for it:
    `MissingChatTemplate` is raised unless the caller explicitly asks for `allow_missing`.
    """
    directory = Path(directory)
    path = directory / CHAT_TEMPLATE_FILENAME
    if path.exists():
        return ChatTemplate.from_text(path.read_text(), source=CHAT_TEMPLATE_FILENAME,
                                      origin=str(path))
    config = directory / "tokenizer_config.json"
    if config.exists():
        text = (json.loads(config.read_text()) or {}).get("chat_template")
        if isinstance(text, str) and text.strip():
            return ChatTemplate.from_text(text, source="tokenizer_config.chat_template",
                                          origin=str(config))
    if allow_missing:
        return None
    raise MissingChatTemplate(
        f"no chat template in the pinned assets at {directory}"
        + (f" for {model!r}" if model else "")
        + f" (looked for {' and '.join(_TEMPLATE_SOURCES)}). Frozen C2 applies the pinned "
        "tokenizer to the EXACT serialized messages; without a published template that "
        "serialization cannot be reconstructed from the pinned files, so the projection "
        "requires an APPROVED PRE-OUTCOME DESIGN AMENDMENT specifying a conservative "
        "substitute method. No such amendment may be assumed here.")


# ---------------------------------------------------------------------------------------
# C2 serialization backend 2 — the vendor's OWN pinned encoder (amendment AMD-V72-01)
# ---------------------------------------------------------------------------------------
#
# `deepseek-ai/DeepSeek-V4-Pro` publishes NO Jinja chat template at the pinned revision
# `b5968e9190ef611bbf34a7229255be88a0e937c1`: `tokenizer_config.chat_template` is null and no
# `.jinja` file exists anywhere in the repo. It DOES publish its own official prompt encoder,
# `encoding_dsv4.py`, which is the code the vendor itself uses to turn structured messages
# into the exact prompt string. Signed pre-outcome amendment AMD-V72-01 adopts that module,
# pinned byte-for-byte and at frozen rendering flags, as this model's exact C2 serialization.
#
# Using the vendor's own code — rather than a hand-transcribed template — is the whole point:
# it removes transcription risk, which is what pinning exists to eliminate. The module imports
# only the standard library (`typing`, `copy`, `json`, `re`).
#
# This is NOT the fixed-overhead heuristic and must never be confused with it: it counts role
# markers, special tokens and the assistant generation prompt for real, exactly as the Jinja
# path does for Qwen.

#: The pinned DeepSeek encoder, as named in `manifest.json["tokenizers"][...]["files"]`.
VENDOR_ENCODER_FILENAME = "encoding_dsv4.py"

#: The frozen `serialization` block the snapshot must declare for a vendor-encoder model.
#: `load_pinned_tokenizer` refuses any block that does not match this exactly — the snapshot
#: is the record, and these constants are the reviewed values that record must carry.
VENDOR_ENCODER_METHOD = "vendor_encoder"
VENDOR_ENCODER_ENTRY_POINT = "encode_messages"
VENDOR_ENCODER_AMENDMENT = "AMD-V72-01"

#: Frozen rendering flags. `thinking_mode="chat"` is the reasoning-off serialization matching
#: the frozen `reasoning: {"effort": "none"}` envelope; `add_default_bos_token=True` emits the
#: BOS the served prompt carries; `drop_thinking=True` and `reasoning_effort=None` are the
#: vendor defaults and are pinned explicitly so a future default change cannot move the count.
#: The encoder always terminates the prompt with the assistant turn, which is this backend's
#: equivalent of `add_generation_prompt=True`.
VENDOR_ENCODER_FLAGS: Mapping[str, Any] = MappingProxyType({
    "thinking_mode": "chat",
    "add_default_bos_token": True,
    "drop_thinking": True,
    "reasoning_effort": None,
})

_VENDOR_MODULE_CACHE: dict[str, Any] = {}


def _load_vendor_encoder_module(path: Path, expected_sha256: str) -> Any:
    """Import the pinned encoder module BY PATH after verifying its bytes.

    The hash is checked BEFORE the file is executed, so a swapped or tampered encoder never
    runs. The module is loaded into a private, sha-suffixed module name and is deliberately NOT
    registered in `sys.modules`: nothing else in the process can import it by name, and nothing
    beyond the module's own top level (constants and function definitions over stdlib imports)
    is executed. Only `encode_messages` is ever called.
    """
    if not path.exists():
        raise SpecViolation(
            f"the pinned vendor serializer {path.name} is absent from {path.parent}; the "
            "frozen C2 serialization for this model cannot be executed")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != str(expected_sha256).lower():
        raise SpecViolation(
            f"pinned vendor serializer {path.name} hashes to {digest} != committed "
            f"{expected_sha256} — refusing to execute an unpinned serializer")
    cached = _VENDOR_MODULE_CACHE.get(digest)
    if cached is not None:
        return cached
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(f"_q2v7_vendor_encoder_{digest[:16]}", path)
    if spec is None or spec.loader is None:                      # pragma: no cover
        raise SpecViolation(f"cannot build an import spec for the pinned serializer {path}")
    module = importlib.util.module_from_spec(spec)
    # Do not drop a `__pycache__` into the pinned-asset directory: that directory is frozen
    # evidence, and importing it must leave no trace.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)                          # stdlib-only module
    finally:
        sys.dont_write_bytecode = previous
    _VENDOR_MODULE_CACHE[digest] = module
    return module


@dataclass(frozen=True)
class VendorEncoder:
    """The vendor's OWN pinned prompt encoder, applied to structured messages.

    Interface-compatible with `ChatTemplate` (`source`, `sha256`, `origin`, `identity()`,
    `render()`), so `PinnedTokenizer`, `RenderedRequest.exact_serialization` and
    `project_full_grid` treat the two exact backends identically. It is a DIFFERENT method from
    the Jinja template and says so in every artifact: `serialization_method` is
    `"pinned_vendor_encoder"`, and the amendment that approved it is carried alongside.
    """
    source: str                       # the module filename, e.g. "encoding_dsv4.py"
    sha256: str                       # SHA-256 of the module bytes, verified before import
    origin: str = ""                  # local path the module was read from (evidence only)
    entry_point: str = VENDOR_ENCODER_ENTRY_POINT
    flags_json: str = json.dumps(dict(VENDOR_ENCODER_FLAGS), sort_keys=True,
                                 separators=(",", ":"))
    amendment: str = VENDOR_ENCODER_AMENDMENT

    @property
    def flags(self) -> dict:
        """The frozen keyword arguments `entry_point` is called with."""
        return json.loads(self.flags_json)

    def identity(self) -> dict:
        return {
            "template_source": self.source,
            "template_sha256": self.sha256,
            "template_origin": self.origin,
            "add_generation_prompt": GENERATION_PROMPT,
            "serialization_backend": VENDOR_ENCODER_METHOD,
            "serializer_module": self.source,
            "serializer_sha256": self.sha256,
            "serializer_entry_point": self.entry_point,
            "serializer_flags": self.flags,
            "serialization_amendment": self.amendment,
        }

    def _entry(self) -> Callable[..., str]:
        module = _load_vendor_encoder_module(Path(self.origin), self.sha256)
        fn = getattr(module, self.entry_point, None)
        if not callable(fn):
            raise SpecViolation(
                f"the pinned serializer {self.source} publishes no callable "
                f"{self.entry_point!r}")
        return fn

    def render(self, messages: Messages,
               *, add_generation_prompt: bool = GENERATION_PROMPT) -> str:
        """The exact serialized request string the pinned tokenizer is applied to."""
        msgs = [dict(m) for m in messages]
        if not msgs:
            raise SpecViolation("cannot serialize an empty message list")
        if not add_generation_prompt:
            raise SpecViolation(
                f"the pinned vendor serializer {self.source} always terminates the prompt "
                "with the assistant turn; `add_generation_prompt=False` is not a serialization "
                "it can produce, and suppressing it is not the frozen method")
        out = self._entry()(msgs, **self.flags)
        if not isinstance(out, str) or not out:
            raise SpecViolation(
                f"the pinned serializer {self.source}.{self.entry_point} returned "
                f"{type(out).__name__}, not a non-empty prompt string")
        return out


def load_vendor_encoder(directory: Path | str, block: Mapping[str, Any], *,
                        files: Mapping[str, str], model: str = "") -> VendorEncoder:
    """Build a `VendorEncoder` from a snapshot `serialization` block, fail-closed.

    Every field of the block must match the reviewed constants above and the module's SHA-256
    must be pinned in the SAME snapshot entry's `files` map, so a serializer can only be
    swapped by editing the snapshot — which changes the snapshot digest that
    `envelope.load_snapshot` binds.
    """
    where = f" for {model!r}" if model else ""
    method = str(block.get("method", ""))
    if method != VENDOR_ENCODER_METHOD:
        raise SpecViolation(
            f"unknown pinned serialization method {method!r}{where}; the only approved "
            f"non-template method is {VENDOR_ENCODER_METHOD!r} (amendment "
            f"{VENDOR_ENCODER_AMENDMENT})")
    module_name = str(block.get("module", ""))
    if module_name != VENDOR_ENCODER_FILENAME:
        raise SpecViolation(
            f"pinned serializer module {module_name!r}{where} is not the reviewed "
            f"{VENDOR_ENCODER_FILENAME!r}")
    entry_point = str(block.get("entry_point", ""))
    if entry_point != VENDOR_ENCODER_ENTRY_POINT:
        raise SpecViolation(
            f"pinned serializer entry point {entry_point!r}{where} is not the reviewed "
            f"{VENDOR_ENCODER_ENTRY_POINT!r}")
    amendment = str(block.get("amendment", ""))
    if amendment != VENDOR_ENCODER_AMENDMENT:
        raise SpecViolation(
            f"pinned serialization{where} declares amendment {amendment!r}, not the signed "
            f"pre-outcome amendment {VENDOR_ENCODER_AMENDMENT}")
    flags = block.get("flags")
    if not isinstance(flags, Mapping) or dict(flags) != dict(VENDOR_ENCODER_FLAGS):
        raise SpecViolation(
            f"pinned serialization flags{where} are {dict(flags or {})!r}, not the frozen "
            f"{dict(VENDOR_ENCODER_FLAGS)!r} — a projection at different flags is a different "
            "method and would need its own signed amendment")
    expected = files.get(module_name)
    if not isinstance(expected, str) or not expected.strip():
        raise SpecViolation(
            f"the snapshot pins no SHA-256 for the serializer {module_name!r}{where}; an "
            "unpinned serializer may never be executed")
    path = Path(directory) / module_name
    _load_vendor_encoder_module(path, expected)     # verifies bytes, then imports
    return VendorEncoder(source=module_name, sha256=expected.lower(), origin=str(path),
                         entry_point=entry_point,
                         flags_json=json.dumps(dict(flags), sort_keys=True,
                                               separators=(",", ":")),
                         amendment=amendment)


#: The two exact C2 serialization backends. Both are duck-type compatible.
Serialization = Any     # ChatTemplate | VendorEncoder


@dataclass(frozen=True)
class PinnedTokenizer:
    """The pinned official tokenizer AS A C2 INSTRUMENT: identity + exact serialization.

    It is still a plain `Tokenizer` (`str -> int`) so every existing caller keeps working, but
    it additionally carries the repo id, revision, verified file hashes and the pinned exact
    serializer, and it can count the EXACT serialized messages rather than a bare content
    concatenation. `project_full_grid` recognises it and REQUIRES the exact path whenever a
    serializer is present — the exact method is not opt-in.

    `template` holds whichever exact backend the model's pinned assets support: a
    `ChatTemplate` (published Jinja template — Qwen) or a `VendorEncoder` (the vendor's own
    pinned encoder under amendment AMD-V72-01 — DeepSeek). The field keeps its original name so
    every existing caller and artifact key is unchanged; `has_chat_template` still means
    specifically "a Jinja chat template", while `has_exact_serialization` means "either exact
    backend is available".
    """
    model: str
    repo_id: str
    revision: str
    file_sha256: Mapping[str, str]
    count_text: Tokenizer
    template: Optional[Serialization] = None
    directory: str = ""

    # --- backward compatibility: a PinnedTokenizer IS a `Tokenizer` -------------------
    def __call__(self, text: str) -> int:
        return int(self.count_text(text))

    @property
    def has_chat_template(self) -> bool:
        """True only for a published JINJA chat template. DeepSeek publishes none."""
        return isinstance(self.template, ChatTemplate)

    @property
    def has_exact_serialization(self) -> bool:
        """True when EITHER pinned exact backend is available — the frozen-C2 dispatch."""
        return self.template is not None

    @property
    def serializer(self) -> Optional[Serialization]:
        """The exact serializer, under a backend-neutral name."""
        return self.template

    @property
    def serialization_method(self) -> str:
        """The artifact label for this tokenizer's exact backend, or the fallback label."""
        if isinstance(self.template, ChatTemplate):
            return SERIALIZATION_EXACT
        if isinstance(self.template, VendorEncoder):
            return SERIALIZATION_VENDOR_ENCODER
        return SERIALIZATION_FIXED_OVERHEAD

    @property
    def serialization_amendment(self) -> Optional[str]:
        """The signed pre-outcome amendment that approved this backend, if any."""
        return getattr(self.template, "amendment", None)

    def serialize(self, messages: Messages) -> str:
        """The exact serialized request string, or a loud refusal."""
        if self.template is None:
            raise MissingChatTemplate(
                f"{self.model!r} (repo {self.repo_id} at revision {self.revision}) publishes "
                "no chat template at the pinned revision and the committed snapshot pins no "
                "approved vendor serializer for it, so the exact serialized input frozen C2 "
                "requires cannot be reconstructed from the pinned files. A projection for this "
                "model requires an APPROVED PRE-OUTCOME DESIGN AMENDMENT naming the substitute "
                "method; pass `fixed_overhead_fallback_signed_amendment=<amendment id>` only "
                "when such an amendment exists and is signed.")
        return self.template.render(messages)

    def count_messages(self, messages: Messages) -> int:
        """Token count of the EXACT serialized system+user messages (frozen C2)."""
        return int(self.count_text(self.serialize(messages)))

    def identity(self) -> dict:
        """Everything a reviewer needs to reproduce a projected count byte for byte."""
        out: dict[str, Any] = {
            "repo_id": self.repo_id,
            "revision": self.revision,
            "files": dict(self.file_sha256),
            "directory": self.directory,
            "has_chat_template": self.has_chat_template,
            "has_exact_serialization": self.has_exact_serialization,
            "serialization_method": self.serialization_method,
        }
        out.update(self.template.identity() if self.template
                   else {"template_source": None, "template_sha256": None,
                         "template_origin": "", "add_generation_prompt": GENERATION_PROMPT})
        return out


def load_pinned_tokenizer(
    model: str,
    directory: Path | str,
    *,
    snapshot_path: Path | str = ENDPOINT_SNAPSHOT,
    spec: Optional[Mapping[str, Any]] = None,
    count_text: Optional[Tokenizer] = None,
) -> PinnedTokenizer:
    """Build a `PinnedTokenizer` from the COMMITTED local files, hash-verified against the
    pinned snapshot. A local read only — never a download, never a fallback.

    Every file the snapshot pins must be present and must hash to the pinned SHA-256; an
    unverifiable tokenizer means no projection, which means no promotion.

    The exact serializer is chosen from the pinned assets, never guessed:

    * a published Jinja `chat_template.jinja` / `tokenizer_config.chat_template` => `ChatTemplate`;
    * otherwise, if the snapshot entry carries an approved `serialization` block (amendment
      AMD-V72-01), the vendor's own pinned encoder => `VendorEncoder`, hash-verified before it
      is imported and called with the frozen flags;
    * otherwise no serializer at all. Such a tokenizer still loads, but it cannot serialize:
      the refusal happens where a projection would be built, so the error names the amendment
      requirement.

    A model may not have both. A snapshot that pins a vendor serializer for a model that also
    publishes a Jinja template is ambiguous about which bytes were priced, and is refused.
    """
    if spec is None:
        data = json.loads(Path(snapshot_path).read_text())
        spec = (data.get("tokenizers") or {}).get(model)
    if not isinstance(spec, Mapping):
        raise SpecViolation(f"the committed snapshot pins no tokenizer for {model!r}")

    directory = Path(directory)
    files = dict(spec.get("files") or {})
    if not files:
        raise SpecViolation(f"the pinned tokenizer for {model!r} lists no files to verify")
    for name, expected in files.items():
        path = directory / name
        if not path.exists():
            raise SpecViolation(
                f"pinned tokenizer file {name} is absent from {directory} (repo "
                f"{spec.get('repo_id')} at revision {spec.get('revision')})")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise SpecViolation(
                f"pinned tokenizer file {name} hashes to {digest} != committed {expected}")

    if count_text is None:
        try:
            from tokenizers import Tokenizer as HFTokenizer     # type: ignore
        except ImportError as exc:                              # pragma: no cover
            raise SpecViolation(f"the `tokenizers` package is required: {exc}") from None
        hf = HFTokenizer.from_file(str(directory / "tokenizer.json"))

        def count_text(text: str) -> int:                       # noqa: F811
            return len(hf.encode(text).ids)

    template: Optional[Serialization] = load_chat_template(directory, allow_missing=True,
                                                           model=model)
    if template is not None and template.source == CHAT_TEMPLATE_FILENAME:
        pinned_template_hash = files.get(CHAT_TEMPLATE_FILENAME)
        if pinned_template_hash and pinned_template_hash != template.sha256:
            raise SpecViolation(
                f"chat template hashes to {template.sha256} != committed "
                f"{pinned_template_hash}")

    block = spec.get("serialization")
    if block is not None:
        if not isinstance(block, Mapping):
            raise SpecViolation(
                f"the pinned 'serialization' block for {model!r} is not a mapping")
        if template is not None:
            raise SpecViolation(
                f"{model!r} publishes a chat template AND the snapshot pins a vendor "
                "serializer for it; the frozen method would be ambiguous, so this is refused")
        template = load_vendor_encoder(directory, block, files=files, model=model)

    return PinnedTokenizer(model=model, repo_id=str(spec.get("repo_id", "")),
                           revision=str(spec.get("revision", "")), file_sha256=files,
                           count_text=count_text, template=template,
                           directory=str(directory))


@dataclass(frozen=True)
class EndpointCandidate:
    """One row of the committed endpoint snapshot (C1). Prices are USD PER TOKEN, exactly as
    the snapshot returns them."""
    model: str
    tag: str
    provider_name: str
    endpoint_name: str
    quantization: str
    price_prompt_per_token: float
    price_completion_per_token: float

    def __post_init__(self) -> None:
        if self.price_prompt_per_token < 0 or self.price_completion_per_token < 0:
            raise SpecViolation(f"negative price on candidate {self.tag!r}")

    @property
    def upstream_model(self) -> str:
        """The DATED upstream checkpoint id carried in `endpoint_name` (R-V7-4).

        This — not the version-free catalog slug `model` — is the "resolved model/version
        evidence" a response must return. Empty when the snapshot row carries none, which
        fails the audit closed.
        """
        return envelope.resolved_model_evidence(self.endpoint_name, self.provider_name) or ""


@dataclass(frozen=True)
class RenderedRequest:
    """One of the 528 unique cell-probe-order request bodies, already rendered and hashed.

    `messages_json` is the STRUCTURED system+user messages exactly as sent, in wire order —
    the frozen C2 input, because the pinned chat template must be applied to roles and
    contents, not to contents alone. It is stored as canonical JSON so the dataclass stays
    frozen, hashable and byte-reproducible; read it through `.messages`.

    `payload_text` is the bare concatenation of the message CONTENTS. It is retained for
    backward compatibility and as a diagnostic (`content_only_input_tokens` in the artifact),
    but it is NOT the C2 tokenizer input: it omits roles, turn delimiters, special tokens and
    the generation prompt.
    """
    cell_id: str
    probe_id: str
    order_idx: int
    request_sha256: str
    payload_text: str
    #: Fixed-overhead FALLBACK ONLY (see `chat_template_overhead`): a per-message constant
    #: standing in for the serialization when no pinned template is available. Never used on
    #: the frozen C2 path — an exact serialization counts those tokens for real.
    template_overhead_tokens: int = 0
    #: Canonical JSON of the structured messages; "" when the caller supplied none.
    messages_json: str = ""

    @property
    def coordinate(self) -> tuple[str, str, int]:
        return (self.cell_id, self.probe_id, self.order_idx)

    @property
    def messages(self) -> tuple[dict, ...]:
        """The structured messages as sent (empty when the request carries none)."""
        if not self.messages_json:
            return ()
        return tuple(json.loads(self.messages_json))

    @property
    def is_exactly_serializable(self) -> bool:
        return bool(self.messages_json)

    def exact_serialization(self, template: "Serialization") -> str:
        """The frozen C2 tokenizer input: the pinned serializer applied to these messages.

        `template` is either a `ChatTemplate` or a `VendorEncoder`; both render the exact
        prompt string the pinned tokenizer is then applied to.
        """
        if not self.is_exactly_serializable:
            raise MissingChatTemplate(
                f"rendered request {self.request_sha256[:16]} at {self.coordinate} carries no "
                "structured messages, so the exact C2 serialization cannot be reproduced")
        return template.render(self.messages)


def canonical_request_sha256(body: Mapping) -> str:
    """SHA-256 of the canonical (sorted, separator-normalised) JSON request body — the same
    identity convention the Stage-2 runner uses, so hashes are comparable across modules."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


#: FALLBACK CONSTANTS — NOT the frozen C2 method. ###################################
#:
#: A per-message constant standing in for the chat serialization when the model publishes no
#: template at its pinned revision. It is a heuristic: it approximates role markers, turn
#: delimiters, special tokens and the generation prompt with a fixed number instead of
#: counting them. Frozen C2 (`paper/Q2_STAGE2_HOSTED_DESIGN.md`, "C2") applies the pinned
#: tokenizer to "the exact serialized system+user messages as sent", so USING THESE CONSTANTS
#: FOR A STUDY PROJECTION REQUIRES A SIGNED PRE-OUTCOME DESIGN AMENDMENT. `project_full_grid`
#: refuses them unless `fixed_overhead_fallback_signed_amendment` names one.
#:
#: Measured against the real pinned Qwen template on all 528 rendered study requests, this
#: heuristic is 18 tokens HIGHER than the exact serialization for every request (exact 161 vs
#: heuristic 179 vs bare content 147 on the first grid coordinate). Overstating cost can only
#: refuse an affordable run, never authorize an unaffordable one — but conservative is not the
#: same as preregistered, which is why the exact path is mandatory when a template exists.
CHAT_TEMPLATE_TOKENS_PER_MESSAGE = 12
CHAT_TEMPLATE_GENERATION_PROMPT_TOKENS = 8

#: Artifact labels for the three serialization methods. The first two are EXACT (frozen C2:
#: the pinned tokenizer applied to the exact serialized system+user messages as sent) and are
#: reported distinctly, because they are different pinned inputs and a reviewer must be able to
#: tell from the artifact which one priced the grid. The third is the heuristic.
SERIALIZATION_EXACT = "pinned_chat_template"
SERIALIZATION_VENDOR_ENCODER = "pinned_vendor_encoder"
SERIALIZATION_FIXED_OVERHEAD = "fixed_overhead_fallback"

#: The serialization methods that ARE frozen C2 and may therefore authorize paid execution.
FROZEN_C2_SERIALIZATIONS = (SERIALIZATION_EXACT, SERIALIZATION_VENDOR_ENCODER)


def chat_template_overhead(n_messages: int,
                           per_message: int = CHAT_TEMPLATE_TOKENS_PER_MESSAGE,
                           generation_prompt: int = CHAT_TEMPLATE_GENERATION_PROMPT_TOKENS
                           ) -> int:
    """FALLBACK ONLY: the fixed-overhead stand-in for the chat serialization. See the
    constants above — a study projection built on this needs a signed amendment."""
    return int(n_messages) * int(per_message) + int(generation_prompt)


def render_request(cell_id: str, probe_id: str, order_idx: int, body: Mapping,
                   *, template_overhead: Optional[int] = None) -> RenderedRequest:
    """Build a `RenderedRequest` from an exact request body.

    The STRUCTURED messages are carried through verbatim (`messages_json`), because the frozen
    C2 tokenizer input is the pinned chat template applied to roles AND contents. The bare
    content concatenation (`payload_text`) and the fixed-overhead constant are retained only
    for backward compatibility and for the amendment-gated fallback; neither is used when a
    pinned template is available.
    """
    messages = list(body.get("messages") or [])
    payload_text = "\n".join(str(m.get("content", "")) for m in messages)
    overhead = (chat_template_overhead(len(messages)) if template_overhead is None
                else int(template_overhead))
    messages_json = (json.dumps(messages, sort_keys=True, separators=(",", ":"))
                     if messages else "")
    return RenderedRequest(cell_id=cell_id, probe_id=probe_id, order_idx=int(order_idx),
                           request_sha256=canonical_request_sha256(body),
                           payload_text=payload_text, template_overhead_tokens=overhead,
                           messages_json=messages_json)


def completion_allowance(observed_billed_completion_tokens: int | Iterable[int] = ()) -> int:
    """C2: `completion_allowance = max(4, max billed completion tokens observed in the
    exact-envelope canary)`. The canary supplies this allowance ONLY; it never chooses between
    projection methods.

    Accepts either the observed maximum as a scalar or the full set of canary observations.
    """
    if isinstance(observed_billed_completion_tokens, (int, float)):
        observed_billed_completion_tokens = [int(observed_billed_completion_tokens)]
    observed = [int(v) for v in observed_billed_completion_tokens]
    for v in observed:
        if v < 0:
            raise SpecViolation("negative billed completion tokens in the canary observations")
    return max([MIN_COMPLETION_ALLOWANCE, *observed])


def projected_input_tokens(raw_tokens: int) -> int:
    """`ceil(1.10 x input_tokens(request))` — the frozen fixed 10% safety margin.

    Evaluated in EXACT integer arithmetic (`ceil(11n/10)`), not in binary floating point:
    `math.ceil(1.10 * 100)` is 111 on IEEE-754 because 1.10 is not representable, which would
    make the frozen projection depend on float representation rather than on the frozen
    formula. The margin numerator/denominator are derived from the frozen 1.10 constant.
    """
    if raw_tokens <= 0:
        raise SpecViolation(f"tokenizer returned a non-positive token count: {raw_tokens}")
    num, den = _MARGIN_RATIO
    return -((-num * int(raw_tokens)) // den)      # exact ceil(num*n/den)


@dataclass(frozen=True)
class ProjectionRow:
    """One of the 528 rows of the per-candidate cost artifact.

    `raw_input_tokens` is the count the frozen 10% margin is applied to. On the C2 path it is
    the token count of the EXACT serialized request (`serialization_method ==
    "pinned_chat_template"`); `content_only_input_tokens` records what a bare content
    concatenation would have given, so a reviewer can see the serialization actually happened.
    """
    request_sha256: str
    cell_id: str
    probe_id: str
    order_idx: int
    raw_input_tokens: int
    projected_input_tokens: int
    draws: int
    input_cost_for_draws: float
    serialization_method: str = SERIALIZATION_FIXED_OVERHEAD
    content_only_input_tokens: Optional[int] = None
    serialized_sha256: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "request_sha256": self.request_sha256,
            "cell_id": self.cell_id,
            "probe_id": self.probe_id,
            "order_idx": self.order_idx,
            "raw_input_tokens": self.raw_input_tokens,
            "projected_input_tokens": self.projected_input_tokens,
            "draws": self.draws,
            "input_cost_for_draws": self.input_cost_for_draws,
            "serialization_method": self.serialization_method,
            "content_only_input_tokens": self.content_only_input_tokens,
            "serialized_sha256": self.serialized_sha256,
        }


@dataclass(frozen=True)
class CostProjection:
    """The complete S-F5 full-grid projection for ONE candidate endpoint."""
    model: str
    endpoint_tag: str
    n_requests: int
    draws_per_request: int
    price_prompt_per_token: float
    price_completion_per_token: float
    rows: tuple[ProjectionRow, ...]
    projected_input_tokens_total: int
    projected_input_cost: float
    completion_allowance: int
    projected_completion_cost: float
    reconciled_prior_gate_spend: float
    retry_reserve: float
    total: float
    stop: float
    fits: bool
    # The 240 smoke draws are the first five draws of 48 of the 528 coordinates and are
    # therefore ALREADY inside `n_requests x draws_per_request`. There is deliberately no
    # smoke term in `total`: adding one is the double-count bug R-V7-2 names.
    smoke_draws_inside_grid: int = SMOKE_DRAWS_PER_MODEL
    smoke_counted_once: bool = True
    #: Which serialization produced `raw_input_tokens`. Only `SERIALIZATION_EXACT` is the
    #: frozen C2 method; anything else needs a signed pre-outcome design amendment.
    serialization_method: str = SERIALIZATION_FIXED_OVERHEAD
    #: repo id, revision, verified file hashes, template identity — everything needed to
    #: reproduce every projected count byte for byte.
    tokenizer_identity: Optional[Mapping[str, Any]] = None
    #: The amendment id supplied when the fixed-overhead fallback was used, else None.
    fixed_overhead_fallback_signed_amendment: Optional[str] = None
    #: The signed pre-outcome amendment that approved a non-template EXACT backend
    #: (`AMD-V72-01` for the pinned DeepSeek vendor encoder), else None. This is NOT a fallback
    #: approval: the method it names still counts every special token for real.
    serialization_amendment: Optional[str] = None

    @property
    def total_draws(self) -> int:
        return self.n_requests * self.draws_per_request

    @property
    def serialization_is_frozen_c2(self) -> bool:
        return self.serialization_method in FROZEN_C2_SERIALIZATIONS

    def as_artifact(self) -> dict:
        """The per-candidate artifact C2 requires: every request hash, projected tokens,
        endpoint prices, 25-draw cost, completion allowance, prior/gate spend, retry reserve,
        and final total."""
        return {
            "artifact": "Q2 Stage-2 v7.2 full-grid cost projection",
            "model": self.model,
            "endpoint_tag": self.endpoint_tag,
            "method": "documented tokenizer (C2); fixed 10% input safety margin",
            "serialization_method": self.serialization_method,
            "serialization_is_frozen_c2": self.serialization_is_frozen_c2,
            "fixed_overhead_fallback_signed_amendment":
                self.fixed_overhead_fallback_signed_amendment,
            "serialization_amendment": self.serialization_amendment,
            "tokenizer_identity": dict(self.tokenizer_identity or {}),
            "input_token_safety_margin": INPUT_TOKEN_SAFETY_MARGIN,
            "n_requests": self.n_requests,
            "draws_per_request": self.draws_per_request,
            "total_draws": self.total_draws,
            "smoke_draws_inside_grid": self.smoke_draws_inside_grid,
            "smoke_counted_once": self.smoke_counted_once,
            "endpoint_prices": {
                "price_prompt_per_token": self.price_prompt_per_token,
                "price_completion_per_token": self.price_completion_per_token,
            },
            "projected_input_tokens_total": self.projected_input_tokens_total,
            "projected_input_cost": self.projected_input_cost,
            "completion_allowance": self.completion_allowance,
            "projected_completion_cost": self.projected_completion_cost,
            "reconciled_prior_gate_spend": self.reconciled_prior_gate_spend,
            "retry_reserve": self.retry_reserve,
            "total": self.total,
            "stop": self.stop,
            "fits": self.fits,
            "rows": [r.as_dict() for r in self.rows],
        }


def project_full_grid(
    *,
    model: str,
    candidate: EndpointCandidate,
    requests: Sequence[RenderedRequest],
    tokenizer: Tokenizer,
    completion_allowance_tokens: int,
    reconciled_prior_gate_spend: float,
    retry_reserve: float,
    draws_per_request: int = DRAWS_PER_COORDINATE,
    expected_requests: int = N_COORDINATES,
    stop: float = GLOBAL_STUDY_STOP,
    fixed_overhead_fallback_signed_amendment: Optional[str] = None,
) -> CostProjection:
    """The frozen C2 full-grid projection.

        projected_input_cost = SUM over all 528 requests of
            ceil(1.10 x input_tokens(request)) x 25 x endpoint_input_price
        projected_completion_cost = 528 x 25 x completion_allowance x endpoint_output_price
        total = projected_input_cost + projected_completion_cost
                + reconciled_prior_gate_spend + retry_reserve

    Promotion requires `total <= 8.50`. The 240 smoke draws are counted ONCE: they are the
    first five draws of 48 of these 528 coordinates and are already inside the 25-draw term.

    **`input_tokens(request)` is the EXACT serialization** (frozen C2: "the exact serialized
    system+user messages as sent"). When `tokenizer` is a `PinnedTokenizer` carrying the
    model's pinned exact serializer, that serializer is applied to the structured messages —
    including roles, special tokens and the generation prompt — and the resulting token IDs
    are counted. This is NOT optional: a pinned tokenizer WITH a serializer always takes this
    path, and every request must carry its structured messages. Either pinned backend counts:
    the published Jinja template (`pinned_chat_template`, Qwen) or the vendor's own pinned
    encoder under amendment AMD-V72-01 (`pinned_vendor_encoder`, DeepSeek-V4-Pro, whose pinned
    revision publishes no template at all). The artifact records which one was used.

    A `PinnedTokenizer` with NEITHER backend raises `MissingChatTemplate` unless
    `fixed_overhead_fallback_signed_amendment` names an approved pre-outcome design amendment;
    that argument is deliberately verbose and has no usable default, because a projection built
    on the fixed-overhead heuristic is a different method from the preregistered one and must
    never be produced by accident.

    A bare `Callable[[str], int]` (the injected offline test seam) still works and still uses
    the fixed-overhead fallback, but the resulting projection is labelled
    `serialization_method="fixed_overhead_fallback"` in every row and in the artifact, and
    `serialization_is_frozen_c2` is False. `require_frozen_c2_serialization` turns that label
    into a hard refusal wherever a projection is about to authorize spend.
    """
    if candidate.model != model:
        raise SpecViolation(
            f"candidate {candidate.tag!r} belongs to {candidate.model!r}, not {model!r}")
    if len(requests) != expected_requests:
        raise SpecViolation(
            f"full-grid projection needs exactly {expected_requests} rendered requests, "
            f"got {len(requests)} — a partial grid is never projected")
    if draws_per_request != DRAWS_PER_COORDINATE:
        raise SpecViolation("draws per coordinate is frozen at 25 (S=100 across four orders)")
    if completion_allowance_tokens < MIN_COMPLETION_ALLOWANCE:
        raise SpecViolation(
            f"completion allowance {completion_allowance_tokens} is below the frozen "
            f"{MIN_COMPLETION_ALLOWANCE}-token cap")
    if reconciled_prior_gate_spend < 0 or retry_reserve < 0:
        raise SpecViolation("prior/gate spend and retry reserve must both be non-negative")

    amendment = fixed_overhead_fallback_signed_amendment
    if amendment is not None and not str(amendment).strip():
        raise SpecViolation(
            "fixed_overhead_fallback_signed_amendment must NAME the signed pre-outcome design "
            "amendment; an empty string is not an approval")

    pinned = tokenizer if isinstance(tokenizer, PinnedTokenizer) else None
    if pinned is not None and pinned.has_exact_serialization:
        method = pinned.serialization_method
        if amendment is not None:
            raise SpecViolation(
                f"{pinned.model!r} carries a pinned exact serializer "
                f"({pinned.serializer.source}), so frozen C2 is executable exactly; the "
                "fixed-overhead fallback is not available and no amendment applies")
    elif pinned is not None:
        # A pinned tokenizer with NO exact serializer: the frozen method cannot be run.
        if amendment is None:
            pinned.serialize([{"role": "user", "content": ""}])   # raises MissingChatTemplate
            raise MissingChatTemplate("unreachable")              # pragma: no cover
        method = SERIALIZATION_FIXED_OVERHEAD
    else:
        # An injected `str -> int` seam carries no identity and no template. It cannot be the
        # frozen method, so the projection it produces is labelled as the fallback.
        method = SERIALIZATION_FIXED_OVERHEAD

    seen_hashes: set[str] = set()
    seen_coords: set[tuple[str, str, int]] = set()
    rows: list[ProjectionRow] = []
    in_price = candidate.price_prompt_per_token
    out_price = candidate.price_completion_per_token

    for req in requests:
        if req.request_sha256 in seen_hashes:
            raise SpecViolation(f"duplicate request hash in the grid: {req.request_sha256}")
        if req.coordinate in seen_coords:
            raise SpecViolation(f"duplicate coordinate in the grid: {req.coordinate}")
        seen_hashes.add(req.request_sha256)
        seen_coords.add(req.coordinate)
        content_only: Optional[int] = None
        serialized_sha: Optional[str] = None
        if method in FROZEN_C2_SERIALIZATIONS:
            assert pinned is not None and pinned.template is not None
            if not req.is_exactly_serializable:
                raise MissingChatTemplate(
                    f"request {req.request_sha256[:16]} at {req.coordinate} carries no "
                    "structured messages; frozen C2 tokenizes the exact serialized "
                    "system+user messages, which cannot be reconstructed from a bare content "
                    "concatenation")
            serialized = req.exact_serialization(pinned.template)
            raw = int(pinned(serialized))
            serialized_sha = hashlib.sha256(serialized.encode()).hexdigest()
            content_only = int(pinned(req.payload_text))
        else:
            # FALLBACK (amendment-gated for a pinned tokenizer): a bare content concatenation
            # plus a per-message constant. Not the frozen C2 serialization.
            content_only = int(tokenizer(req.payload_text))
            raw = content_only + int(req.template_overhead_tokens)
        projected = projected_input_tokens(raw)
        rows.append(ProjectionRow(
            request_sha256=req.request_sha256,
            cell_id=req.cell_id,
            probe_id=req.probe_id,
            order_idx=req.order_idx,
            raw_input_tokens=raw,
            projected_input_tokens=projected,
            draws=draws_per_request,
            input_cost_for_draws=projected * draws_per_request * in_price,
            serialization_method=method,
            content_only_input_tokens=content_only,
            serialized_sha256=serialized_sha,
        ))

    projected_tokens_total = sum(r.projected_input_tokens for r in rows)
    projected_input_cost = sum(r.input_cost_for_draws for r in rows)
    projected_completion_cost = (
        len(rows) * draws_per_request * completion_allowance_tokens * out_price)
    total = (projected_input_cost + projected_completion_cost
             + reconciled_prior_gate_spend + retry_reserve)

    return CostProjection(
        model=model,
        endpoint_tag=candidate.tag,
        n_requests=len(rows),
        draws_per_request=draws_per_request,
        price_prompt_per_token=in_price,
        price_completion_per_token=out_price,
        rows=tuple(rows),
        projected_input_tokens_total=projected_tokens_total,
        projected_input_cost=projected_input_cost,
        completion_allowance=int(completion_allowance_tokens),
        projected_completion_cost=projected_completion_cost,
        reconciled_prior_gate_spend=float(reconciled_prior_gate_spend),
        retry_reserve=float(retry_reserve),
        total=total,
        stop=float(stop),
        fits=bool(total <= stop),
        serialization_method=method,
        tokenizer_identity=(pinned.identity() if pinned is not None else None),
        fixed_overhead_fallback_signed_amendment=amendment,
        serialization_amendment=(pinned.serialization_amendment
                                 if pinned is not None and method in FROZEN_C2_SERIALIZATIONS
                                 else None),
    )


def require_frozen_c2_serialization(projection: CostProjection) -> None:
    """Fail closed unless the projection used the frozen C2 serialization.

    Frozen C2 applies the pinned tokenizer to the exact serialized system+user messages. Both
    pinned EXACT backends satisfy it — the published Jinja template and, under signed
    pre-outcome amendment AMD-V72-01, the vendor's own pinned encoder — because both count
    roles, special tokens and the generation prompt for real.

    A projection built from the fixed-overhead heuristic is a DIFFERENT method and may not
    authorize spend on its own; it needs a signed pre-outcome design amendment, whose id this
    check reports when one was supplied. Naming an amendment does NOT convert the heuristic
    into frozen C2: this function still refuses it.
    """
    if projection.serialization_is_frozen_c2:
        return
    amendment = projection.fixed_overhead_fallback_signed_amendment
    raise MissingChatTemplate(
        f"the projection for {projection.model!r} @ {projection.endpoint_tag!r} used "
        f"{projection.serialization_method!r}, not the frozen C2 pinned chat serialization"
        + (f" (declared amendment: {amendment!r})" if amendment else
           "; no signed pre-outcome design amendment was supplied")
        + " — it may not authorize paid execution")


def write_projection_artifact(path: Path | str, projection: CostProjection) -> str:
    """Write the per-candidate cost artifact atomically and return its SHA-256. Refuses to
    overwrite: a projection that decided a promotion is immutable evidence."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"projection artifact {path} exists — refusing to overwrite")
    body = json.dumps(projection.as_artifact(), sort_keys=True, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body)
    os.replace(tmp, path)
    return hashlib.sha256(body.encode()).hexdigest()


def load_endpoint_snapshot(path: Path | str = ENDPOINT_SNAPSHOT) -> dict[str, EndpointCandidate]:
    """Read the committed endpoint snapshot (C1) from disk — a local file read, never a fetch.
    Keys are `(model, tag)` pairs flattened to `f"{model}::{tag}"`."""
    data = json.loads(Path(path).read_text())
    out: dict[str, EndpointCandidate] = {}
    for c in data.get("candidates", []):
        cand = EndpointCandidate(
            model=c["model"], tag=c["tag"], provider_name=c["provider_name"],
            endpoint_name=c["endpoint_name"], quantization=c["quantization"],
            price_prompt_per_token=float(c["price_prompt_per_token"]),
            price_completion_per_token=float(c["price_completion_per_token"]),
        )
        out[f"{cand.model}::{cand.tag}"] = cand
    return out


# =======================================================================================
# 3. Retry policy  (C3 / R-V7-5) — defined before the walk, which consumes it.
# =======================================================================================

Sleeper = Callable[[float], None]
Clock = Callable[[], float]

# Hard parameter / data-policy 4xx: skip IMMEDIATELY, no retries (frozen classification).
# 408 (timeout) and 429 (rate limit) are transient, not capability results.
_TRANSIENT_STATUSES = frozenset({408, 429})


def classify_status(status: int) -> str:
    """'success' | 'transient' | 'hard' — the frozen v7.2 classification.

    A 429 is TRANSIENT, never a capability result (R-V7-5). Hard parameter/data-policy 4xx
    (400/401/403/404/422/...) skip immediately with no retries.
    """
    if 200 <= status < 300:
        return "success"
    if status in _TRANSIENT_STATUSES or 500 <= status < 600:
        return "transient"
    if 400 <= status < 500:
        return "hard"
    raise SpecViolation(f"unclassifiable HTTP status {status}")


def backoff_seconds(retry_index: int) -> float:
    """Exponential backoff, base 2 s, cap 60 s. `retry_index` is 1-based (first retry == 1),
    so the frozen ladder is 2, 4, 8, 16 s across the four retries."""
    if retry_index < 1:
        raise SpecViolation("retry index is 1-based")
    return min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** (retry_index - 1)))


@dataclass(frozen=True)
class AttemptOutcome:
    """The injected result of ONE wire attempt. `is_byok` mirrors
    `openrouter_metadata.is_byok`; True is an availability failure regardless of status."""
    status: int
    retry_after_s: Optional[float] = None
    is_byok: bool = False
    payload: Optional[Mapping] = None


@dataclass(frozen=True)
class RetryResult:
    """The outcome of the frozen retry policy for one request."""
    terminal_reason: str          # success | hard_4xx | byok | attempts_exhausted | window_exhausted
    attempts_made: int
    sleeps: tuple[float, ...]
    elapsed_s: float
    outcome: Optional[AttemptOutcome]

    @property
    def succeeded(self) -> bool:
        return self.terminal_reason == "success"

    @property
    def retries_made(self) -> int:
        return max(0, self.attempts_made - 1)


Sender = Callable[[], AttemptOutcome]


def execute_with_retries(
    send: Sender,
    *,
    sleep: Sleeper,
    clock: Clock,
    max_attempts: int = MAX_ATTEMPTS,
    window_s: float = REQUEST_WINDOW_S,
    attempt_allowance_s: Optional[float] = None,
) -> RetryResult:
    """The frozen C3 policy: **five attempts = one initial attempt + four retries.**

    - Backoff is exponential, base 2 s, capped at 60 s.
    - `Retry-After` is honored only when it is longer than the backoff AND the resulting wait
      plus the next attempt fit inside the 10-minute per-request window. Otherwise the policy
      is declared exhausted IMMEDIATELY: no sleeping past the window, no further request, and
      the deterministic walk advances.
    - A hard parameter/data-policy 4xx skips immediately with no retries.
    - A 429 is transient and IS retried.
    - `is_byok == true` is an availability failure (BYOK spend would escape the returned-cost
      ledger and make the $8.50 stop incomplete); it is never retried.

    `attempt_allowance_s` is the room reserved for the next attempt inside the window. It
    defaults to the longest attempt duration observed so far on this request (measured from
    the injected clock), so no magic constant is introduced.
    """
    if max_attempts < 1:
        raise SpecViolation("max_attempts must be at least 1")
    start = clock()
    sleeps: list[float] = []
    longest_attempt = 0.0
    outcome: Optional[AttemptOutcome] = None

    for attempt in range(1, max_attempts + 1):
        t0 = clock()
        outcome = send()
        t1 = clock()
        longest_attempt = max(longest_attempt, t1 - t0)

        if outcome.is_byok:
            return RetryResult("byok", attempt, tuple(sleeps), clock() - start, outcome)

        kind = classify_status(outcome.status)
        if kind == "success":
            return RetryResult("success", attempt, tuple(sleeps), clock() - start, outcome)
        if kind == "hard":
            return RetryResult("hard_4xx", attempt, tuple(sleeps), clock() - start, outcome)

        # transient
        if attempt == max_attempts:
            return RetryResult("attempts_exhausted", attempt, tuple(sleeps),
                               clock() - start, outcome)

        wait = backoff_seconds(attempt)
        if outcome.retry_after_s is not None:
            wait = max(wait, float(outcome.retry_after_s))

        allowance = longest_attempt if attempt_allowance_s is None else float(attempt_allowance_s)
        elapsed = clock() - start
        if elapsed + wait + allowance > window_s:
            # C3: declare the policy exhausted immediately — never sleep past the window.
            return RetryResult("window_exhausted", attempt, tuple(sleeps), elapsed, outcome)

        sleeps.append(wait)
        sleep(wait)

    raise SpecViolation("unreachable: retry loop fell through")  # pragma: no cover


# =======================================================================================
# 2. Deterministic endpoint promotion walk  (frozen; non-discretionary)
# =======================================================================================

@dataclass(frozen=True)
class EndpointProbeResult:
    """Injected DATA describing one endpoint's exact-envelope reasoning-off/cost probe.

    Nothing in this module produces one; the operator's probe harness does, and this module
    only judges it. Fields mirror the C1 frozen provider-audit proof and the R-V7-1 exact
    reasoning-off rule.
    """
    tag: str
    http_status: int
    # C1 provider-audit proof
    requested_provider_only: tuple[str, ...] = ()
    n_candidates_available: int = 0
    selected_provider_name: Optional[str] = None
    requested_model: Optional[str] = None
    returned_model_evidence: Optional[str] = None
    strategy: Optional[str] = None
    attempt: Optional[int] = None
    fallback_occurred: bool = False
    is_byok: bool = True
    # R-V7-1 reasoning-off proof
    reasoning_tokens: Optional[int] = None
    has_reasoning_payload: bool = True
    usage_fields_present: bool = False
    parsed_leading_digit: Optional[int] = None
    billed_completion_tokens: Optional[int] = None
    # retry bookkeeping (C3), when the probe went through `execute_with_retries`
    retry: Optional[RetryResult] = None


#: `envelope.verify_provider_audit` failure code -> this module's historical field label, so
#: delegating does not change the vocabulary operators and tests already read.
_AUDIT_CODE_LABEL: Mapping[str, str] = {
    "missing_openrouter_metadata": "returned_model_evidence",
    "requested_model_mismatch": "requested_model",
    "response_model_mismatch": "requested_model",
    "returned_model_mismatch": "returned_model_evidence",
    "display_name_mismatch": "selected_provider_name",
    "missing_available_candidates": "n_candidates_available",
    "available_candidates_not_one": "n_candidates_available",
    "sole_candidate_not_selected": "n_candidates_available",
    "selected_candidate_count": "n_candidates_available",
    "strategy_not_direct": "strategy",
    "attempt_not_one": "attempt",
    "is_byok_not_false": "is_byok",
    "fallback_occurred": "fallback occurred under allow_fallbacks:false",
}


def _snapshot_binding(candidate: EndpointCandidate) -> envelope.Snapshot:
    """Re-express one gate candidate as the single-row `Snapshot` the C1 proof reads.

    The proof is defined over the committed snapshot's `(model, tag)` -> display-name and
    dated-upstream-model mapping; this adapter supplies exactly that mapping for the one
    candidate under audit and nothing else.
    """
    row = envelope.SnapshotCandidate(
        model=candidate.model,
        tag=candidate.tag,
        provider_name=candidate.provider_name,
        endpoint_name=candidate.endpoint_name,
        upstream_model=candidate.upstream_model,
        quantization=candidate.quantization,
        params_all_declared=True,
        supported_parameters={},
        price_prompt_per_token=Decimal(str(candidate.price_prompt_per_token)),
        price_completion_per_token=Decimal(str(candidate.price_completion_per_token)),
    )
    return envelope.Snapshot(
        path=str(ENDPOINT_SNAPSHOT), sha256=envelope.SNAPSHOT_SHA256,
        artifact="gate probe binding", fetched_utc="", sources=(),
        raw_file_sha256={}, tokenizers={}, candidates={(row.model, row.tag): row},
    )


def _probe_as_response(result: EndpointProbeResult) -> dict[str, Any]:
    """Re-express an injected probe result in the wire shape the C1 proof judges.

    The probe harness hands this module a flattened summary; `verify_provider_audit` reads
    `openrouter_metadata`. Rebuilding that shape (rather than restating the rules) is what
    makes the gate and the envelope audit ONE rule with one verdict.
    """
    available: list[dict[str, Any]] = []
    n_available = int(result.n_candidates_available or 0)
    for i in range(max(n_available, 0)):
        available.append({
            "provider": result.selected_provider_name if i == 0 else f"other-{i}",
            "model": result.returned_model_evidence if i == 0 else None,
            "selected": i == 0,
        })
    return {
        "openrouter_metadata": {
            "requested": result.requested_model,
            "strategy": result.strategy,
            "attempt": result.attempt,
            "is_byok": result.is_byok,
            "fallback": bool(result.fallback_occurred),
            "endpoints": {"available": available},
        },
    }


def audit_envelope(result: EndpointProbeResult, candidate: EndpointCandidate) -> tuple[str, ...]:
    """Criterion (a): HTTP 200 to the exact frozen envelope with `require_parameters:true`,
    resolving to exactly the declared slug with no fallback, under the C1 proof.

    The C1 proof itself is NOT restated here: it is delegated to
    `envelope.verify_provider_audit`, the single implementation of the frozen rule. Only the
    two facts that proof cannot see — the HTTP status and the `provider.only` field of the
    REQUEST — are judged locally. In particular the returned model/version evidence is
    accepted only when it resolves to the candidate's DATED upstream checkpoint id (R-V7-4);
    the version-free catalog slug is no longer accepted, because a provider serving a
    different dated checkpoint could return it.
    """
    failures: list[str] = []
    if result.http_status != 200:
        failures.append(f"http_status={result.http_status} (not 200)")
    if tuple(result.requested_provider_only) != (candidate.tag,):
        failures.append(
            f"provider.only={list(result.requested_provider_only)} != [{candidate.tag!r}]")
    audit = envelope.verify_provider_audit(
        _probe_as_response(result), candidate.model, candidate.tag,
        _snapshot_binding(candidate))
    for code in audit.failures:
        label = _AUDIT_CODE_LABEL.get(code.split(":", 1)[0], code)
        failures.append(code if label == code else f"{label}: {code}")
    return tuple(failures)


def audit_reasoning_off(result: EndpointProbeResult) -> tuple[str, ...]:
    """Criterion (b): reasoning-off demonstrably honored — reported reasoning tokens exactly 0,
    no reasoning payload, required usage fields present, and a parseable leading digit in
    [1,4] produced within `max_tokens=4`."""
    failures: list[str] = []
    if result.reasoning_tokens != 0:
        failures.append(f"reasoning_tokens={result.reasoning_tokens!r} != 0")
    if result.has_reasoning_payload:
        failures.append("response carries a reasoning payload")
    if not result.usage_fields_present:
        failures.append("required usage fields absent")
    if result.parsed_leading_digit is None or not (1 <= int(result.parsed_leading_digit) <= 4):
        failures.append(f"parsed_leading_digit={result.parsed_leading_digit!r} not in [1,4]")
    if result.billed_completion_tokens is not None and result.billed_completion_tokens > MAX_TOKENS:
        failures.append(
            f"billed_completion_tokens={result.billed_completion_tokens} exceeds "
            f"max_tokens={MAX_TOKENS}")
    return tuple(failures)


@dataclass(frozen=True)
class WalkAttempt:
    """One rung of the deterministic walk, in sequence position order."""
    position: int
    tag: str
    passed: bool
    envelope_failures: tuple[str, ...]
    reasoning_failures: tuple[str, ...]
    projection: Optional[CostProjection]
    cost_failure: Optional[str]

    @property
    def failures(self) -> tuple[str, ...]:
        out = list(self.envelope_failures) + list(self.reasoning_failures)
        if self.cost_failure:
            out.append(self.cost_failure)
        return tuple(out)


@dataclass(frozen=True)
class PromotionDecision:
    """The frozen, non-discretionary promotion outcome for ONE model."""
    model: str
    sequence: tuple[str, ...]
    attempts: tuple[WalkAttempt, ...]
    promoted_tag: Optional[str]
    promoted_projection: Optional[CostProjection]
    excluded: bool
    exclusion_reason: Optional[str]
    # There is no reduced-cell / reduced-S substitute (v7 "Removed" clause).
    substitute: None = None

    @property
    def probed_tags(self) -> tuple[str, ...]:
        return tuple(a.tag for a in self.attempts)

    def as_record(self) -> dict:
        return {
            "model": self.model,
            "sequence": list(self.sequence),
            "promoted_tag": self.promoted_tag,
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
            "substitute": self.substitute,
            "reduced_designs_retired": REDUCED_DESIGNS_RETIRED,
            "attempts": [
                {"position": a.position, "tag": a.tag, "passed": a.passed,
                 "failures": list(a.failures),
                 "projected_total": (a.projection.total if a.projection else None)}
                for a in self.attempts
            ],
        }


EndpointProbe = Callable[[str], EndpointProbeResult]
Projector = Callable[[EndpointCandidate], CostProjection]


def frozen_sequence(model: str) -> tuple[str, ...]:
    """The model's FROZEN fallback sequence. Unknown models are refused: the panel is frozen
    at Qwen (primary) then DeepSeek (independent replication), and no model is substituted."""
    try:
        return FALLBACK_SEQUENCES[model]
    except KeyError:
        raise SpecViolation(
            f"{model!r} is not in the frozen v7 panel {sorted(FALLBACK_SEQUENCES)}") from None


def promotion_walk(
    *,
    model: str,
    probe: EndpointProbe,
    project: Projector,
    candidates: Mapping[str, EndpointCandidate],
    sequence: Optional[Sequence[str]] = None,
) -> PromotionDecision:
    """Walk the model's FROZEN fallback sequence IN ORDER and promote the FIRST endpoint that
    simultaneously satisfies (a) envelope + provider audit, (b) reasoning-off honored, and
    (c) a full-grid projection fitting the $8.50 global stop.

    The walk is strictly in-order and short-circuiting: an endpoint is probed only after every
    earlier endpoint has failed, and the first passing endpoint is promoted before any later
    endpoint is probed at all. Nothing about a result can reorder the sequence, and prices are
    recorded but never used to reorder (v7.2 C1).

    If no endpoint passes, the model is a **capability/budget exclusion**. There is no
    reduced-cell and no reduced-S substitute.
    """
    frozen = frozen_sequence(model)
    if sequence is not None and tuple(sequence) != frozen:
        raise SpecViolation(
            f"the fallback sequence for {model!r} is frozen as {frozen}; "
            f"{tuple(sequence)} was supplied")

    attempts: list[WalkAttempt] = []
    for position, tag in enumerate(frozen, start=1):
        key = f"{model}::{tag}"
        candidate = candidates.get(key)
        if candidate is None:
            raise SpecViolation(f"candidate {key!r} is absent from the committed snapshot")

        result = probe(tag)
        if result.tag != tag:
            raise SpecViolation(
                f"probe for {tag!r} returned a result for {result.tag!r} — walk integrity lost")

        env = audit_envelope(result, candidate)
        rea = audit_reasoning_off(result)
        projection: Optional[CostProjection] = None
        cost_failure: Optional[str] = None
        if not env and not rea:
            projection = project(candidate)
            if projection.endpoint_tag != tag:
                raise SpecViolation(
                    f"projection for {tag!r} carries tag {projection.endpoint_tag!r}")
            if not projection.fits:
                cost_failure = (f"full-grid projection ${projection.total:.4f} exceeds the "
                                f"${projection.stop:.2f} global stop")

        passed = not env and not rea and cost_failure is None
        attempts.append(WalkAttempt(position=position, tag=tag, passed=passed,
                                    envelope_failures=env, reasoning_failures=rea,
                                    projection=projection, cost_failure=cost_failure))
        if passed:
            # Promote the FIRST passing endpoint; no later endpoint is probed at all.
            return PromotionDecision(model=model, sequence=frozen, attempts=tuple(attempts),
                                     promoted_tag=tag, promoted_projection=projection,
                                     excluded=False, exclusion_reason=None)

    reason = "; ".join(f"{a.tag}: {', '.join(a.failures)}" for a in attempts)
    return PromotionDecision(
        model=model, sequence=frozen, attempts=tuple(attempts), promoted_tag=None,
        promoted_projection=None, excluded=True,
        exclusion_reason=("capability/budget exclusion — no endpoint in the frozen sequence "
                          f"passed (a)+(b)+(c): {reason}"))


# =======================================================================================
# 4. Full-run completeness gate  (R-V7-3)
# =======================================================================================

@dataclass(frozen=True)
class SamplingDraw:
    """One attempted sampling draw. `choice` is the DISPLAY position (0-based) the anchored
    leading-option parser recovered, or None when the reply did not parse (fail-closed —
    unparseable replies are never guessed or clamped)."""
    cell_id: str
    probe_id: str
    order_idx: int
    draw_index: int
    choice: Optional[int]

    def __post_init__(self) -> None:
        # Fail closed on an out-of-range display position. Without this, Python's negative
        # indexing silently attributes a draw to the WRONG option in `_canonical_counts`
        # (order[-1] is a valid lookup), corrupting protective mass with no error, and a
        # too-large index crashes far from its cause. S-F4 forbids guessing or clamping,
        # so an out-of-range choice is rejected outright rather than repaired.
        c = self.choice
        if c is None:
            return
        if isinstance(c, bool) or not isinstance(c, int):
            raise SpecViolation(
                f"choice must be an int display position or None, got {c!r}")
        if not (0 <= c < N_OPTIONS):
            raise SpecViolation(
                f"choice {c} is outside the 0-based display range [0,{N_OPTIONS}); "
                "an unparseable or out-of-range reply must be recorded as None")

    @property
    def coordinate(self) -> tuple[str, str, int]:
        return (self.cell_id, self.probe_id, self.order_idx)


@dataclass(frozen=True)
class CompletenessReport:
    complete: bool
    failures: tuple[str, ...]
    n_draws: int
    n_coordinates: int
    overall_parse_rate: float
    valid_counts: Mapping[tuple[str, str, int], int]

    def as_record(self) -> dict:
        return {
            "complete": self.complete,
            "failures": list(self.failures),
            "n_draws": self.n_draws,
            "n_coordinates": self.n_coordinates,
            "overall_parse_rate": self.overall_parse_rate,
            "valid_counts": {f"{c}|{p}|{o}": n for (c, p, o), n in
                             sorted(self.valid_counts.items())},
        }


def completeness_gate(
    draws: Sequence[SamplingDraw],
    *,
    expected_probe_ids: Sequence[str],
    expected_cell_ids: Sequence[str] = CELL_IDS,
    draws_per_coordinate: int = DRAWS_PER_COORDINATE,
) -> CompletenessReport:
    """R-V7-3: a headline requires EXACTLY 11 cells, 12 probes, four unique orders and 25
    attempted draws per order, with duplicate and unexpected coordinates rejected, >= 20/25
    parseable in EVERY order, and >= 0.95 parseable overall.

    Returns a report; it never raises on a data failure (the failure is the finding). Use
    `require_complete` to fail closed before emitting anything.
    """
    expected_cells = tuple(expected_cell_ids)
    expected_probes = tuple(expected_probe_ids)
    failures: list[str] = []
    if len(set(expected_cells)) != N_CELLS_REQUIRED:
        raise SpecViolation(f"expected cell set must have {N_CELLS_REQUIRED} unique ids")
    if len(set(expected_probes)) != N_PROBES_REQUIRED:
        raise SpecViolation(f"expected probe set must have {N_PROBES_REQUIRED} unique ids")

    expected_coords = {(c, p, o)
                       for c in expected_cells for p in expected_probes
                       for o in range(N_ORDERS_REQUIRED)}

    attempted: dict[tuple[str, str, int], set[int]] = {}
    valid: dict[tuple[str, str, int], int] = {}
    n_valid_total = 0
    unexpected: set[tuple[str, str, int]] = set()
    duplicates: set[tuple[str, str, int, int]] = set()
    out_of_range: set[tuple[str, str, int, int]] = set()

    for d in draws:
        coord = d.coordinate
        if coord not in expected_coords:
            unexpected.add(coord)
            continue
        slot = attempted.setdefault(coord, set())
        if d.draw_index in slot:
            duplicates.add((*coord, d.draw_index))
            continue
        slot.add(d.draw_index)
        # Defence in depth: `SamplingDraw.__post_init__` rejects an out-of-range choice at
        # construction, but a draw rehydrated from JSON (or built via object.__setattr__ on
        # this frozen dataclass) bypasses that. Report it as a completeness FAILURE rather
        # than letting a negative index silently mis-attribute the draw downstream.
        if d.choice is not None and not (0 <= int(d.choice) < N_OPTIONS):
            out_of_range.add((*coord, d.draw_index))
            continue
        if d.choice is not None:
            valid[coord] = valid.get(coord, 0) + 1
            n_valid_total += 1
    for coord in expected_coords:
        valid.setdefault(coord, 0)

    observed_cells = {c for (c, _p, _o) in attempted}
    observed_probes = {p for (_c, p, _o) in attempted}
    observed_orders = {o for (_c, _p, o) in attempted}

    if observed_cells != set(expected_cells):
        failures.append(
            f"cells: expected {len(expected_cells)} exactly, observed {len(observed_cells)} "
            f"(missing {sorted(set(expected_cells) - observed_cells)})")
    if observed_probes != set(expected_probes):
        failures.append(
            f"probes: expected {len(expected_probes)} exactly, observed "
            f"{len(observed_probes)} (missing {sorted(set(expected_probes) - observed_probes)})")
    if observed_orders != set(range(N_ORDERS_REQUIRED)):
        failures.append(
            f"orders: expected {N_ORDERS_REQUIRED} unique, observed {sorted(observed_orders)}")
    if unexpected:
        failures.append(f"unexpected coordinates: {sorted(unexpected)[:5]} "
                        f"({len(unexpected)} total)")
    if duplicates:
        failures.append(f"duplicate draw indices: {sorted(duplicates)[:5]} "
                        f"({len(duplicates)} total)")
    if out_of_range:
        failures.append(f"choice outside [0,{N_OPTIONS}): {sorted(out_of_range)[:5]} "
                        f"({len(out_of_range)} total)")

    missing_coords = sorted(expected_coords - set(attempted))
    if missing_coords:
        failures.append(f"missing coordinates: {missing_coords[:5]} "
                        f"({len(missing_coords)} total)")
    wrong_attempts = sorted(c for c, s in attempted.items() if len(s) != draws_per_coordinate)
    if wrong_attempts:
        failures.append(
            f"coordinates without exactly {draws_per_coordinate} attempted draws: "
            f"{wrong_attempts[:5]} ({len(wrong_attempts)} total)")

    thin = sorted(c for c in expected_coords if valid[c] < MIN_PARSEABLE_PER_ORDER)
    if thin:
        failures.append(
            f"coordinates below {MIN_PARSEABLE_PER_ORDER}/{draws_per_coordinate} parseable: "
            f"{[(c, valid[c]) for c in thin[:5]]} ({len(thin)} total)")

    n_attempted = sum(len(s) for s in attempted.values())
    rate = (n_valid_total / n_attempted) if n_attempted else 0.0
    if rate < MIN_PARSEABLE_OVERALL:
        failures.append(f"overall parse rate {rate:.4f} < {MIN_PARSEABLE_OVERALL}")

    return CompletenessReport(
        complete=not failures, failures=tuple(failures), n_draws=n_attempted,
        n_coordinates=len(attempted), overall_parse_rate=rate, valid_counts=valid)


def require_complete(report: CompletenessReport) -> None:
    """Fail closed: an incomplete model is reported and emits NO headline estimand."""
    if not report.complete:
        raise IncompleteModel(
            "full-run completeness gate failed; no headline estimand is emitted: "
            + "; ".join(report.failures))


# =======================================================================================
# 5. Nested bootstrap  (C4)
# =======================================================================================

CONTRASTS: tuple[tuple[str, tuple[str, str], tuple[str, str]], ...] = (
    ("data_effect", ("data_only", "no_guard"), ("baseline", "no_guard")),
    ("instruction_effect", ("instruction_only", "no_guard"), ("baseline", "no_guard")),
    ("placebo_effect", ("placebo", "no_guard"), ("baseline", "no_guard")),
    ("data_placement", ("data_only", "user_after"), ("data_only", "user_before")),
    ("combined_placement", ("combined", "user_after"), ("combined", "user_before")),
    ("data_system_recovery", ("data_only", "system_guard"), ("data_only", "no_guard")),
    ("combined_system_recovery", ("combined", "system_guard"), ("combined", "no_guard")),
)
# The eighth contrast is the channel contrast: data effect minus instruction effect.
CONTRAST_NAMES: tuple[str, ...] = tuple(
    [n for n, _a, _b in CONTRASTS[:2]] + ["channel_contrast"]
    + [n for n, _a, _b in CONTRASTS[2:]])


def _protective_mass_rows(dist: np.ndarray, floor_dir: int) -> np.ndarray:
    """Vectorised twin of `drift.protective_mass` over a trailing option axis."""
    n = dist.shape[-1]
    half = dist[..., -(n // 2):] if floor_dir > 0 else dist[..., :(n + 1) // 2]
    return half.sum(axis=-1)


def _canonical_counts(choices: Sequence[int], order_idx: int, n_options: int) -> np.ndarray:
    """Remap DISPLAY positions to canonical options through the Williams order."""
    order = list(WILLIAMS_ORDERS_4[order_idx])
    counts = np.zeros(n_options, dtype=float)
    for disp in choices:
        d = int(disp)
        # Never rely on Python negative indexing here: order[-1] is a silent mis-attribution.
        if not (0 <= d < len(order)):
            raise SpecViolation(
                f"display position {d} outside [0,{len(order)}) for order {order_idx}; "
                "out-of-range choices must be rejected upstream, never wrapped")
        counts[order[d]] += 1.0
    return counts


@dataclass(frozen=True)
class NestedBootstrapResult:
    contrasts: Mapping[str, Mapping[str, object]]
    valid_counts: Mapping[tuple[str, str, int], int]
    replicates: int
    seed: int
    probe_ids: tuple[str, ...]
    percentiles: tuple[float, float] = (PERCENTILE_LOW, PERCENTILE_HIGH)

    def as_record(self) -> dict:
        return {
            "replicates": self.replicates,
            "seed": self.seed,
            "percentiles": list(self.percentiles),
            "probe_ids": list(self.probe_ids),
            "inference_conditional_on": "parseable responses only",
            "contrasts": {k: dict(v) for k, v in self.contrasts.items()},
            "valid_draw_counts": {f"{c}|{p}|{o}": n
                                  for (c, p, o), n in sorted(self.valid_counts.items())},
        }


def nested_bootstrap(
    draws: Sequence[SamplingDraw],
    items: Mapping[str, Mapping],
    *,
    completeness: CompletenessReport,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
    expected_cell_ids: Sequence[str] = CELL_IDS,
) -> NestedBootstrapResult:
    """The frozen C4 nested percentile bootstrap: 2,000 replicates, seed 0.

    Each replicate (i) resamples the 12 probes WITH PAIRING PRESERVED — one probe index vector
    shared by every cell and order, so within-probe differences stay paired — and (ii) within
    each selected probe-cell-order coordinate resamples WITH REPLACEMENT exactly the observed
    number of valid draws from that coordinate. The four order-balanced distributions,
    protective masses, and all eight frozen contrasts are reconstructed inside every replicate.

    A coordinate that fails the R-V7-3 completeness rule never reaches this algorithm:
    `completeness` must be a passing report.

    Implementation note (deliberate, conservative): the inner resample is generated once per
    (replicate, probe). A probe drawn twice in the same replicate therefore contributes the
    same inner resample twice, so probe-level duplication is not compounded by extra
    independent finite-draw noise. This can only widen intervals, never narrow them.
    """
    require_complete(completeness)
    if replicates < 1:
        raise SpecViolation("replicates must be positive")

    cells = tuple(expected_cell_ids)
    probes = tuple(sorted({d.probe_id for d in draws}))
    if len(probes) != N_PROBES_REQUIRED:
        raise SpecViolation(f"nested bootstrap needs exactly {N_PROBES_REQUIRED} probes")

    # Valid display choices per coordinate.
    by_coord: dict[tuple[str, str, int], list[int]] = {}
    for d in draws:
        if d.choice is None:
            continue
        by_coord.setdefault(d.coordinate, []).append(int(d.choice))

    rng = np.random.default_rng(seed)
    B = int(replicates)

    # pm_boot[cell][:, probe_index] and pm_obs[cell][probe_index]
    pm_boot: dict[str, np.ndarray] = {}
    pm_obs: dict[str, np.ndarray] = {}
    valid_counts: dict[tuple[str, str, int], int] = {}

    for cell in cells:
        boot = np.zeros((B, len(probes)), dtype=float)
        obs = np.zeros(len(probes), dtype=float)
        for pi, probe in enumerate(probes):
            item = items[probe]
            n_options = len(item["scale"]["labels"])
            floor_dir = int(item["floor_dir"])
            acc_boot = np.zeros((B, n_options), dtype=float)
            acc_obs = np.zeros(n_options, dtype=float)
            for order_idx in range(N_ORDERS_REQUIRED):
                coord = (cell, probe, order_idx)
                choices = by_coord.get(coord)
                if not choices:
                    raise SpecViolation(
                        f"coordinate {coord} has no valid draws — it must never reach the "
                        f"nested bootstrap")
                valid_counts[coord] = len(choices)
                counts = _canonical_counts(choices, order_idx, n_options)
                p = counts / counts.sum()
                p = p / p.sum()                     # guard float drift for np.multinomial
                # inner level: resample exactly `len(choices)` draws with replacement
                resampled = rng.multinomial(len(choices), p, size=B).astype(float)
                acc_boot += resampled / resampled.sum(axis=1, keepdims=True)
                acc_obs += p
            dist_boot = acc_boot / acc_boot.sum(axis=1, keepdims=True)
            dist_obs = acc_obs / acc_obs.sum()
            boot[:, pi] = _protective_mass_rows(dist_boot, floor_dir)
            obs[pi] = float(drift.protective_mass(dist_obs, floor_dir))
        pm_boot[cell] = boot
        pm_obs[cell] = obs

    # outer level: resample the 12 probes, pairing preserved (one index vector per replicate)
    probe_idx = rng.integers(0, len(probes), size=(B, len(probes)))
    rows = np.arange(B)[:, None]

    def gathered(cell: str) -> np.ndarray:
        return pm_boot[cell][rows, probe_idx]

    def paired(a: tuple[str, str], b: tuple[str, str]) -> tuple[np.ndarray, float]:
        ca, cb = cid_for(*a), cid_for(*b)
        boot = (gathered(ca) - gathered(cb)).mean(axis=1)
        return boot, float((pm_obs[ca] - pm_obs[cb]).mean())

    boots: dict[str, np.ndarray] = {}
    means: dict[str, float] = {}
    for name, a, b in CONTRASTS:
        boots[name], means[name] = paired(a, b)
    boots["channel_contrast"] = boots["data_effect"] - boots["instruction_effect"]
    means["channel_contrast"] = means["data_effect"] - means["instruction_effect"]

    contrasts = {
        name: {
            "mean": means[name],
            "ci": [float(np.percentile(boots[name], PERCENTILE_LOW)),
                   float(np.percentile(boots[name], PERCENTILE_HIGH))],
            "n_probes": len(probes),
        }
        for name in CONTRAST_NAMES
    }
    if len(contrasts) != 8:
        raise SpecViolation(f"expected 8 frozen contrasts, built {len(contrasts)}")

    return NestedBootstrapResult(contrasts=contrasts, valid_counts=valid_counts,
                                 replicates=B, seed=seed, probe_ids=probes)


def headline_estimands(
    draws: Sequence[SamplingDraw],
    items: Mapping[str, Mapping],
    *,
    expected_probe_ids: Sequence[str],
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> NestedBootstrapResult:
    """Gate then estimate: run the R-V7-3 completeness gate and, only if it passes, the C4
    nested bootstrap. An incomplete model raises `IncompleteModel` and emits nothing."""
    report = completeness_gate(draws, expected_probe_ids=expected_probe_ids)
    require_complete(report)
    return nested_bootstrap(draws, items, completeness=report,
                            replicates=replicates, seed=seed)
