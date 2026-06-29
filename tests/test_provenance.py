"""Provenance must cover every polity-wave and flag the GBR W6 EVS/IVS proxy + synthetic state."""
from alignment import provenance as P


def test_sources_cover_all_polity_waves():
    s = P.load_sources()
    for country in ("GBR", "USA"):
        for wave in (6, 7):
            info = P.source_info(country, wave, s)
            assert info["source_type"] != "unknown", f"{country} w{wave} has no provenance"
            assert "label" in info


def test_gbr_wave6_is_flagged_as_proxy_not_wvs6():
    info = P.source_info("GBR", 6)
    assert info["is_proxy"] is True
    assert "WVS Wave 6" in info["note"]            # explains GBR's absence from WVS6


def test_targets_signed_off():
    # Gate 1 is signed off -> real + approved (no longer pending/synthetic)
    assert P.targets_are_real() is True
    assert P.targets_are_synthetic() is False
    assert P.targets_signed_off() is True


def test_second_person_review_outstanding_is_surfaced():
    # signed off by a single reviewer; the independent class review wasn't done -> caveat
    assert P.second_person_review_done() is False
    caveats = P.baseline_caveats("USA", [6, 7])
    assert any("2nd-person" in c.lower() for c in caveats)
    assert not any("pending" in c.lower() for c in caveats)   # no longer 'sign-off pending'


def test_gbr_keeps_proxy_caveat_after_signoff():
    caveats = P.baseline_caveats("GBR", [6, 7])
    assert any("proxy" in c.lower() for c in caveats)         # proxy caveat persists
    assert not any("synthetic" in c.lower() for c in caveats)


def test_usa_has_no_proxy_caveat():
    # USA is in both WVS waves — no proxy asterisk (still gets the 2nd-person caveat)
    caveats = P.baseline_caveats("USA", [6, 7])
    assert not any("proxy" in c.lower() for c in caveats)
