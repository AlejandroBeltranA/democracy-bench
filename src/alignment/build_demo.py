"""Build a single self-contained demo/app.html from the out/*.json the drivers produced.

No server, no fetch (file:// blocks CORS): the JSON is inlined into the page. Re-run after
the drivers to refresh. The page leads with the frozen-default gap, shows the steering fix,
the tracking with 95% CIs (greying out non-significant cases), the tier ladder, and the UK
government-change floor-hold beat — under a prominent provenance banner built from the same
caveats the drivers emit (Gate 1 approved but 2nd-person review outstanding; GBR W6 = EVS2018
proxy; model SIMULATED; scenario data synthetic).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
DEMO = ROOT / "demo"


def _load(name: str):
    p = OUT / name
    return json.loads(p.read_text()) if p.exists() else None


def build_caveats(sources: dict, modes: list) -> list[dict]:
    cav = []
    so = sources.get("gate1_signoff", {})
    if sources.get("json_status") == "signed_off":
        cav.append({"level": "ok",
                    "text": f"Gate 1 APPROVED — real WVS/EVS targets "
                            f"({so.get('reviewer','?')}, {so.get('date','?')})"})
        if not so.get("second_person_class_review"):
            cav.append({"level": "warn",
                        "text": "2nd-person class review OUTSTANDING — floor/contestable/"
                                "excluded assignments not independently verified"})
    else:
        cav.append({"level": "warn", "text": "Targets not yet Gate-1 signed off"})
    cav.append({"level": "warn",
                "text": "GBR Wave 6 = EVS2018 proxy (EVS2018→WVS2022), NOT WVS Wave 6"})
    # model caveat derived from the actual output modes (real MLX/Ollama vs simulation)
    real = sorted({m.split(":", 1)[-1] for m in modes if "SIMULATED" not in m})
    sim = [m for m in modes if "SIMULATED" in m]
    if real and not sim:
        cav.append({"level": "ok", "text": f"Model: {', '.join(real)} (real local model)"})
    elif real and sim:
        cav.append({"level": "warn",
                    "text": f"MIXED model state — some panels real ({', '.join(real)}), "
                            f"some SIMULATED. Re-run all drivers with one model."})
    else:
        cav.append({"level": "sim",
                    "text": "Model is SIMULATED — distributions are a stand-in, not a real LLM"})
    cav.append({"level": "synth",
                "text": "UK government-change scenario data is SYNTHETIC (Gate 2 pending)"})
    return cav


def assemble() -> dict:
    sources = json.loads((ROOT / "data" / "targets" / "SOURCES.json").read_text())
    loops = {c: _load(f"loop_{c}_w67.json") for c in ("USA", "GBR")}
    compare = _load("compare_tiers_GBR_w7.json")
    scenario = _load("scenario_uk_gov_change.json")
    modes = [d["mode"] for d in [*loops.values(), compare, scenario] if d and "mode" in d]
    return {
        "caveats": build_caveats(sources, modes),
        "loops": loops, "compare": compare, "scenario": scenario,
    }


def build(output_dir: Path | None = None) -> Path:
    data = assemble()
    demo_dir = output_dir or DEMO
    demo_dir.mkdir(exist_ok=True)
    html = TEMPLATE.replace("__DATA__", json.dumps(data))
    out = demo_dir / "app.html"
    out.write_text(html)
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Democracy Bench — demo</title>
<style>
  :root{--bg:#0f1419;--card:#1a2029;--ink:#e6edf3;--mut:#8b98a5;--line:#2b3440;
        --target:#6ea8fe;--default:#9aa4b2;--steered:#3fb950;--t1:#d29922;--t2:#3fb950;
        --ok:#2ea043;--warn:#d29922;--sim:#6e7681;--synth:#da3633;}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:24px}
  h1{font-size:22px;margin:0 0 2px} h2{font-size:16px;margin:26px 0 10px;color:var(--ink)}
  .sub{color:var(--mut);margin:0 0 16px}
  .banner{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0 6px}
  .pill{font-size:12.5px;padding:5px 10px;border-radius:20px;border:1px solid var(--line)}
  .ok{background:rgba(46,160,67,.12);border-color:var(--ok)}
  .warn{background:rgba(210,153,34,.12);border-color:var(--warn)}
  .sim{background:rgba(110,118,129,.15);border-color:var(--sim)}
  .synth{background:rgba(218,54,51,.12);border-color:var(--synth)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
  .row{display:flex;flex-wrap:wrap;gap:16px}
  .row .card{flex:1;min-width:300px}
  .qt{font-size:13px;color:var(--mut);margin:0 0 8px}
  .rep{font-size:13px;margin:6px 0 2px}
  .rep b{font-size:15px}
  .legend{font-size:12px;color:var(--mut);margin-top:6px}
  .sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 10px;vertical-align:middle}
  .track{font-size:13px;margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
  .muted{color:var(--mut)} .grey{opacity:.5}
  .floorcard{border-color:var(--steered)}
  .tag{font-size:11px;padding:2px 7px;border-radius:6px;border:1px solid var(--line);margin-left:6px}
  footer{color:var(--mut);font-size:12px;margin-top:30px;border-top:1px solid var(--line);padding-top:12px}
</style></head>
<body>
<h1>Democracy Bench <span class="muted" style="font-size:14px">— real-time alignment to public values</span></h1>
<p class="sub">Frozen default → steer to the polity → does it track when values shift? With a rights floor that must hold.</p>
<div id="banner" class="banner"></div>
<div id="content"></div>
<footer>
  Bars: <span class="sw" style="background:var(--target)"></span>population target ·
  <span class="sw" style="background:var(--default)"></span>model default ·
  <span class="sw" style="background:var(--steered)"></span>model steered.
  Elasticity ≈1 = reproduced the population's move; ~0 = frozen; CI is 95% (sampling error only).
  Approved real targets, but read every caveat above.
</footer>
<script>
const DATA = __DATA__;
const C = {target:'#6ea8fe', default:'#9aa4b2', steered:'#3fb950', t1:'#d29922', t2:'#3fb950'};
const el = (t,c,h)=>{const e=document.createElement(t); if(c)e.className=c; if(h!=null)e.innerHTML=h; return e;};

function bars(series, labels){
  // grouped vertical bars, values in [0,1]. series=[{name,color,values}]
  const W=300,H=120,pad=22,n=labels.length,g=series.length;
  const bw=(W-2*pad)/n/(g+0.6), gap=bw*0.15;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  s+=`<line x1="${pad}" y1="${H-18}" x2="${W-4}" y2="${H-18}" stroke="#2b3440"/>`;
  labels.forEach((lab,i)=>{
    const x0=pad+i*((W-2*pad)/n);
    series.forEach((se,j)=>{
      const v=se.values[i]||0, bh=v*(H-40), x=x0+6+j*(bw+gap), y=H-18-bh;
      s+=`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${se.color}" rx="1"><title>${se.name}: ${(v*100).toFixed(0)}%</title></rect>`;
    });
    s+=`<text x="${(x0+(W-2*pad)/n/2).toFixed(1)}" y="${H-6}" font-size="8" fill="#8b98a5" text-anchor="middle">${lab.length>10?lab.slice(0,9)+'…':lab}</text>`;
  });
  return s+`</svg>`;
}

function ciBar(tr){
  // horizontal elasticity axis [-2,2] with point + 95% CI band
  if(tr.elasticity==null) return `<span class="muted">elasticity n/a — population didn't move</span>`;
  const W=260,H=34,ax=v=>20+((Math.max(-2,Math.min(2,v))+2)/4)*(W-30);
  const e=tr.elasticity, ci=tr.elasticity_ci, sig=tr.population_delta_significant;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">`;
  s+=`<line x1="20" y1="17" x2="${W-10}" y2="17" stroke="#2b3440"/>`;
  s+=`<line x1="${ax(0)}" y1="6" x2="${ax(0)}" y2="28" stroke="#3a4452"/>`;
  s+=`<line x1="${ax(1)}" y1="9" x2="${ax(1)}" y2="25" stroke="#2ea043" stroke-dasharray="2"/>`;
  const col = sig===false ? '#6e7681' : '#3fb950';
  if(ci){ s+=`<line x1="${ax(ci[0])}" y1="17" x2="${ax(ci[1])}" y2="17" stroke="${col}" stroke-width="3" opacity=".5"/>`; }
  s+=`<circle cx="${ax(e)}" cy="17" r="4" fill="${col}"/>`;
  s+=`</svg>`;
  let lab=`elasticity ${e>=0?'+':''}${e.toFixed(2)}`;
  if(ci) lab+=` <span class="muted">95%CI[${ci[0].toFixed(2)},${ci[1].toFixed(2)}]</span>`;
  else lab+=` <span class="muted">(CI n/a)</span>`;
  if(sig===false) lab+=` <span class="tag warn">pop Δ not significant</span>`;
  return s+'<div class="muted" style="font-size:12px">'+lab+'</div>';
}

function itemCard(id, it, floor){
  const c=el('div', floor?'card floorcard':'card');
  c.appendChild(el('div','qt', (floor?'FLOOR · ':'')+ (it.prompt||id)));
  const ser=[{name:'population target',color:C.target,values:it.dist.target}];
  ser.push({name:'model default',color:C.default,values:it.dist.default});
  if(it.dist.steered) ser.push({name:'model steered',color:C.steered,values:it.dist.steered});
  c.insertAdjacentHTML('beforeend', bars(ser, it.labels));
  if(floor){
    c.insertAdjacentHTML('beforeend',
      `<div class="rep">floor ${it.held?'<b style="color:var(--steered)">HELD ✓</b>':'<b style="color:var(--synth)">VIOLATED ✗</b>'} — not steered toward any mandate <span class="muted">(gap ${it.protective_gap>=0?'+':''}${(it.protective_gap||0).toFixed(2)})</span></div>`);
  }else{
    c.insertAdjacentHTML('beforeend',
      `<div class="rep">representation <b>${it.rep_default.toFixed(2)}</b> → <b style="color:var(--steered)">${it.rep_steered.toFixed(2)}</b> <span class="muted">(+${it.rep_gain.toFixed(2)} when steered to the polity)</span></div>`);
    c.insertAdjacentHTML('beforeend', '<div class="track">'+ciBar(it.tracking)+'</div>');
  }
  return c;
}

function renderLoop(country, L){
  if(!L) return;
  const wrap=el('div');
  const sa=L.source_a.label, sb=L.source_b.label;
  wrap.appendChild(el('h2',null,`${country} — measure → steer → track <span class="muted" style="font-size:12px">(${sa} → ${sb})</span>`));
  const row=el('div','row');
  Object.entries(L.contestable||{}).forEach(([id,it])=>row.appendChild(itemCard(id,it,false)));
  Object.entries(L.floor||{}).forEach(([id,it])=>row.appendChild(itemCard(id,it,true)));
  wrap.appendChild(row);
  return wrap;
}

function renderCompare(cmp){
  if(!cmp) return;
  const wrap=el('div');
  wrap.appendChild(el('h2',null,`Steering tiers — ${cmp.country} <span class="muted" style="font-size:12px">(representation should climb: default ＜ Tier 1 label ＜ Tier 2 injected distribution)</span>`));
  const row=el('div','row');
  Object.entries(cmp.items).forEach(([id,it])=>{
    const c=el('div','card'); c.appendChild(el('div','qt',id));
    const ser=[{name:'default',color:C.default,values:[it.rep_default]},
               {name:'Tier 1',color:C.t1,values:[it.rep_tier1]},
               {name:'Tier 2',color:C.t2,values:[it.rep_tier2]}];
    c.insertAdjacentHTML('beforeend', bars(ser,['default','Tier1','Tier2']));
    c.insertAdjacentHTML('beforeend', `<div class="rep muted">${it.rep_default.toFixed(2)} → ${it.rep_tier1.toFixed(2)} → <b style="color:var(--steered)">${it.rep_tier2.toFixed(2)}</b></div>`);
    row.appendChild(c);
  });
  wrap.appendChild(row); return wrap;
}

function renderScenario(sc){
  if(!sc) return;
  const wrap=el('div');
  wrap.appendChild(el('h2',null,`UK government change — re-align to the new mandate, hold the floor <span class="tag synth">SYNTHETIC data (Gate 2)</span>`));
  const row=el('div','row');
  Object.entries(sc.contestable||{}).forEach(([id,it])=>{
    const c=el('div','card'); c.appendChild(el('div','qt',id));
    c.insertAdjacentHTML('beforeend', `<div class="rep">to incoming mandate: <b>${it.rep_to_incoming_default.toFixed(2)}</b> → <b style="color:var(--steered)">${it.rep_to_incoming_aligned.toFixed(2)}</b> <span class="muted">(+${it.rep_gain.toFixed(2)})</span></div>`);
    const tr=it.tracking_vs_mandate_shift;
    c.insertAdjacentHTML('beforeend', `<div class="track muted">tracks mandate shift: elasticity ${tr.elasticity==null?'n/a':(tr.elasticity>=0?'+':'')+tr.elasticity.toFixed(2)} · dir ${tr.direction_match}</div>`);
    row.appendChild(c);
  });
  Object.entries(sc.floor||{}).forEach(([id,it])=>{
    const c=el('div','card floorcard'); c.appendChild(el('div','qt','FLOOR · '+id));
    c.insertAdjacentHTML('beforeend', `<div class="rep">${it.held?'<b style="color:var(--steered)">HELD ✓</b>':'<b style="color:var(--synth)">VIOLATED ✗</b>'} — NOT steered to the mandate</div>`);
    row.appendChild(c);
  });
  wrap.appendChild(row); return wrap;
}

(function(){
  const b=document.getElementById('banner');
  DATA.caveats.forEach(c=>b.appendChild(el('span','pill '+c.level, c.text)));
  const root=document.getElementById('content');
  ['USA','GBR'].forEach(c=>{const n=renderLoop(c,DATA.loops[c]); if(n)root.appendChild(n);});
  const cm=renderCompare(DATA.compare); if(cm)root.appendChild(cm);
  const sc=renderScenario(DATA.scenario); if(sc)root.appendChild(sc);
})();
</script></body></html>"""


if __name__ == "__main__":
    p = build()
    print(f"wrote {p.relative_to(ROOT)}  ({p.stat().st_size} bytes)")
