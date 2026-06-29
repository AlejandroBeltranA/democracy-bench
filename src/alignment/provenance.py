"""Provenance for population targets — so a proxy or synthetic baseline is never shown as
plain WVS. Loaded by the demo drivers and written into their JSON output, so the demo
surface can render the right asterisk next to every number.

Driven by data/targets/SOURCES.json. The cardinal facts it encodes: Great Britain is absent
from WVS Wave 6, so the GBR W6 baseline is an explicit EVS2018 proxy (is_proxy=True); Gate 1
is signed off (real targets); and two caveats persist — the 2nd-person class review is
outstanding, and a proxy baseline must never be shown as plain WVS.
"""
from __future__ import annotations

import json
from pathlib import Path

_SOURCES = Path(__file__).resolve().parents[2] / "data" / "targets" / "SOURCES.json"


def load_sources() -> dict:
    return json.loads(_SOURCES.read_text())


_REAL_STATES = {"real_targets_pending_gate1_signoff", "signed_off"}


def targets_signed_off(sources: dict | None = None) -> bool:
    s = sources or load_sources()
    return s.get("json_status") == "signed_off"


def targets_are_real(sources: dict | None = None) -> bool:
    """True once the target_*.json files hold real (or real-proxy) numbers — whether or not
    Gate 1 is formally signed off."""
    s = sources or load_sources()
    return s.get("json_status") in _REAL_STATES


def targets_are_synthetic(sources: dict | None = None) -> bool:
    return not targets_are_real(sources)


def second_person_review_done(sources: dict | None = None) -> bool:
    """Whether the independent 2nd-person class-assignment review was recorded as done."""
    s = sources or load_sources()
    return bool(s.get("gate1_signoff", {}).get("second_person_class_review"))


def source_info(country: str, wave: int, sources: dict | None = None) -> dict:
    """Provenance for one polity-wave: {source_type, label, is_proxy, real_available, ...}.
    Falls back to an explicit 'unknown' rather than guessing."""
    s = sources or load_sources()
    info = s.get("polities", {}).get(country, {}).get(str(wave))
    if info is None:
        return {"source_type": "unknown", "label": "unknown", "is_proxy": False,
                "real_available": False, "note": "no provenance recorded"}
    return info


def baseline_caveats(country: str, waves: list[int], sources: dict | None = None) -> list[str]:
    """Human-readable caveats to print/show for a country's tracking baseline."""
    s = sources or load_sources()
    out = []
    if targets_are_synthetic(s):
        out.append("targets are SYNTHETIC stubs — not real numbers")
    elif not targets_signed_off(s):
        out.append("targets are REAL but Gate 1 sign-off is PENDING — not yet an approved benchmark")
    elif not second_person_review_done(s):
        out.append("Gate 1 APPROVED, but the 2nd-person class review is OUTSTANDING — "
                   "floor/contestable/excluded assignments not independently verified")
    for w in waves:
        info = source_info(country, w, s)
        if info.get("is_proxy"):
            out.append(f"{country} wave {w} = {info['label']} (proxy, NOT WVS{w})")
    return out
