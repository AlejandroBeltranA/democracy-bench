#!/usr/bin/env python3
"""Verify docs/REPRODUCTION.md against the artifacts' own run blocks.

For every fenced command block in docs/REPRODUCTION.md that this script can bind
to an artifact, it asserts the quoted command string byte-matches that artifact's
run-block ``command`` field. Artifacts with no run-block ``command`` (the three
Phase-1 logit-bias JSONs, the uncommitted superseded steering curve, the mlx_lm
lora training call, the extractor, the figures) are reported as ``asserted-by-doc``
and NOT compared against a JSON — the doc is the authority there.

Reads files only. Fails loudly (nonzero exit) on any mismatch or missing artifact.

    python scripts/verify_repro_reference.py
"""
from __future__ import annotations

import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "out")
DOC_PATH = os.path.join(REPO_ROOT, "docs", "REPRODUCTION.md")

# Which artifact each documented command must match. A None value marks an entry
# that the doc asserts (no run-block command exists to check against).
# The order here is also the order the command must appear in the doc's fenced
# blocks, so a mis-ordered/duplicated command surfaces as a mismatch.
EXPECTED = [
    # (label, artifact-basename-or-None, expected command string)
    ("phase1-sweep", None,
     "python -m alignment.logit_bias_calibration --sweep"),
    ("phase1-logprobs-4opt", None,
     "python -m alignment.logit_bias_calibration --elicit openai/gpt-4o-mini "
     "--n-options 4 --n-orders 4 --out "
     "out/logit_bias_calibration_logprobs_gpt4omini_4opt.json"),
    ("phase1-logprobs-5opt", None,
     "python -m alignment.logit_bias_calibration --elicit openai/gpt-4o-mini "
     "--n-options 5 --n-orders 4 --out "
     "out/logit_bias_calibration_logprobs_gpt4omini_5opt.json"),
    ("p2-r1-holdout", "act_steer_holdout_3b.json",
     "python -m alignment.activation_steering_run --holdout"),
    ("p2-r1-holdout-late", "act_steer_holdout_late_3b.json",
     "python -m alignment.activation_steering_run --holdout"),
    ("p2-r4-ci", "act_steer_ci_3b.json",
     "python -m alignment.activation_steering_run --ci"),
    ("p2-r2-randctrl", "act_steer_randctrl_3b.json",
     "python -m alignment.activation_steering_run --direction random"),
    ("p2-r3-negalpha", "act_steer_negalpha_3b.json",
     "python -m alignment.activation_steering_run --negdose"),
    ("p2-w3-geometry", "act_steer_geometry_3b.json",
     "python -m alignment.activation_steering_run --geometry"),
    ("p2-r7-offtask", "act_steer_offtask_3b.json",
     "python -m alignment.activation_steering_run --offtask"),
    ("p2-r8-personactrl", "act_steer_personactrl_3b.json",
     "python -m alignment.activation_steering_run --persona-control"),
    ("p2-superseded", None,
     "python -m alignment.activation_steering_run"),
    ("p0-w1-cosine", "act_steer_w1_cosine_3b.json",
     "python -m alignment.activation_steering_run --w1-cosine"),
    ("p2-baseline", "evidcond_baseline_3b.json",
     "python -m alignment.evidcond_run --baseline"),
    ("p3-tracking", "evidcond_tracking_3b.json",
     "python -m alignment.evidcond_run --tracking"),
    ("p4-floors", "evidcond_floors_3b.json",
     "python -m alignment.evidcond_run --floors"),
    ("p5a-lora-build", "lora_deference_design.json",
     "python -m alignment.evidcond_run --lora-build"),
    ("p5a-lora-train", None,
     "mlx_lm.lora --model mlx-community/Llama-3.2-3B-Instruct-4bit --train "
     "--data out/lora_deference_data --fine-tune-type lora --num-layers 8 "
     "--batch-size 4 --iters 500 --learning-rate 1e-4 --mask-prompt "
     "--max-seq-length 384 --seed 0 --adapter-path out/lora_deference_adapter "
     "--save-every 250"),
    ("p5b-lora-eval", "evidcond_lora_eval_3b.json",
     "python -m alignment.evidcond_run --lora-eval"),
    ("g1-guard-grid", "floorguard_grid_3b.json",
     "python -m alignment.evidcond_run --guard-grid"),
    ("extractor", None,
     "python scripts/extract_paper_results.py --out out/paper_results_extract.json"),
    ("figures", None,
     "python scripts/make_paper_figures.py"),
    # Phase 5 — 8B replication. These reuse the P2/P3/P4/G1 runners with a
    # --model override; the run-block `command` is the runner's canonical string
    # (NO --model echo), so it byte-matches the same command as the 3B run and is
    # run-block-verified. The --model flag is documented in prose in the doc.
    ("rep-p2-baseline-8b", "evidcond_baseline_8b.json",
     "python -m alignment.evidcond_run --baseline"),
    ("rep-p3-tracking-8b", "evidcond_tracking_8b.json",
     "python -m alignment.evidcond_run --tracking"),
    ("rep-p4-floors-8b", "evidcond_floors_8b.json",
     "python -m alignment.evidcond_run --floors"),
    ("rep-g1-guard-grid-8b", "floorguard_grid_8b.json",
     "python -m alignment.evidcond_run --guard-grid"),
    # Frontier crack — P4 floors on gpt-4o-mini via the OpenRouter logprob backend.
    # Same runner as the 3B/8B floors; the run-block `command` is the canonical
    # `--floors` string (the `--model openrouter/openai/gpt-4o-mini` override is
    # prose-documented, not echoed), so the command byte-matches. This is an API run:
    # the run-block COMMAND is verified here, but the artifact NUMBERS are not
    # byte-reproducible (hosted, unpinned model — see Known irreproducibilities #7).
    ("frontier-crack-gpt4omini", "evidcond_floors_gpt4omini.json",
     "python -m alignment.evidcond_run --floors"),
]


