#!/usr/bin/env python3
"""Build the anonymised AAAI supplement archive.

Double-blind: the archive must contain no author name, institution, or repository
URL that identifies the authors. This script scrubs known identifiers and then
FAILS LOUDLY if any remain, so an accidental deanonymisation cannot ship.

Excluded by policy, not by accident:
  * survey microdata (BSA/WVS) -- licence-gated, never redistributed;
  * the 26,400 raw wire envelopes -- 622 MB, and they retain provider response
    headers that have not yet been scrubbed (see STAGE2_PENDING_HANDOFF.md D1).
    The derived records and extraction artifacts they produce ARE included, so
    every number in the paper still regenerates.

Usage:  .venv/bin/python scripts/build_supplement.py
"""
from __future__ import annotations

import io
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ZIP = os.path.join(ROOT, "democracy_bench_aaai27_supplement.zip")
TOP = "submission_supplement"

# Identifiers scrubbed from text files and checked for in the finished archive.
IDENTIFIERS = [
    # personal domain and email first: they are substrings of nothing else
    (re.compile(r"beltranalejandro\.com[^\s)\"']*", re.I), "[URL removed]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]*beltran[A-Za-z0-9.-]*\.[a-z]{2,}", re.I),
     "anonymous@example.org"),
    (re.compile(r"alex\.beltran91@gmail\.com", re.I), "anonymous@example.org"),
    (re.compile(r"github\.com/[A-Za-z0-9._-]+/democracy-bench", re.I),
     "[repository URL removed for anonymous review]"),
    (re.compile(r"AlejandroBeltranA", re.I), "anonymous"),
    (re.compile(r"Alejandro\s+Beltran", re.I), "Anonymous Author"),
    # bare given/family name, no word-boundary requirement on the right so that
    # concatenations like "beltranalejandro" cannot slip through
    (re.compile(r"beltran", re.I), "anonymous"),
    (re.compile(r"alejandro", re.I), "anonymous"),
    # Award/venue provenance is as deanonymising as a name: an overall-winner
    # line naming the organisers is a one-search identification. Strip whole
    # lines that claim a prize or name the hosting organisations.
    (re.compile(r"^.*(overall winner|🏆|won the|winner of).*$", re.I | re.M),
     "[award line removed for anonymous review]"),
    (re.compile(r"i\.AI\s*[x×]\s*ElevenLabs[^\n]*", re.I),
     "[event name removed for anonymous review]"),
    (re.compile(r"AI in Government Hackathon\s*\d{0,4}", re.I),
     "[event name removed for anonymous review]"),
]

# Extensions scrubbed as text. Files with NO extension (LICENSE, CITATION) are
# also treated as text -- a missing extension is exactly how the author name
# survived the first build.
TEXT_EXT = {".md", ".tex", ".bib", ".py", ".json", ".jsonl", ".txt", ".cff",
            ".toml", ".yaml", ".yml", ".sh", ".html", ".cfg", ".ini", ""}

# Internal material that is not a research artifact and carries identifying or
# venue-revealing detail (demo URLs, hackathon results, release logistics).
DOC_DENYLIST = {
    "docs/DEMO_PRESENTER_SCRIPT.md",
    "docs/DEMO_CONSOLIDATION_HANDOFF.md",
    "docs/RELEASE_PLAN.md",
}

INCLUDE_DIRS = ["src", "scripts", "tests", "data", "out", "paper", "gates", "docs"]
INCLUDE_FILES = ["LICENSE", "README.md", "DATA.md", "PLAN.md", "pyproject.toml",
                 "SUPPLEMENT.md"]


def excluded(rel: str) -> bool:
    p = rel.replace(os.sep, "/")
    if "/.git/" in f"/{p}" or p.startswith(".git/"):
        return True
    if "/__pycache__/" in f"/{p}" or p.endswith(".pyc"):
        return True
    if ".venv/" in p or ".pytest_cache/" in p or ".DS_Store" in p:
        return True
    # licence-gated microdata: never redistribute
    if "microdata" in p:
        return True
    # Per-draw stores: raw envelopes are 622 MB and retain unscrubbed provider
    # response headers; the per-draw derived records are hashes and validity
    # flags that carry no information without the raw files they point at. The
    # extraction artifacts these produce (extract_*.json) ARE included, and they
    # hold every estimand reported in the paper.
    for store in ("study", "walk", "study_attempts", "interlock"):
        if re.search(rf"q2_stage2_[^/]+/{store}/", p):
            return True
    # build detritus
    if p.endswith((".aux", ".log", ".blg", ".fls", ".fdb_latexmk", ".out", ".synctex.gz")):
        return True
    if p.endswith(".zip"):
        return True
    # this packaging tool carries the identifier patterns it scrubs; it is not
    # part of the research artifact, so it never ships
    if p.endswith("scripts/build_supplement.py"):
        return True
    if p in DOC_DENYLIST:
        return True
    # vendored tokenizer vocabularies: multi-MB, not research artifacts, and
    # their token lists trip identifier matching
    if "q2_stage2_tokenizers" in p:
        return True
    return False


def scrub(data: bytes, rel: str) -> bytes:
    ext = os.path.splitext(rel)[1].lower()
    if ext not in TEXT_EXT:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    for pat, repl in IDENTIFIERS:
        text = pat.sub(repl, text)
    return text.encode("utf-8")


def collect() -> list[str]:
    files: list[str] = []
    for name in INCLUDE_FILES:
        if os.path.exists(os.path.join(ROOT, name)):
            files.append(name)
    for d in INCLUDE_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for r, dirs, fs in os.walk(base):
            dirs[:] = [x for x in dirs
                       if not excluded(os.path.relpath(os.path.join(r, x), ROOT))]
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), ROOT)
                if not excluded(rel):
                    files.append(rel)
    return sorted(files)


def main() -> int:
    files = collect()
    if not files:
        print("FAIL: nothing collected", file=sys.stderr)
        return 2

    payload: dict[str, bytes] = {}
    for rel in files:
        with open(os.path.join(ROOT, rel), "rb") as fh:
            payload[rel] = scrub(fh.read(), rel)

    # Fail loudly if any identifier survived, in ANY file. Binary files are
    # checked too (decoded leniently) -- a PDF or vocabulary carrying the
    # author's name is still a double-blind violation.
    leaks = []
    for rel, data in payload.items():
        text = data.decode("utf-8", errors="ignore")
        for pat, _ in IDENTIFIERS:
            if pat.search(text):
                leaks.append((rel, pat.pattern))
    if leaks:
        print("FAIL: identifiers survived scrubbing (double-blind violation):",
              file=sys.stderr)
        for rel, pat in leaks[:20]:
            print(f"  {rel}: /{pat}/", file=sys.stderr)
        return 2

    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)
    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel, data in payload.items():
            info = zipfile.ZipInfo(f"{TOP}/{rel.replace(os.sep, '/')}")
            info.date_time = (2026, 1, 1, 0, 0, 0)  # deterministic
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)

    size = os.path.getsize(OUT_ZIP)
    print(f"wrote {OUT_ZIP}")
    print(f"  {len(payload)} files, {size/1e6:.1f} MB compressed")
    if size > 100e6:
        print("  WARNING: >100 MB; check the venue's supplement size limit",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
