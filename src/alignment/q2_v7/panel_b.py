"""Panel B — the labelled frontier-model extension of the Stage-2 v7 harness (AMD-PB-01).

Panel B is a SEPARATE, labelled panel run on the same frozen instrument as the v7 panel. It
changes no v7 constant and no v7 behaviour: every v7 value stays exactly where it is, and
Panel B is selected explicitly (``panel_b.activate()``, or ``Q2_PANEL=B`` in the environment)
before any run. With the environment variable unset, nothing in this module executes.

The panel is ``("z-ai/glm-5.3", "openai/gpt-5.6-sol")``, frozen by the operator's decision of
2026-09-22 together with the four departures from v7 that the signed pre-outcome amendment
**AMD-PB-01** authorizes, and nothing else:

1. **Sampling parameters omitted for a closed model.** `openai/gpt-5.6-sol`'s promoted
   endpoint declares NEITHER ``temperature`` NOR ``top_p`` in its supported-parameter set.
   Under ``require_parameters: true`` a declared-but-absent parameter is a refusal, so the
   frozen envelope must OMIT both keys rather than send them as nulls; the provider's own
   default sampling then applies and is recorded as such. This is a wire-format concession,
   not a design change: the envelope is otherwise byte-identical to v7's.

2. **Usage-calibrated projection for a closed model.** `openai/gpt-5.6-sol` publishes no
   tokenizer and no chat template, so the frozen C2 pinned-serialization projection is not
   executable for it at all. Its input-token counter is instead CALIBRATED from its own
   persisted walk probe: the provider's reported ``prompt_tokens`` divided by the probe's
   character length, applied per character. `gate.project_full_grid` labels the resulting
   projection ``fixed_overhead_fallback`` and adds the frozen per-message template overhead on
   top of the calibrated count, so the projection is conservative in the budget's direction.
   ``gate.require_frozen_c2_serialization`` still refuses that projection unless AMD-PB-01 is
   named, which is the whole point of the amendment: the fallback is auditable, not silent.
   `z-ai/glm-5.3` publishes a real tokenizer and chat template and takes the ORDINARY frozen
   C2 path — the amendment applies to the Sol row only.

3. **A Panel-B-only $11.00 hard stop.** Panel B's spend is accounted separately from the v7
   panel's $8.50 stop, and prior spend is reconciled ONLY from Panel B's own canary raw
   directory. No v7 record is re-reconciled into Panel B, and no Panel B record counts against
   the v7 stop; the two ledgers do not touch.

4. **GLM on a third-party fp8 endpoint.** `z-ai/glm-5.3` is promoted on ``reka/fp8`` rather
   than a first-party bf16 endpoint, by budget decision. The quantization is recorded in the
   snapshot and travels with every projection and every estimand, so the reader can see it.

Each model has a SINGLE endpoint, so there is no promotion walk to fall back through: a failed
capability probe ends that model's run rather than selecting a substitute.

Usage::

    Q2_PANEL=B .venv/bin/python -m alignment.q2_v7.canary --i-have-authorized-paid-spend
    Q2_PANEL=B .venv/bin/python -m alignment.q2_v7.study_run walk --model z-ai/glm-5.3 ...

or, in process::

    from alignment.q2_v7 import panel_b
    panel_b.activate()
"""
from __future__ import annotations

import math
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

#: The frozen Panel B roster, in order: GLM (primary) then Sol (independent replication).
PANEL_B_ORDER: tuple[str, ...] = ("z-ai/glm-5.3", "openai/gpt-5.6-sol")

#: One endpoint per model — there is no walk fallback on Panel B.
FALLBACK_SEQUENCES_B: Mapping[str, tuple[str, ...]] = {
    "z-ai/glm-5.3": ("reka/fp8",),
    "openai/gpt-5.6-sol": ("openai",),
}

#: Panel-B-only spend ceiling (USD). Disjoint from the v7 panel's $8.50 stop.
HARD_STOP_B_USD = 11.00

#: The committed Panel B endpoint snapshot, SHA-256-bound exactly as v7's is.
SNAPSHOT_PATH_B = "out/q2_stage2_panel_b_snapshot/manifest.json"
SNAPSHOT_SHA256_B = "56f64dd974e2e7bfd86d0570e67feded34e9a6a1e274af2901d7cb7be41c061b"

#: Run directories. Panel B never writes into a v7 run directory.
CANARY_RUN_DIR_B = ROOT / "out" / "q2_stage2_panel_b_canary"
STUDY_RUN_DIR_B = ROOT / "out" / "q2_stage2_panel_b_run"

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
PRIOR_DIAGNOSTIC_COMPONENTS_B: tuple[Any, ...] = ()


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


def _bindings() -> tuple[tuple[Any, str, Any], ...]:
    base = _base_bindings()
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


def activate() -> None:
    """Rebind every v7 constant Panel B replaces. Idempotent; reversed by `deactivate()`.

    This is the ONLY way Panel B's values enter the harness. It is deliberately explicit: no
    module activates itself at import, so importing `panel_b` (as `study_run.pinned_tokenizer`
    does, lazily) can never change a v7 run's behaviour.
    """
    global _SAVED
    if _SAVED is not None:
        return                                   # already active; rebinding again is a no-op
    bindings = _bindings()
    _SAVED = tuple((mod, name, getattr(mod, name)) for mod, name, _ in bindings)
    for mod, name, value in bindings:
        setattr(mod, name, value)


