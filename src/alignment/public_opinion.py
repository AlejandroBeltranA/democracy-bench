"""Extraction and analysis for England-vs-Scotland public-opinion targets.

The raw UK Data Service downloads are zipped tab-delimited files with RTF data dictionaries.
This module reads them in place, applies a small reviewed config, and writes reproducible
weighted distributions plus England/Scotland comparisons for the policy-drift demo.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "data" / "public_opinion_extraction.json"
OUT = ROOT / "out" / "public_opinion"
HEADLINE_MIN_N = 300
DIRECTIONAL_MIN_N = 100


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text())
    cfg["_config_path"] = str(path)
    return cfg


def missing_source_files(config: dict[str, Any] | None = None) -> list[Path]:
    cfg = config or load_config()
    paths = []
    for ds in cfg["datasets"].values():
        p = ROOT / ds["zip"]
        if not p.exists():
            paths.append(p)
    return paths


def build_dataset_inventory(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return dataset-level metadata, headers, dictionary labels, and configured variables."""
    cfg = config or load_config()
    inventory: dict[str, Any] = {"datasets": {}}
    for ds_id, ds in cfg["datasets"].items():
        zip_path = ROOT / ds["zip"]
        with zipfile.ZipFile(zip_path) as zf:
            header = _tab_header(zf, ds["tab"])
            var_meta = _dictionary_metadata(zf)
        configured_vars = sorted({
            var
            for item in cfg["items"]
            for d_id, var in item.get("datasets", {}).items()
            if d_id == ds_id
        })
        inventory["datasets"][ds_id] = {
            "polity": ds["polity"],
            "label": ds["label"],
            "programme": ds["programme"],
            "study": ds["study"],
            "year": ds["year"],
            "zip": ds["zip"],
            "tab": ds["tab"],
            "weight": ds["weight"],
            "filters": ds.get("filters", []),
            "n_columns": len(header),
            "configured_vars": configured_vars,
            "configured_var_labels": {
                var: var_meta.get(var, {}).get("label") for var in configured_vars
            },
            "missing_configured_vars": [
                var for var in configured_vars + [ds["weight"]]
                if var not in header
            ],
        }
    return inventory


