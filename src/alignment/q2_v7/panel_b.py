"""Panel B — the labelled frontier-model extension of the Stage-2 v7 harness (AMD-PB-01).

Panel B is a SEPARATE, labelled panel run on the same frozen instrument as the v7 panel. It
changes no v7 constant and no v7 behaviour: every v7 value stays exactly where it is, and
Panel B is selected explicitly (``panel_b.activate()``, or ``Q2_PANEL=B`` in the environment)
before any run. With the environment variable unset, nothing in this module executes.

The panel is ``("z-ai/glm-5.2", "openai/gpt-5.6-sol")``, frozen by the operator's decision of
2026-09-22 together with the four departures from v7 that the signed pre-outcome amendment
**AMD-PB-01** authorizes, and nothing else:

1. **Sampling parameters omitted for a closed model.** `openai/gpt-5.6-sol`'s promoted
   endpoint declares NEITHER ``temperature`` NOR ``top_p`` in its supported-parameter set.
   Under ``require_parameters: true`` a declared-but-absent parameter is a refusal, so the
   frozen envelope must OMIT both keys rather than send them as nulls; the provider's own
   default sampling then applies and is recorded as such. This is a wire-format concession,
   not a design change: the envelope is otherwise byte-identical to v7's.

2. **Public-encoding projection for a closed model.** `openai/gpt-5.6-sol` publishes no
   tokenizer and no chat template, so the frozen C2 pinned-serialization projection is not
   executable for it at all. Its input-token counter instead counts message CONTENT with
   OpenAI's published ``o200k_base`` encoding (tiktoken), and the model's own persisted walk
   probe is used to CHECK that the provider's real request framing is no larger than the fixed
   overhead the gate adds on top. `gate.project_full_grid` labels the resulting projection
   ``fixed_overhead_fallback`` and adds the frozen per-message template overhead on top of the
   content count, so the projection stays conservative in the budget's direction.
   ``gate.require_frozen_c2_serialization`` still refuses that projection unless AMD-PB-01 is
   named, which is the whole point of the amendment: the fallback is auditable, not silent.
   `z-ai/glm-5.2` publishes a real tokenizer and chat template and takes the ORDINARY frozen
   C2 path — the amendment applies to the Sol row only.

3. **A Panel-B-only $11.00 hard stop.** Panel B's spend is accounted separately from the v7
   panel's $8.50 stop, and prior spend is reconciled ONLY from Panel B's own canary raw
   directory. No v7 record is re-reconciled into Panel B, and no Panel B record counts against
   the v7 stop; the two ledgers do not touch.

4. **GLM on a third-party fp8 endpoint.** `z-ai/glm-5.2` is promoted on ``novita/fp8``, the
   cheapest fp8 endpoint declaring all four parameters, by budget decision (Z.AI's own
   endpoint is also fp8, at twice the price). GLM-5.3 was the first choice and is recorded as
   a capability exclusion: it is reasoning-mandatory on every endpoint, so the frozen
   reasoning-off proof cannot hold for it (see the decision memo). The quantization is recorded in the
   snapshot and travels with every projection and every estimand, so the reader can see it.

Each model has a SINGLE endpoint, so there is no promotion walk to fall back through: a failed
capability probe ends that model's run rather than selecting a substitute.

Usage::

    Q2_PANEL=B .venv/bin/python -m alignment.q2_v7.canary --i-have-authorized-paid-spend
    Q2_PANEL=B .venv/bin/python -m alignment.q2_v7.study_run walk --model z-ai/glm-5.2 ...

or, in process::

    from alignment.q2_v7 import panel_b
    panel_b.activate()
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from alignment.q2_v7 import canary as C
from alignment.q2_v7 import envelope as E
from alignment.q2_v7 import gate as G
from alignment.q2_v7 import ledger as L
from alignment.q2_v7 import study_run as SR

ROOT = Path(__file__).resolve().parents[3]

#: The signed pre-outcome design amendment this whole module operates under.
AMENDMENT = "AMD-PB-01"
#: The second signed pre-outcome amendment (2026-09-22): variant **B2** re-runs the Sol row
#: in its OWN run directory after the frozen walk excluded it for five billed completion
#: tokens on a one-digit reply with reasoning tokens exactly 0. B2 (a) tolerates up to
#: `FRAMING_TOKEN_TOLERANCE_B2` billed tokens above `max_tokens` on the `openai` tag when
#: reasoning is demonstrably off, (b) carries a Sol-only roster, and (c) runs under a
#: Panel-B2 stop of $8.40: the $11.00 Panel B ceiling Alex set minus GLM-5.2's bound
#: projection of $2.5785 leaves $8.4215, floored to $8.40, so B + B2 stays inside $11.00.
#: Nothing else differs from variant B.
AMENDMENT_2 = "AMD-PB-02"
FRAMING_TOKEN_TOLERANCE_B2: Mapping[str, int] = {"openai": 8}
PANEL_B2_ORDER: tuple[str, ...] = ("openai/gpt-5.6-sol",)
HARD_STOP_B2_USD = 8.40
STUDY_RUN_DIR_B2 = None   # set below, after ROOT-relative dirs are defined
#: B2-ONLY non-reconciled component: the one paid Sol walk probe of the cost-excluded first
#: B2 attempt. It is a B2 debit, not a Panel B one — adding it to the shared list after
#: GLM-5.2's funding record was written moved B's reconciled prior spend and made the frozen
#: authorization refuse GLM's resume, so it lives in the B2 overrides alone.
PRIOR_DIAGNOSTIC_COMPONENTS_B2_EXTRA = None   # set below, after `L` components are defined

#: The frozen Panel B roster, in order: GLM (primary) then Sol (independent replication).
PANEL_B_ORDER: tuple[str, ...] = ("z-ai/glm-5.2", "openai/gpt-5.6-sol")

#: One endpoint per model — there is no walk fallback on Panel B.
FALLBACK_SEQUENCES_B: Mapping[str, tuple[str, ...]] = {
    "z-ai/glm-5.2": ("novita/fp8",),
    "openai/gpt-5.6-sol": ("openai",),
}

#: Panel-B-only spend ceiling (USD). Disjoint from the v7 panel's $8.50 stop.
HARD_STOP_B_USD = 11.00

#: The committed Panel B endpoint snapshot, SHA-256-bound exactly as v7's is.
SNAPSHOT_PATH_B = "out/q2_stage2_panel_b_snapshot/manifest.json"
SNAPSHOT_SHA256_B = "fc781eb7a41a32b5caae33fc6bbf12ee2c3e671be183faea90620d4f0d632e2f"

#: Run directories. Panel B never writes into a v7 run directory.
CANARY_RUN_DIR_B = ROOT / "out" / "q2_stage2_panel_b_canary"
STUDY_RUN_DIR_B = ROOT / "out" / "q2_stage2_panel_b_run"
STUDY_RUN_DIR_B2 = ROOT / "out" / "q2_stage2_panel_b2_run"

#: AMD-PB-01 (1): the closed endpoint declares no sampling parameters, so the envelope omits
#: them rather than sending nulls under `require_parameters: true`.
PROVIDER_DEFAULT_SAMPLING_MODELS_B: frozenset[str] = frozenset({"openai/gpt-5.6-sol"})

#: AMD-PB-01 (2): the closed model publishes no tokenizer, so its counter is calibrated from
#: its own persisted walk probe's provider-reported usage.
USAGE_CALIBRATED_MODELS_B: frozenset[str] = frozenset({"openai/gpt-5.6-sol"})

#: The amendment named on the resulting non-C2 projection, and the set that authorizes it.
FALLBACK_AMENDMENT_BY_MODEL_B: Mapping[str, str] = {"openai/gpt-5.6-sol": AMENDMENT}
APPROVED_FALLBACK_AMENDMENTS_B: frozenset[str] = frozenset({AMENDMENT})

#: AMD-PB-01 (3): prior Panel B spend is reconciled from Panel B's OWN canary records only.
PRIOR_RECORD_DIRS_B: tuple[Path, ...] = (CANARY_RUN_DIR_B / "raw",)
#: Panel B has no pre-v7-era ad-hoc diagnostic artifacts to debit at an upper bound.
#: Two synthetic diagnostic probes (GLM-5.3 first-party: 400, no cost; GLM-5.2 first-party:
#: $0.0000506) sent outside the runner to establish the GLM-5.3 exclusion. Debited as a
#: conservative upper bound, labelled non-reconciled, exactly as R-V7-6 prescribes.
PRIOR_DIAGNOSTIC_COMPONENTS_B: tuple[Any, ...] = (
    L.NonReconciledComponent(
        label="panel_b_glm_reasoning_off_diagnostics",
        upper_bound_usd=0.0002,
        reason="two ad-hoc curl probes in out/q2_stage2_panel_b_diagnostics/ (GLM-5.3 and "
               "GLM-5.2 first-party, reasoning off); returned cost $0.0000506 total, debited "
               "at an upper bound"),
    L.NonReconciledComponent(
        label="panel_b_canary_attempts_1_and_2",
        upper_bound_usd=0.0003,
        reason="out/q2_stage2_panel_b_canary_attempt1_ssl_failed/ (two HTTP-0 TLS failures, "
               "no cost) and out/q2_stage2_panel_b_canary_attempt2_glm53_excluded/ (GLM-5.3 "
               "HTTP 400, no cost; Sol HTTP 200, $0.000142). Error records carry no finite "
               "returned cost, so the attempts are debited at an upper bound rather than "
               "reconciled record by record"),
)
PRIOR_DIAGNOSTIC_COMPONENTS_B2_EXTRA = (
    L.NonReconciledComponent(
        label="panel_b2_walk_attempt1_cost_excluded",
        upper_bound_usd=0.0002,
        reason="out/q2_stage2_panel_b2_run_attempt1_cost_excluded/: one Sol walk probe, "
               "HTTP 200, $0.000142, whose ratio-calibrated projection ($11.13) exceeded "
               "the $8.00 stop; debited at an upper bound"),
)


class PanelBError(RuntimeError):
    """Fail-closed Panel B activation/calibration failure."""


# =======================================================================================
# Activation — an explicit, idempotent, fully reversible rebinding
# =======================================================================================

#: (module, attribute, Panel B value). Every attribute listed here is a v7 constant that some
#: module captures BY NAME (or reads as a module global) and would otherwise carry a v7 value
#: into a Panel B run. Nothing here is a behaviour change: each value is the Panel B analogue
#: of the v7 constant it replaces.
def _main_alias(mod: Any) -> Optional[Any]:
    """The `__main__` copy of `mod`, when `mod` is the file being run with `python -m`.

    `python -m alignment.q2_v7.canary` executes canary.py as `__main__`; a later
    `import alignment.q2_v7.canary` (this module's `C`) is a SECOND module object with its own
    globals. Rebinding only the imported copy would leave the RUNNING copy on v7 values — the
    v7 run dir, the v7 panel — which is exactly the silent misrouting this profile exists to
    prevent. So every binding is applied to both objects when they are the same file.
    """
    main = sys.modules.get("__main__")
    if main is None or main is mod:
        return None
    try:
        same = (Path(getattr(main, "__file__", "")).resolve()
                == Path(getattr(mod, "__file__", "")).resolve())
    except (OSError, ValueError):
        return None
    return main if same else None


#: Which variant `activate()` applied: None (inactive), "B" or "B2".
_VARIANT: Optional[str] = None


def active_variant() -> Optional[str]:
    return _VARIANT


def _b2_overrides() -> tuple[tuple[Any, str, Any], ...]:
    """AMD-PB-02: the three Sol-row departures from variant B."""
    return (
        (G, "PANEL_ORDER", PANEL_B2_ORDER),
        (C, "PANEL_ORDER", PANEL_B2_ORDER),
        (G, "GLOBAL_STUDY_STOP", HARD_STOP_B2_USD),
        (L, "HARD_STOP_USD", HARD_STOP_B2_USD),
        (G, "FRAMING_TOKEN_TOLERANCE_BY_TAG", dict(FRAMING_TOKEN_TOLERANCE_B2)),
        (SR, "DEFAULT_RUN_DIR", STUDY_RUN_DIR_B2),
        (C, "PRIOR_DIAGNOSTIC_COMPONENTS",
         PRIOR_DIAGNOSTIC_COMPONENTS_B + PRIOR_DIAGNOSTIC_COMPONENTS_B2_EXTRA),
    )


def _bindings(variant: str = "B") -> tuple[tuple[Any, str, Any], ...]:
    base = _base_bindings()
    if variant == "B2":
        # later entries win: apply B, then overlay the B2 departures
        base = base + _b2_overrides()
    elif variant != "B":
        raise ValueError(f"unknown Panel B variant {variant!r}; expected 'B' or 'B2'")
    extra: list[tuple[Any, str, Any]] = []
    for mod, name, value in base:
        alias = _main_alias(mod)
        if alias is not None and hasattr(alias, name):
            extra.append((alias, name, value))
    return base + tuple(extra)


def _base_bindings() -> tuple[tuple[Any, str, Any], ...]:
    return (
        # --- gate: the panel roster, its endpoints, the stop, the amendment allow-list ---
        (G, "PANEL_ORDER", PANEL_B_ORDER),
        (G, "FALLBACK_SEQUENCES", dict(FALLBACK_SEQUENCES_B)),
        (G, "FALLBACK_SEQUENCE", dict(FALLBACK_SEQUENCES_B)),
        (G, "GLOBAL_STUDY_STOP", HARD_STOP_B_USD),
        (G, "APPROVED_FALLBACK_AMENDMENTS", APPROVED_FALLBACK_AMENDMENTS_B),
        # `gate.ENDPOINT_SNAPSHOT` is the module-level snapshot path; the study path always
        # passes an explicit `spec=`/`path=`, but anything that falls back to the module
        # attribute must read Panel B's manifest, not v7's. (The two functions that take it
        # as a DEF-TIME default keep the v7 path in their signature; both are always called
        # with an explicit argument on the Panel B path.)
        (G, "ENDPOINT_SNAPSHOT", ROOT / SNAPSHOT_PATH_B),
        # --- envelope: the SHA-bound snapshot and the omitted-sampling set ---
        (E, "SNAPSHOT_PATH", SNAPSHOT_PATH_B),
        (E, "SNAPSHOT_SHA256", SNAPSHOT_SHA256_B),
        (E, "PROVIDER_DEFAULT_SAMPLING_MODELS", PROVIDER_DEFAULT_SAMPLING_MODELS_B),
        # --- ledger: the Panel-B-only stop ---
        (L, "HARD_STOP_USD", HARD_STOP_B_USD),
        # --- canary: imports PANEL_ORDER/FALLBACK_SEQUENCES BY NAME, so both must be rebound
        #     on the canary module itself, not only on `gate` ---
        (C, "PANEL_ORDER", PANEL_B_ORDER),
        (C, "FALLBACK_SEQUENCES", dict(FALLBACK_SEQUENCES_B)),
        (C, "DEFAULT_RUN_DIR", CANARY_RUN_DIR_B),
        (C, "PRIOR_RECORD_DIRS", PRIOR_RECORD_DIRS_B),
        (C, "PRIOR_DIAGNOSTIC_COMPONENTS", PRIOR_DIAGNOSTIC_COMPONENTS_B),
        # --- study_run: the run dir and the two amendment seams ---
        (SR, "DEFAULT_RUN_DIR", STUDY_RUN_DIR_B),
        (SR, "FALLBACK_AMENDMENT_BY_MODEL", dict(FALLBACK_AMENDMENT_BY_MODEL_B)),
        (SR, "USAGE_CALIBRATED_MODELS", USAGE_CALIBRATED_MODELS_B),
    )


#: The v7 values captured the first time `activate()` runs, so `deactivate()` restores the
#: originals rather than some intermediate state. `None` means "never activated".
_SAVED: Optional[tuple[tuple[Any, str, Any], ...]] = None


def is_active() -> bool:
    """True iff `activate()` has run and `deactivate()` has not undone it."""
    return _SAVED is not None


def activate(variant: str = "B") -> None:
    """Rebind every v7 constant Panel B replaces. Idempotent; reversed by `deactivate()`.
    `variant="B2"` additionally applies the AMD-PB-02 overrides (Sol-only re-run).

    This is the ONLY way Panel B's values enter the harness. It is deliberately explicit: no
    module activates itself at import, so importing `panel_b` (as `study_run.pinned_tokenizer`
    does, lazily) can never change a v7 run's behaviour.
    """
    global _SAVED, _VARIANT
    if _SAVED is not None:
        if _VARIANT != variant:
            raise RuntimeError(f"Panel {_VARIANT} is already active; deactivate() first")
        return                                   # already active; rebinding again is a no-op
    bindings = _bindings(variant)
    saved: dict[tuple[int, str], tuple[Any, str, Any]] = {}
    for mod, name, _ in bindings:
        saved.setdefault((id(mod), name), (mod, name, getattr(mod, name)))   # first = v7
    _SAVED = tuple(saved.values())
    _VARIANT = variant
    for mod, name, value in bindings:
        setattr(mod, name, value)


def deactivate() -> None:
    """Restore every v7 constant `activate()` rebound. Idempotent."""
    global _SAVED, _VARIANT
    if _SAVED is None:
        return
    for mod, name, value in _SAVED:
        setattr(mod, name, value)
    _SAVED = None
    _VARIANT = None


def activate_from_env(env: Optional[Mapping[str, str]] = None) -> bool:
    """Activate Panel B iff ``Q2_PANEL=B`` (or ``B2`` for the AMD-PB-02 Sol re-run) is set.

    Wired into `canary.main`, `study_run.main` and `study_extract.load_draws`, so one
    environment variable selects the panel for a whole run. Unset, it does nothing at all.
    """
    source = os.environ if env is None else env
    value = str(source.get("Q2_PANEL", "") or "").strip().upper()
    if value in ("B", "B2"):
        activate(value)
        return True
    return False


# =======================================================================================
# AMD-PB-01 (2) — the usage-calibrated token counter for a closed model
# =======================================================================================

class UsageCalibratedCounter:
    """A ``str -> int`` input-token counter for a closed model with no published tokenizer.

    This is **not** the model's exact tokenizer, and it does not claim to be. It counts text
    with OpenAI's PUBLISHED ``o200k_base`` encoding (`tiktoken`), which is the closest public
    stand-in available for a closed OpenAI-family model; the true billed count may differ.

    Deliberately NOT a `gate.PinnedTokenizer`: `gate.project_full_grid` dispatches on the type,
    and a plain callable is labelled `fixed_overhead_fallback` — which is exactly the honest
    label for this counter, and is why `require_frozen_c2_serialization` must be shown the
    AMD-PB-01 signature before the projection may authorize spend.

    `__call__` counts the request's message CONTENT only. The gate then adds the frozen
    fixed per-message template overhead (`gate.chat_template_overhead`) on top, standing in
    for the provider's request framing (role markers, turn delimiters, the generation prompt).
    That substitution is conservative only while the provider's REAL framing is at or below
    that fixed overhead, so the model's own persisted walk probe is used to BOUND it:

        framing = probe.usage.prompt_tokens - o200k_base(probe payload text)

    and the counter fails closed if that framing is negative (the probe cannot be reconciled
    at all) or larger than `gate.chat_template_overhead(len(messages))` (the gate's overhead
    would understate the real framing, so the projection would no longer be conservative).

    The probe is read LAZILY on the FIRST call, not at construction, so building a runner does
    not depend on a run directory that a `walk` stage has not yet written. The probe selected
    is the LATEST successful (HTTP 200, integer `usage.prompt_tokens`) one for this model.

    Fails closed: with no usable envelope on disk, or with `tiktoken` unavailable, there is no
    framing check and therefore no projection and no promotion.
    """

    #: OpenAI's published encoding. Not the model's pinned tokenizer — see the docstring.
    ENCODING = "o200k_base"
    METHOD = "tiktoken_content_count_plus_fixed_overhead"

    def __init__(self, model: str, *, run_dir: Path):
        self.model = str(model)
        self.run_dir = Path(run_dir)
        self._enc: Any = None
        self._checked = False
        self._source_draw_id: Optional[str] = None
        self._timestamp: Optional[str] = None
        self._probe_prompt_tokens: Optional[int] = None
        self._probe_payload_tokens: Optional[int] = None
        self._framing: Optional[int] = None
        self._framing_cap: Optional[int] = None

    # --- the public encoding --------------------------------------------------------------
    def _encoding(self) -> Any:
        if self._enc is not None:
            return self._enc
        try:
            import tiktoken                                          # noqa: WPS433
        except Exception as exc:                                     # pragma: no cover
            raise SR.StudyRunError(
                f"`tiktoken` is not importable, so the AMD-PB-01 input-token count for "
                f"{self.model!r} cannot be produced ({type(exc).__name__}: {exc}); install "
                "the `stage2` extra. There is no projection and no promotion without it"
            ) from exc
        try:
            self._enc = tiktoken.get_encoding(self.ENCODING)
        except Exception as exc:
            raise SR.StudyRunError(
                f"`tiktoken` cannot load the {self.ENCODING!r} encoding needed to count "
                f"input tokens for {self.model!r} ({type(exc).__name__}: {exc})") from exc
        return self._enc

    @staticmethod
    def _tiktoken_version() -> Optional[str]:
        try:
            import tiktoken                                          # noqa: WPS433
            return str(getattr(tiktoken, "__version__", "") or "") or None
        except Exception:                                            # pragma: no cover
            return None

    # --- the framing check ------------------------------------------------------------------
    def _check_framing(self) -> None:
        """Bound the provider's fixed request framing with this model's own walk probe."""
        if self._checked:
            return
        enc = self._encoding()
        try:
            envelopes = SR.walk_store(self.run_dir).envelopes()
        except Exception as exc:
            raise SR.StudyRunError(
                f"cannot read the walk records under {self.run_dir} to bound the provider "
                f"framing for {self.model!r} ({type(exc).__name__}: {exc}); AMD-PB-01 "
                "requires a persisted successful walk probe before any projection") from exc

        usable = []
        for env in envelopes:
            if getattr(env, "model", None) != self.model:
                continue
            if int(getattr(env, "http_status", 0) or 0) != 200:
                continue
            tokens = (getattr(env, "usage", None) or {}).get("prompt_tokens")
            if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens <= 0:
                continue
            usable.append((str(getattr(env, "timestamp", "") or ""), env, int(tokens)))
        if not usable:
            raise SR.StudyRunError(
                f"no successful walk probe with reported `usage.prompt_tokens` for "
                f"{self.model!r} under {self.run_dir}; AMD-PB-01's framing check has nothing "
                "to bound the provider framing against, so there is no projection")

        _, env, prompt_tokens = max(usable, key=lambda row: row[0])
        messages = (getattr(env, "request_body", None) or {}).get("messages")
        if not isinstance(messages, list) or not messages:
            raise SR.StudyRunError(
                f"the walk envelope for {self.model!r} carries no request messages; the "
                "payload it was billed for cannot be reconstructed")
        try:
            text = "\n".join(m["content"] for m in messages)
        except (KeyError, TypeError) as exc:
            raise SR.StudyRunError(
                f"the walk envelope for {self.model!r} has a message with no `content`; its "
                f"payload cannot be reconstructed ({exc})") from exc

        payload_tokens = len(enc.encode(text))
        framing = prompt_tokens - payload_tokens
        cap = G.chat_template_overhead(len(messages))
        if framing < 0:
            raise SR.StudyRunError(
                f"the walk probe for {self.model!r} was billed {prompt_tokens} prompt tokens "
                f"but its payload encodes to {payload_tokens} {self.ENCODING} tokens: a "
                "NEGATIVE provider framing means this encoding over-counts the provider's "
                "own tokenizer, so the projection would not be conservative")
        if framing > cap:
            raise SR.StudyRunError(
                f"the walk probe for {self.model!r} implies {framing} tokens of provider "
                f"framing, above the {cap} tokens `gate.chat_template_overhead"
                f"({len(messages)})` adds on the fallback path; the projection would "
                "UNDERSTATE the billed request, so it is refused")

        self._source_draw_id = str(getattr(env, "draw_id", "") or "")
        self._timestamp = str(getattr(env, "timestamp", "") or "")
        self._probe_prompt_tokens = prompt_tokens
        self._probe_payload_tokens = payload_tokens
        self._framing = framing
        self._framing_cap = cap
        self._checked = True

    # --- the counter itself -------------------------------------------------------------
    def __call__(self, text: str) -> int:
        self._check_framing()
        return len(self._encoding().encode(str(text)))

    def identity(self) -> dict:
        """The record of HOW this count was produced, for the projection's audit trail."""
        self._check_framing()
        return {
            "method": self.METHOD,
            "encoding": self.ENCODING,
            "tiktoken_version": self._tiktoken_version(),
            "amendment": AMENDMENT,
            "signed_amendment": AMENDMENT,
            "model": self.model,
            "run_dir": str(self.run_dir),
            "calibration_draw_id": self._source_draw_id,
            "calibration_timestamp": self._timestamp,
            "probe_prompt_tokens": self._probe_prompt_tokens,
            "probe_payload_tokens": self._probe_payload_tokens,
            "provider_framing_tokens": self._framing,
            "framing_cap_tokens": self._framing_cap,
        }

    def __repr__(self) -> str:                                    # pragma: no cover
        return (f"UsageCalibratedCounter(model={self.model!r}, run_dir={str(self.run_dir)!r}, "
                f"framing_checked={self._checked})")


def usage_calibrated_counter(model: str, *, run_dir: Path) -> Callable[[str], int]:
    """The AMD-PB-01 input-token counter for a closed model. See `UsageCalibratedCounter`."""
    return UsageCalibratedCounter(model, run_dir=Path(run_dir))
