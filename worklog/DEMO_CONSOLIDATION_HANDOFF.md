# Handoff: consolidate the demo to a single canonical file

*Task for a fresh session. Self-contained — you need no prior context. Goal: there should be ONE
demo file, named `index.html`, and the four stale ones removed. Read every step before running.*

## Context

`demo/` currently holds five HTML files. Only one is the real, current demo; the other four are
stale drafts from earlier iterations and cause confusion (people keep opening the wrong one).

- **`demo/whose_values_live.html` — THE CANONICAL FILE. Keep it.** Civic-dark, React + Babel,
  ~46 KB. It opens with an interactive "Ask the panel" explorer (question tabs that redraw a
  bar chart of the British public vs six models), then sections: how it works, a closeness
  leaderboard, the matched-pair rights reflex, steering, the fix, and a closer.
- `demo/whose_values.html` — STALE (old light "blog-post" version, ~40 KB).
- `demo/index.html` — STALE (byte-identical to the old `whose_values.html`).
- `demo/example.html` — STALE (an earlier light example).
- `demo/app.html` — STALE (the original WVS demo).

There may also be a `demo/voice/` folder with `.mp3` files (narration for the demo). **If it exists,
leave it untouched** — the demo references it.

## The task

Make `whose_values_live.html` the canonical `index.html` (so GitHub Pages / any static host serves
it by default) and delete the four stale files.

## Steps

1. **Confirm the canonical file is the right one.** It must contain the interactive explorer. Verify:
   ```bash
   cd /Users/abeltran/Documents/GitHub/democracy-bench
   grep -c "function Explorer\|exp-tab\|Ask the panel\|ReflexMatch" demo/whose_values_live.html
   ```
   Expect a non-zero count (≥3). If it's 0, STOP — you have the wrong file; do not proceed.

2. **Confirm the four others are stale** (none should contain the explorer):
   ```bash
   for f in whose_values.html index.html example.html app.html; do
     echo "$f: $(grep -c 'function Explorer\|exp-tab' demo/$f)"
   done
   ```
   Every line should print `: 0`. If any prints non-zero, STOP and report — a "stale" file isn't stale.

3. **Delete the four stale files:**
   ```bash
   rm demo/whose_values.html demo/index.html demo/example.html demo/app.html
   ```

4. **Rename the canonical file to `index.html`:**
   ```bash
   mv demo/whose_values_live.html demo/index.html
   ```

5. **Verify the result** — `demo/` should now contain exactly one HTML file (`index.html`), plus the
   `voice/` folder if it existed:
   ```bash
   ls demo/
   grep -c "function Explorer" demo/index.html   # expect non-zero
   ```

6. **Smoke-test it renders.** A simple static server, then open the page:
   ```bash
   python3 -m http.server 8088 --directory /Users/abeltran/Documents/GitHub/democracy-bench/demo
   ```
   Open `http://localhost:8088/` (it now serves `index.html` by default). Confirm: the page loads,
   the question tabs at the top switch the bar chart, and there are no console errors. It is a
   React + Babel page, so allow ~1–2 s for it to render after load.

## Update references (light touch)

Some docs mention the old filename. Update any that point at `whose_values_live.html`:
```bash
grep -rl "whose_values_live.html" docs/ README.md 2>/dev/null
```
For each hit, change `whose_values_live.html` → `index.html`. Do NOT touch anything outside `docs/`
and `README.md` for this. The launch config at `.claude/launch.json` serves the `demo/` directory
(not a specific file), so it needs no change — the preview just becomes `…:8088/index.html`.

## Do NOT touch

- `demo/voice/` (narration audio, referenced by the demo).
- Anything under `out/`, `src/`, `data/`, `.env`, or `.claude/` (other than reading).
- The demo's contents/copy — this is a file-consolidation task only, no edits to the HTML body.

## Done when

`demo/` has a single `index.html` (the interactive explorer demo) plus an optional `voice/` folder,
the four stale files are gone, it renders cleanly at `http://localhost:8088/`, and any doc links
point to `index.html`.
