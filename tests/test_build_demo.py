"""The demo builder produces a self-contained page that inlines the data and the caveats."""
import json

from alignment import build_demo


def test_build_caveats_surface_signoff_proxy_and_sim():
    sources = json.loads((build_demo.ROOT / "data" / "targets" / "SOURCES.json").read_text())
    cav = build_demo.build_caveats(sources, ["SIMULATED (no model — plumbing only)"])
    texts = " ".join(c["text"].lower() for c in cav)
    assert "approved" in texts                       # Gate 1 signed off
    assert "2nd-person" in texts                     # outstanding review surfaced
    assert "proxy" in texts                          # GBR W6 proxy
    assert "simulated" in texts                      # model is a stand-in (all-sim modes)


def test_build_caveats_real_model_drops_simulated():
    sources = json.loads((build_demo.ROOT / "data" / "targets" / "SOURCES.json").read_text())
    cav = build_demo.build_caveats(sources, ["mlx:mlx-community/Llama-3.2-3B-Instruct-4bit"] * 4)
    texts = " ".join(c["text"].lower() for c in cav)
    assert "real local model" in texts               # real model surfaced
    assert "simulated" not in texts                  # no false 'simulated' caveat


def test_page_builds_and_inlines_data(tmp_path):
    p = build_demo.build(output_dir=tmp_path)
    html = p.read_text()
    assert p.name == "app.html"
    assert "const DATA =" in html
    assert "__DATA__" not in html                    # placeholder was substituted
    assert "EVS2018" in html                         # provenance reached the page
    # the inlined data is valid JSON and carries distributions for the bars
    blob = html.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    data = json.loads(blob)
    usa = data["loops"].get("USA")
    assert usa and usa["contestable"], "USA loop data missing"
    any_item = next(iter(usa["contestable"].values()))
    assert "dist" in any_item and "target" in any_item["dist"]
