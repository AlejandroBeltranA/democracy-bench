#!/usr/bin/env bash
# One entrypoint: validate data, run tests, run the drivers (+ optional real model via the
# Inspect harness), and rebuild the demo page. Falls back to the labelled SIMULATION when no
# model is given. Usage:  ./scripts/run_all.sh            (simulation)
#                          MODEL=ollama/llama3 ./scripts/run_all.sh   (real model)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .venv/bin/activate ] && source .venv/bin/activate
MODEL="${MODEL:-}"
ARGS=""; [ -n "$MODEL" ] && ARGS="--model $MODEL"

echo "== Gate 1 validation (read-only) =="
python scripts/apply_gate1.py

echo "== tests =="
python -m pytest -q

echo "== drivers ${MODEL:+(model: $MODEL)}${MODEL:-(SIMULATED — set MODEL=ollama/llama3 for a real model)} =="
python src/alignment/loop.py --country USA $ARGS
python src/alignment/loop.py --country GBR $ARGS
python src/alignment/scenario.py $ARGS
python src/alignment/compare_tiers.py $ARGS

echo "== canonical harness (Inspect — policy-delegate axis) =="
case "$MODEL" in
  ollama/*|openrouter/*) inspect eval src/alignment/policy_inspect.py@policy_delegate --model "$MODEL" -T mode=default ;;
  "")       echo "  (skipped — set MODEL=openrouter/... or ollama/... to run a real model)" ;;
  *)        echo "  (skipped — Inspect has no MLX provider; the drivers above measured $MODEL via mlx-lm)" ;;
esac

echo "== build demo =="
python src/alignment/build_demo.py
echo ""
echo "Done. Open demo/app.html in a browser."
