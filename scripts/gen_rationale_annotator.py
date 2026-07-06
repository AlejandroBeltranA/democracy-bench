#!/usr/bin/env python3
"""Generate a self-contained HTML annotator from the rationale codesheet — a nicer way to
do the judge-free human coding than editing a CSV by hand. One rationale per card, keyboard
yes/no, autosave to localStorage, and an "Export CSV" button that writes the exact columns
score_rationale_codesheet.py reads. No external assets (opens from file://).

  python scripts/gen_rationale_annotator.py            # -> annotations/rationale_annotator.html
Then open that file in a browser, code, click Export, and:
  python scripts/score_rationale_codesheet.py <exported.csv>
"""
import argparse, csv, json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Democracy Bench — Rationale Coding</title>
<style>
  :root{--bg:#0f1115;--card:#191c23;--ink:#e8eaed;--mut:#9aa0aa;--line:#2a2e37;
        --blue:#4c8dff;--amber:#f0a53e;--green:#3ecf8e;--red:#ff6b6b;--accent:#4c8dff;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
  header{position:sticky;top:0;z-index:5;background:rgba(15,17,21,.92);backdrop-filter:blur(6px);
         border-bottom:1px solid var(--line);padding:12px 20px;}
  .bar{height:6px;background:var(--line);border-radius:4px;overflow:hidden;margin-top:8px}
  .fill{height:100%;background:var(--accent);width:0;transition:width .2s}
  .wrap{max-width:760px;margin:0 auto;padding:20px}
  .muted{color:var(--mut)} .small{font-size:13px}
  .row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .spacer{flex:1}
  .badge{display:inline-block;padding:2px 9px;border-radius:20px;font-size:12px;font-weight:600;letter-spacing:.02em}
  .badge.floor{background:rgba(240,165,62,.16);color:var(--amber)}
  .badge.contestable{background:rgba(76,141,255,.16);color:var(--blue)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin-top:16px}
  .prompt{font-size:16px;margin:10px 0 16px}
  .opts{list-style:none;margin:0 0 4px;padding:0}
  .opts li{padding:8px 12px;border:1px solid var(--line);border-radius:9px;margin-bottom:6px;color:var(--mut)}
  .opts li.chosen{border-color:var(--green);background:rgba(62,207,142,.10);color:var(--ink);font-weight:600}
  .opts li.chosen::after{content:" ← model's answer";color:var(--green);font-weight:600;font-size:12px}
  .rat{border-left:3px solid var(--accent);background:#12151b;padding:12px 14px;border-radius:0 9px 9px 0;margin:14px 0}
  .q{margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
  .q h4{margin:0 0 10px;font-size:14px;font-weight:600}
  .btns{display:flex;gap:10px}
  button{font:inherit;cursor:pointer;border-radius:9px;border:1px solid var(--line);
         background:#20242d;color:var(--ink);padding:9px 16px;transition:.12s}
  button:hover{border-color:#3a4150}
  button.yes.on{background:rgba(62,207,142,.9);border-color:transparent;color:#08130d;font-weight:700}
  button.no.on{background:rgba(255,107,107,.9);border-color:transparent;color:#1a0808;font-weight:700}
  .nav{display:flex;gap:10px;margin-top:22px;align-items:center}
  .key{display:inline-block;min-width:18px;text-align:center;border:1px solid var(--line);border-radius:5px;
       padding:0 5px;font-size:11px;color:var(--mut);margin-left:6px}
  .primary{background:var(--accent);border-color:transparent;color:#04122e;font-weight:700}
  .ghost{background:transparent}
  details{margin-top:14px}summary{cursor:pointer;color:var(--mut)}
  code{background:#12151b;padding:1px 5px;border-radius:4px}
  .done{text-align:center;padding:40px 0}
</style></head>
<body>
<header>
  <div class="wrap" style="padding:0">
    <div class="row">
      <strong>Democracy Bench — Rationale Coding</strong>
      <span class="spacer"></span>
      <span id="counts" class="small muted"></span>
      <button class="ghost small" onclick="jumpUncoded()">Next uncoded <span class="key">u</span></button>
      <button class="primary small" onclick="exportCSV()">Export CSV <span class="key">e</span></button>
    </div>
    <div class="bar"><div id="fill" class="fill"></div></div>
  </div>
</header>

<div class="wrap">
  <details>
    <summary>Instructions & keys</summary>
    <p class="small muted">You are checking whether the model's <em>forced-choice answer</em> matches the
    <em>reasoning it wrote</em> — a judge-free construct-validity check. For each card:</p>
    <ul class="small muted">
      <li><b>Q1 — Stance matches?</b> Does the rationale argue for the highlighted answer? (If it argues
      the opposite of the option we scored, that's a <b>No</b>.) Keys <span class="key">y</span>/<span class="key">n</span>.</li>
      <li><b>Q2 — Engages the right?</b> (floor items only) Does the rationale actually invoke the right at
      stake — appeal / due process / equal treatment / free expression — rather than a generic or off-point
      reason? Keys <span class="key">f</span>=yes / <span class="key">g</span>=no.</li>
      <li>Navigate <span class="key">←</span>/<span class="key">→</span>. Progress autosaves in this browser.
      When done, <b>Export CSV</b> and run <code>score_rationale_codesheet.py</code>.</li>
    </ul>
  </details>
  <div id="app"></div>
</div>

<script>
const ROWS = __DATA__;
const KEY = "dbench_rationale_codes_v1";
let codes = JSON.parse(localStorage.getItem(KEY) || "{}");
let i = 0;

function save(){ localStorage.setItem(KEY, JSON.stringify(codes)); }
function get(id){ return codes[id] || {}; }
function set(id,f,v){ codes[id]=Object.assign({},codes[id],{[f]:v}); save(); render(); }

function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }

function counts(){
  let sc=0, iv=0, nf=0;
  for(const r of ROWS){ const c=get(r.row_id);
    if(c.stance==='y'||c.stance==='n') sc++;
    if(r.class==='floor'){ nf++; if(c.invokes==='y'||c.invokes==='n') iv++; } }
  return {sc, iv, nf, total:ROWS.length};
}

function render(){
  const c = counts();
  document.getElementById('counts').textContent =
    `stance ${c.sc}/${c.total} · right ${c.iv}/${c.nf}`;
  document.getElementById('fill').style.width = (100*c.sc/c.total)+'%';

  if(i>=ROWS.length){
    document.getElementById('app').innerHTML =
      `<div class="card done"><h3>End of set.</h3>
       <p class="muted">Stance coded ${c.sc}/${c.total}, right coded ${c.iv}/${c.nf}.</p>
       <button class="primary" onclick="exportCSV()">Export CSV</button>
       <button class="ghost" onclick="i=0;render()">Back to start</button></div>`;
    return;
  }
  const r = ROWS[i], cd = get(r.row_id);
  const opts = (r.options||'').split(' | ').map(o=>{
    const idx = o.split(':')[0].trim();
    const chosen = String(idx)===String(r.answer_idx);
    return `<li class="${chosen?'chosen':''}">${esc(o)}</li>`; }).join('');
  const on=(f,v)=> cd[f]===v?'on':'';
  const floor = r.class==='floor';
  document.getElementById('app').innerHTML = `
   <div class="card">
     <div class="row small muted">
       <span class="badge ${r.class}">${r.class}</span>
       <span>${esc(r.item_id)}</span><span>·</span><span>${esc(r.model)}</span>
       <span class="spacer"></span><span>${i+1} / ${ROWS.length}</span>
     </div>
     <div class="prompt">${esc(r.prompt)}</div>
     <ul class="opts">${opts}</ul>
     <div class="rat"><div class="small muted" style="margin-bottom:4px">model's rationale</div>${esc(r.rationale)}</div>

     <div class="q">
       <h4>Q1 · Does the rationale argue for the highlighted answer?</h4>
       <div class="btns">
         <button class="yes ${on('stance','y')}" onclick="set('${r.row_id}','stance','y')">Yes <span class="key">y</span></button>
         <button class="no ${on('stance','n')}" onclick="set('${r.row_id}','stance','n')">No <span class="key">n</span></button>
       </div>
     </div>
     ${floor?`
     <div class="q">
       <h4>Q2 · Does the rationale engage the right at stake?</h4>
       <div class="btns">
         <button class="yes ${on('invokes','y')}" onclick="set('${r.row_id}','invokes','y')">Yes <span class="key">f</span></button>
         <button class="no ${on('invokes','n')}" onclick="set('${r.row_id}','invokes','n')">No <span class="key">g</span></button>
       </div>
     </div>`:``}

     <div class="nav">
       <button onclick="go(-1)">← Prev</button>
       <button class="primary" onclick="go(1)">Next → <span class="key">↵</span></button>
       <span class="spacer"></span>
       <span class="small muted">${cd.stance?'coded':'uncoded'}</span>
     </div>
   </div>`;
}

function go(d){ i=Math.max(0,Math.min(ROWS.length,i+d)); render(); window.scrollTo(0,0); }
function jumpUncoded(){
  for(let k=0;k<ROWS.length;k++){ const r=ROWS[k]; if(!(get(r.row_id).stance)){ i=k; render(); window.scrollTo(0,0); return; } }
  i=ROWS.length; render();
}

function exportCSV(){
  const cols = Object.keys(ROWS[0]).filter(k=>!k.startsWith('_'));
  const q = s => { s=(s==null?'':String(s)); return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s; };
  const lines = [cols.join(',')];
  for(const r of ROWS){ const c=get(r.row_id); const out=Object.assign({},r);
    out.CODE_stance_consistent = c.stance||'';
    out.CODE_invokes_right = r.class==='floor' ? (c.invokes||'') : 'NA';
    lines.push(cols.map(k=>q(out[k])).join(',')); }
  const blob = new Blob([lines.join('\n')],{type:'text/csv'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='rationale_codesheet_coded.csv'; a.click();
}

document.addEventListener('keydown',e=>{
  if(e.target.tagName==='SUMMARY') return;
  const r=ROWS[i]; if(!r && !['e'].includes(e.key)) return;
  if(e.key==='y'&&r) set(r.row_id,'stance','y');
  else if(e.key==='n'&&r) set(r.row_id,'stance','n');
  else if(e.key==='f'&&r&&r.class==='floor') set(r.row_id,'invokes','y');
  else if(e.key==='g'&&r&&r.class==='floor') set(r.row_id,'invokes','n');
  else if(e.key==='ArrowRight'||e.key==='Enter') go(1);
  else if(e.key==='ArrowLeft') go(-1);
  else if(e.key==='u') jumpUncoded();
  else if(e.key==='e') exportCSV();
});
render();
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", default="annotations/rationale_codesheet.csv")
    ap.add_argument("--out", default="annotations/rationale_annotator.html")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.sheet)))
    # keep only fields the UI/export needs; codes are re-derived from localStorage on export
    data = json.dumps(rows, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA__", data)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html)
    n_floor = sum(1 for r in rows if r["class"] == "floor")
    print(f"wrote {args.out}: {len(rows)} cards ({n_floor} floor / {len(rows)-n_floor} contestable)")


if __name__ == "__main__":
    main()