# ---- pure parsing / matching helpers (unit-tested; no I/O) -----------------

_FENCE_RE = re.compile(r"^```(\w*)\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def parse_fenced_commands(markdown):
    """Return the list of one-line command strings from fenced blocks in order.

    Only blocks whose single stripped line begins with ``python`` or ``mlx_lm``
    are treated as reproduction commands (skips the ``source .venv`` env block
    and the multi-line dependency ASCII diagram).
    """
    cmds = []
    for _lang, body in _FENCE_RE.findall(markdown):
        lines = [ln for ln in body.splitlines() if ln.strip()]
        if len(lines) != 1:
            continue
        line = lines[0].strip()
        if line.startswith("python ") or line.startswith("mlx_lm"):
            cmds.append(line)
    return cmds


def normalise_command(cmd):
    """Collapse internal whitespace so wrapping in the doc source is ignored."""
    return " ".join(cmd.split())


def match_commands(doc_cmds, expected):
    """Match documented commands (in order) to the EXPECTED table.

    Returns (matches, errors). ``matches`` is a list of
    (label, artifact, command, verified_bool). ``errors`` is a list of
    human-readable mismatch strings. Pure: takes the expected command strings,
    does not read the doc file or the JSONs.
    """
    matches, errors = [], []
    exp_norm = [(lbl, art, normalise_command(c)) for lbl, art, c in expected]
    doc_norm = [normalise_command(c) for c in doc_cmds]

    if len(doc_norm) != len(exp_norm):
        errors.append(
            "command COUNT mismatch: doc has %d fenced commands, expected %d"
            % (len(doc_norm), len(exp_norm))
        )
    for i, (lbl, art, exp_cmd) in enumerate(exp_norm):
        doc_cmd = doc_norm[i] if i < len(doc_norm) else None
        if doc_cmd != exp_cmd:
            errors.append(
                "[%s] doc/expected mismatch:\n    doc      = %r\n    expected = %r"
                % (lbl, doc_cmd, exp_cmd)
            )
        matches.append((lbl, art, exp_cmd, art is not None))
    return matches, errors


def compare_to_runblock(command, run_block):
    """True iff the run block's ``command`` equals ``command`` (normalised)."""
    got = run_block.get("command")
    if got is None:
        return False, "run block has no 'command' field"
    if normalise_command(got) != normalise_command(command):
        return False, "run-block command = %r" % (got,)
    return True, None


# ---- I/O driver ------------------------------------------------------------

def _load_run_block(basename):
    path = os.path.join(OUT_DIR, basename)
    if not os.path.exists(path):
        raise FileNotFoundError("missing artifact: out/%s" % basename)
    with open(path) as fh:
        return json.load(fh).get("run")


def main(argv=None):
    with open(DOC_PATH) as fh:
        doc = fh.read()
    doc_cmds = parse_fenced_commands(doc)
    matches, errors = match_commands(doc_cmds, EXPECTED)

    verified, asserted = [], []
    for lbl, art, cmd, has_art in matches:
        if not has_art:
            asserted.append(lbl)
            continue
        try:
            rb = _load_run_block(art)
        except FileNotFoundError as exc:
            errors.append("[%s] %s" % (lbl, exc))
            continue
        if rb is None:
            errors.append("[%s] out/%s has no 'run' block" % (lbl, art))
            continue
        ok, why = compare_to_runblock(cmd, rb)
        if ok:
            verified.append(lbl)
        else:
            errors.append(
                "[%s] out/%s run-block MISMATCH:\n    doc = %r\n    %s"
                % (lbl, art, cmd, why)
            )

    print("Reproduction reference verification")
    print("  fenced commands parsed : %d" % len(doc_cmds))
    print("  run-block-verified     : %d  (%s)"
          % (len(verified), ", ".join(verified)))
    print("  asserted-by-doc        : %d  (%s)"
          % (len(asserted), ", ".join(asserted)))
    if errors:
        print("\nFAIL — %d problem(s):" % len(errors))
        for e in errors:
            print("  - " + e)
        return 1
    print("\nOK — every run-block command matches the doc; %d asserted-by-doc entries."
          % len(asserted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