def extract_targets(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    metadata_by_dataset = _load_all_dataset_metadata(cfg)
    data_by_dataset = _load_all_configured_columns(cfg)

    items: dict[str, Any] = {}
    for item in cfg["items"]:
        series = []
        for ds_id, var in item["datasets"].items():
            ds = cfg["datasets"][ds_id]
            rows = data_by_dataset[ds_id]
            var_meta = metadata_by_dataset[ds_id].get(var, {})
            valid_codes = [float(c) for c in item["valid_codes"]]
            dist = _weighted_distribution(rows, var, ds["weight"], valid_codes)
            labels = [
                var_meta.get("value_labels", {}).get(str(_int_if_whole(c)), str(_int_if_whole(c)))
                for c in valid_codes
            ]
            series.append({
                "dataset_id": ds_id,
                "polity": ds["polity"],
                "label": ds["label"],
                "programme": ds["programme"],
                "study": ds["study"],
                "year": ds["year"],
                "variable": var,
                "variable_label": var_meta.get("label"),
                "weight": ds["weight"],
                "filters": ds.get("filters", []),
                "valid_codes": [_int_if_whole(c) for c in valid_codes],
                "labels": labels,
                **dist,
            })
        items[item["id"]] = {
            "domain": item["domain"],
            "class": item["class"],
            "title": item["title"],
            "question": item["question"],
            "series": series,
            "comparisons": _comparisons(series),
        }

    return {
        "generated_at": date.today().isoformat(),
        "title": cfg.get("title", "Public Opinion: England vs Scotland"),
        "source_config": _display_path(Path(cfg.get("_config_path", CONFIG))),
        "status": "microdata_built",
        "base_size_thresholds": {
            "headline_min_unweighted_n": HEADLINE_MIN_N,
            "directional_min_unweighted_n": DIRECTIONAL_MIN_N,
        },
        "note": cfg.get("dashboard_note", (
            "England targets are BSA respondents filtered by GOR; Scotland targets are SSA. "
            "Comparisons are informative but not a single harmonised survey design."
        )),
        "items": items,
        "warnings": _target_warnings(items),
    }


def write_outputs(targets: dict[str, Any], inventory: dict[str, Any] | None = None,
                  out_dir: Path = OUT) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    inventory = inventory or build_dataset_inventory()
    target_path = out_dir / "targets.json"
    inventory_path = out_dir / "inventory.json"
    html_path = out_dir / "index.html"
    target_path.write_text(json.dumps(targets, indent=2))
    inventory_path.write_text(json.dumps(inventory, indent=2))
    html_path.write_text(render_dashboard(targets))
    return {"targets": target_path, "inventory": inventory_path, "html": html_path}


def render_dashboard(targets: dict[str, Any]) -> str:
    rows = []
    title = targets.get("title", "Public Opinion")
    note = targets.get("note", "")
    for item_id, item in targets["items"].items():
        rows.append(f"<section><h2>{html.escape(item['title'])}</h2>")
        rows.append(f"<p>{html.escape(item['question'])}</p>")
        rows.append("<div class='series'>")
        for s in item["series"]:
            rows.append(_series_card(item_id, s))
        rows.append("</div>")
        if item["comparisons"]:
            rows.append("<h3>Comparisons</h3><table><thead><tr>"
                        "<th>Pair</th><th>Year</th><th>TV distance</th><th>Mean-position gap</th>"
                        "</tr></thead><tbody>")
            for c in item["comparisons"]:
                pair = c.get("pair", f"{c.get('left')} vs {c.get('right')}")
                rows.append("<tr>"
                            f"<td>{html.escape(pair)}</td>"
                            f"<td>{c['year']}</td>"
                            f"<td>{c['total_variation']:.3f}</td>"
                            f"<td>{c['mean_position_gap']:+.3f}</td>"
                            "</tr>")
            rows.append("</tbody></table>")
        rows.append("</section>")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{ --bg:#f7f7f5; --ink:#1e2328; --mut:#68717a; --line:#cfd4d9;
           --eng:#2f6f9f; --sco:#5c7d3b; --wls:#8b5e9f; --card:#fff; }}
  body {{ margin:0; padding:28px; font:14px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;
          background:var(--bg); color:var(--ink); }}
  h1 {{ font-size:24px; margin:0 0 4px; }}
  h2 {{ font-size:18px; margin:0 0 4px; }}
  h3 {{ font-size:14px; margin:14px 0 6px; color:var(--mut); }}
  p {{ margin:0 0 12px; color:var(--mut); max-width:900px; }}
  section {{ border-top:1px solid var(--line); padding-top:18px; margin-top:22px; }}
  .series {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:10px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px; }}
  .meta {{ display:flex; justify-content:space-between; gap:8px; font-size:12px; color:var(--mut); margin-bottom:8px; }}
  .bar {{ display:flex; height:24px; overflow:hidden; border-radius:4px; border:1px solid var(--line); }}
  .seg {{ height:100%; }}
  .labels {{ margin-top:7px; display:grid; gap:3px; }}
  .lab {{ display:grid; grid-template-columns:34px 1fr 48px; gap:6px; align-items:start; font-size:12px; }}
  .sw {{ width:20px; height:10px; border-radius:2px; margin-top:3px; }}
  .warn {{ color:#9a5b00; font-size:12px; margin-top:6px; }}
  table {{ border-collapse:collapse; font-size:13px; min-width:360px; }}
  th, td {{ border:1px solid var(--line); padding:5px 8px; text-align:left; }}
  th {{ background:#ecefed; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>{html.escape(note)}</p>
{''.join(rows)}
</body>
</html>"""


def _series_card(item_id: str, s: dict[str, Any]) -> str:
    palette = _palette(s["polity"].lower(), len(s["distribution"]))
    segments = []
    labels = []
    for i, (p, label) in enumerate(zip(s["distribution"], s["labels"])):
        color = palette[i]
        segments.append(f"<div class='seg' title='{html.escape(label)}: {p:.1%}' "
                        f"style='width:{p*100:.3f}%;background:{color}'></div>")
        labels.append("<div class='lab'>"
                      f"<span class='sw' style='background:{color}'></span>"
                      f"<span>{html.escape(label)}</span>"
                      f"<span>{p:.1%}</span>"
                      "</div>")
    return ("<div class='card'>"
            f"<div class='meta'><b>{html.escape(s['label'])} {s['year']}</b>"
            f"<span>{html.escape(s['programme'])} · n={s['n_unweighted']} · wt={s['n_weighted']:.0f}</span></div>"
            f"<div class='bar'>{''.join(segments)}</div>"
            f"<div class='labels'>{''.join(labels)}</div>"
            f"{_series_warning_html(s)}"
            "</div>")


def _palette(kind: str, n: int) -> list[str]:
    base = {
        "eng": ["#d9e9f3", "#9ecae1", "#4f93bd", "#1f638e", "#0e3f5f"],
        "sco": ["#e3ead7", "#bdcf9a", "#87a95f", "#5d7f36", "#35541f"],
        "wls": ["#eadff0", "#c9a7d8", "#a173b5", "#76458e", "#4f2762"],
    }.get(kind, ["#eeeeee", "#c8c8c8", "#999999", "#696969", "#3f3f3f"])
    return base[:n] if n <= len(base) else base + [base[-1]] * (n - len(base))


def _load_all_dataset_metadata(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {}
    for ds_id, ds in cfg["datasets"].items():
        with zipfile.ZipFile(ROOT / ds["zip"]) as zf:
            out[ds_id] = _dictionary_metadata(zf)
    return out


def _load_all_configured_columns(cfg: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    out = {}
    needed_by_dataset: dict[str, set[str]] = defaultdict(set)
    for ds_id, ds in cfg["datasets"].items():
        needed_by_dataset[ds_id].add(ds["weight"])
        for flt in ds.get("filters", []):
            needed_by_dataset[ds_id].add(flt["var"])
    for item in cfg["items"]:
        for ds_id, var in item.get("datasets", {}).items():
            needed_by_dataset[ds_id].add(var)

    for ds_id, ds in cfg["datasets"].items():
        with zipfile.ZipFile(ROOT / ds["zip"]) as zf:
            rows = _read_tab_rows(zf, ds["tab"], needed_by_dataset[ds_id])
        rows = [row for row in rows if _passes_filters(row, ds.get("filters", []))]
        out[ds_id] = rows
    return out


def _read_tab_rows(zf: zipfile.ZipFile, tab_name: str, columns: set[str]) -> list[dict[str, str]]:
    with zf.open(tab_name) as f:
        text = io.TextIOWrapper(f, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        rows = []
        for row in reader:
            rows.append({c: row.get(c, "") for c in columns})
        return rows


def _tab_header(zf: zipfile.ZipFile, tab_name: str) -> list[str]:
    with zf.open(tab_name) as f:
        return f.readline().decode("utf-8", errors="replace").strip().split("\t")


def _dictionary_metadata(zf: zipfile.ZipFile) -> dict[str, Any]:
    dd_name = next((n for n in zf.namelist() if n.endswith("ukda_data_dictionaries.zip")), None)
    if not dd_name:
        return {}
    merged: dict[str, Any] = {}
    with zipfile.ZipFile(io.BytesIO(zf.read(dd_name))) as dd:
        for rtf_name in (n for n in dd.namelist() if n.endswith(".rtf")):
            text = _rtf_to_text(dd.read(rtf_name).decode("latin-1", errors="replace"))
            merged.update(_parse_dictionary_text(text))
    return merged


def _rtf_to_text(rtf: str) -> str:
    text = rtf.replace("\\par", "\n").replace("\\tab", "\t")
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text


def _parse_dictionary_text(text: str) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    chunks = re.split(r"\bPos\. =", text)
    for chunk in chunks:
        vm = re.search(r"\bVariable =\s+([A-Za-z0-9_]+)\s+Variable label =\s+(.*?)\s+This variable is", chunk, re.S)
        if not vm:
            continue
        var = vm.group(1)
        label = _clean_ws(vm.group(2))
        values: dict[str, str] = {}
        for val, lab in re.findall(r"Value =\s+(-?\d+(?:\.\d+)?)\s+Label =\s+(.*?)(?=\s+Value =|\s*$)", chunk, re.S):
            values[str(_int_if_whole(float(val)))] = _clean_ws(lab)
        meta[var] = {"label": label, "value_labels": values}
    return meta


def _passes_filters(row: dict[str, str], filters: list[dict[str, Any]]) -> bool:
    for flt in filters:
        value = _number(row.get(flt["var"]))
        if value is None:
            return False
        if "include_codes" in flt and int(value) not in set(flt["include_codes"]):
            return False
        if "exclude_codes" in flt and int(value) in set(flt["exclude_codes"]):
            return False
    return True


def _weighted_distribution(rows: list[dict[str, str]], var: str, weight: str,
                           valid_codes: list[float]) -> dict[str, Any]:
    counts = {c: 0.0 for c in valid_codes}
    n_unweighted = 0
    for row in rows:
        code = _number(row.get(var))
        if code not in counts:
            continue
        wt = _number(row.get(weight))
        if wt is None or wt <= 0:
            continue
        counts[code] += wt
        n_unweighted += 1
    total = sum(counts.values())
    dist = [counts[c] / total if total else 0.0 for c in valid_codes]
    quality, warning = _base_quality(n_unweighted)
    return {
        "n_unweighted": n_unweighted,
        "n_weighted": total,
        "weighted_counts": {str(_int_if_whole(c)): counts[c] for c in valid_codes},
        "distribution": dist,
        "usable": total > 0,
        "base_quality": quality,
        "base_warning": warning,
    }


def _comparisons(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_year: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for s in series:
        by_year[int(s["year"])][s["polity"]] = s
    out = []
    for year, polities in sorted(by_year.items()):
        polity_ids = sorted(polities)
        for i, left_id in enumerate(polity_ids):
            for right_id in polity_ids[i + 1:]:
                left = polities[left_id]
                right = polities[right_id]
                if not left.get("usable", True) or not right.get("usable", True):
                    continue
                left_dist = left["distribution"]
                right_dist = right["distribution"]
                if len(left_dist) != len(right_dist):
                    continue
                min_n = min(left["n_unweighted"], right["n_unweighted"])
                quality, warning = _base_quality(min_n)
                out.append({
                    "year": year,
                    "pair": f"{left['label']} vs {right['label']}",
                    "left_polity": left_id,
                    "right_polity": right_id,
                    "left": left["dataset_id"],
                    "right": right["dataset_id"],
                    "total_variation": _tv(left_dist, right_dist),
                    "mean_position_gap": _mean_position(right_dist) - _mean_position(left_dist),
                    "min_n_unweighted": min_n,
                    "base_quality": quality,
                    "base_warning": warning,
                })
    return out


def _base_quality(n_unweighted: int) -> tuple[str, str | None]:
    if n_unweighted <= 0:
        return "no_valid_responses", "No valid substantive responses; exclude from comparisons."
    if n_unweighted < DIRECTIONAL_MIN_N:
        return "too_low", f"n={n_unweighted} is below {DIRECTIONAL_MIN_N}; do not use for model ranking or headline claims."
    if n_unweighted < HEADLINE_MIN_N:
        return "directional", f"n={n_unweighted} is below {HEADLINE_MIN_N}; read as directional only."
    return "headline_ok", None


def _target_warnings(items: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = []
    for item_id, item in items.items():
        for s in item["series"]:
            if s.get("base_warning"):
                warnings.append({
                    "type": "base_size",
                    "item": item_id,
                    "dataset_id": s["dataset_id"],
                    "polity": s["polity"],
                    "year": s["year"],
                    "n_unweighted": s["n_unweighted"],
                    "base_quality": s["base_quality"],
                    "message": s["base_warning"],
                })
        for c in item["comparisons"]:
            if c.get("base_warning"):
                warnings.append({
                    "type": "comparison_base_size",
                    "item": item_id,
                    "pair": c["pair"],
                    "year": c["year"],
                    "min_n_unweighted": c["min_n_unweighted"],
                    "base_quality": c["base_quality"],
                    "message": c["base_warning"],
                })
    return warnings


def _series_warning_html(s: dict[str, Any]) -> str:
    warning = s.get("base_warning")
    return f"<div class='warn'>{html.escape(warning)}</div>" if warning else ""


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _tv(a: list[float], b: list[float]) -> float:
    return 0.5 * sum(abs(x - y) for x, y in zip(a, b))


def _mean_position(dist: list[float]) -> float:
    return sum(i * p for i, p in enumerate(dist))


def _number(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int_if_whole(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