def deactivate() -> None:
    """Restore every v7 constant `activate()` rebound. Idempotent."""
    global _SAVED
    if _SAVED is None:
        return
    for mod, name, value in _SAVED:
        setattr(mod, name, value)
    _SAVED = None


def activate_from_env(env: Optional[Mapping[str, str]] = None) -> bool:
    """Activate Panel B iff ``Q2_PANEL=B`` (case-insensitive) is set. Returns whether it is.

    Wired into `canary.main`, `study_run.main` and `study_extract.load_draws`, so one
    environment variable selects the panel for a whole run. Unset, it does nothing at all.
    """
    source = os.environ if env is None else env
    if str(source.get("Q2_PANEL", "") or "").strip().upper() == "B":
        activate()
        return True
    return False


# =======================================================================================
# AMD-PB-01 (2) — the usage-calibrated token counter for a closed model
# =======================================================================================

class UsageCalibratedCounter:
    """A ``str -> int`` token counter calibrated from a closed model's own walk probe.

    Deliberately NOT a `gate.PinnedTokenizer`: `gate.project_full_grid` dispatches on the type,
    and a plain callable is labelled `fixed_overhead_fallback` — which is exactly the honest
    label for this counter, and is why `require_frozen_c2_serialization` must be shown the
    AMD-PB-01 signature before the projection may authorize spend.

    Calibration is LAZY: the persisted walk envelope is read on the FIRST call, not at
    construction, so building a runner does not depend on a run directory that a `walk` stage
    has not yet written. The ratio is ``prompt_tokens / characters`` taken from the LATEST
    successful (HTTP 200, usage present) probe for this model, and each subsequent count is
    ``ceil(len(text) * ratio)``. `gate.project_full_grid` then adds the frozen per-message
    template overhead on top, so the projected total sits ABOVE a true tokenizer count.

    Fails closed: with no such envelope on disk there is no calibration, and therefore no
    projection and no promotion.
    """

    def __init__(self, model: str, *, run_dir: Path):
        self.model = str(model)
        self.run_dir = Path(run_dir)
        self._ratio: Optional[float] = None
        self._source_draw_id: Optional[str] = None
        self._prompt_tokens: Optional[int] = None
        self._chars: Optional[int] = None
        self._timestamp: Optional[str] = None

    # --- calibration -------------------------------------------------------------------
    def _calibrate(self) -> float:
        if self._ratio is not None:
            return self._ratio
        try:
            envelopes = SR.walk_store(self.run_dir).envelopes()
        except Exception as exc:
            raise SR.StudyRunError(
                f"cannot read the walk records under {self.run_dir} to calibrate the "
                f"{self.model!r} token counter ({type(exc).__name__}: {exc}); AMD-PB-01 "
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
                f"{self.model!r} under {self.run_dir}; AMD-PB-01's usage-calibrated counter "
                "has nothing to calibrate against, so there is no projection")

        _, env, prompt_tokens = max(usable, key=lambda row: row[0])
        messages = (getattr(env, "request_body", None) or {}).get("messages")
        if not isinstance(messages, list) or not messages:
            raise SR.StudyRunError(
                f"the calibrating walk envelope for {self.model!r} carries no request "
                "messages; the character count it was billed for cannot be reconstructed")
        try:
            text = "\n".join(m["content"] for m in messages)
        except (KeyError, TypeError) as exc:
            raise SR.StudyRunError(
                f"the calibrating walk envelope for {self.model!r} has a message with no "
                f"`content`; its character count cannot be reconstructed ({exc})") from exc
        chars = len(text)
        if chars <= 0:
            raise SR.StudyRunError(
                f"the calibrating walk envelope for {self.model!r} serialises to zero "
                "characters; a zero denominator is not a calibration")

        self._prompt_tokens = prompt_tokens
        self._chars = chars
        self._source_draw_id = str(getattr(env, "draw_id", "") or "")
        self._timestamp = str(getattr(env, "timestamp", "") or "")
        self._ratio = prompt_tokens / chars
        return self._ratio

    # --- the counter itself -------------------------------------------------------------
    def __call__(self, text: str) -> int:
        ratio = self._calibrate()
        return int(math.ceil(len(text) * ratio))

    def identity(self) -> dict:
        """The record of HOW this counter was calibrated, for the projection's audit trail."""
        ratio = self._calibrate()
        return {
            "method": "usage_calibrated",
            "signed_amendment": AMENDMENT,
            "model": self.model,
            "run_dir": str(self.run_dir),
            "source_draw_id": self._source_draw_id,
            "source_timestamp": self._timestamp,
            "prompt_tokens": self._prompt_tokens,
            "characters": self._chars,
            "tokens_per_character": ratio,
        }

    def __repr__(self) -> str:                                    # pragma: no cover
        return (f"UsageCalibratedCounter(model={self.model!r}, run_dir={str(self.run_dir)!r}, "
                f"calibrated={self._ratio is not None})")


def usage_calibrated_counter(model: str, *, run_dir: Path) -> Callable[[str], int]:
    """The AMD-PB-01 counter for a closed model. See `UsageCalibratedCounter`."""
    return UsageCalibratedCounter(model, run_dir=Path(run_dir))
