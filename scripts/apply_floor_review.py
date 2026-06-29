"""Apply a floor-review sign-off (from gates/floor_review.html) to the floor probes.

Reads data/floor_review_signoff.json and stamps each floor item in data/policy_items.jsonl with
the reviewer's verdict: accepted directions are marked reviewed (the `needs_review` flag is
cleared); flagged directions keep `needs_review` and gain the reviewer's note. Non-floor lines are
left byte-for-byte unchanged. Run: python scripts/apply_floor_review.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "policy_items.jsonl"
SIGNOFF = ROOT / "data" / "floor_review_signoff.json"


def main(signoff_path: Path = SIGNOFF) -> None:
    signoff = json.loads(signoff_path.read_text())
    reviewer = signoff["reviewer"]
    date = signoff["generated_at"][:10]          # YYYY-MM-DD
    review = signoff["review"]
    verdicts = {it["id"]: it for it in signoff["items"]}

    out_lines = []
    changed = 0
    for raw in ITEMS.read_text().splitlines():
        if not raw.strip():
            out_lines.append(raw)
            continue
        item = json.loads(raw)
        if item.get("class") != "floor" or item["id"] not in verdicts:
            out_lines.append(raw)                # leave contestable / unreviewed lines verbatim
            continue
        v = verdicts[item["id"]]
        item.pop("needs_review", None)
        item["reviewed_by"] = reviewer
        item["review_date"] = date
        item["review"] = review
        if v["verdict"] == "accept":
            item["reviewed"] = True
        else:
            item["reviewed"] = False
            item["needs_review"] = True
            item["review_note"] = v.get("note") or "flagged by reviewer; direction not confirmed"
        out_lines.append(json.dumps(item, ensure_ascii=False))
        changed += 1

    ITEMS.write_text("\n".join(out_lines) + "\n")
    accepted = sum(1 for v in verdicts.values() if v["verdict"] == "accept")
    flagged = sum(1 for v in verdicts.values() if v["verdict"] == "flag")
    print(f"applied {review} by {reviewer} ({date}): {changed} floor items stamped "
          f"({accepted} accepted, {flagged} flagged)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else SIGNOFF)
