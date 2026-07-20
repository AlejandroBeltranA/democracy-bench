#!/usr/bin/env bash
# One entrypoint: run tests, run the Policy Delegate Stress Test (simulated by default,
# real via MODEL=...), and point at the deployed demo. The legacy WVS layer runs only
# with LEGACY_WVS=1.
#
# Usage:
#   ./scripts/run_all.sh                                        # simulation, no keys needed
#   MODEL=openrouter/openai/gpt-4o-mini ./scripts/run_all.sh    # real model (needs .env key)
#   MODEL=ollama/llama3 ./scripts/run_all.sh                    # real local model
#   LEGACY_WVS=1 ./scripts/run_all.sh                           # also run the WVS layer
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .venv/bin/activate ] && source .venv/bin/activate
MODEL="${MODEL:-}"

echo "== tests =="
python -m pytest -q

echo "== Policy Delegate Stress Test ${MODEL:+(model: $MODEL)}${MODEL:-(SIMULATED — set MODEL=... for a real model)} =="
if [ -n "$MODEL" ]; then
  python -m alignment.policy_delegate_stress --models "$MODEL" --out out/_stress_run.json
else
  python -m alignment.policy_delegate_stress --out out/_stress_sim.json
fi

echo "== canonical harness (Inspect) =="
case "$MODEL" in
  ollama/*|openrouter/*) inspect eval src/alignment/policy_inspect.py@policy_delegate --model "$MODEL" -T mode=default ;;
  "")       echo "  (skipped — set MODEL=openrouter/... or ollama/... to run a real model)" ;;
  *)        echo "  (skipped — Inspect has no MLX provider; the stress driver above measured $MODEL via mlx-lm)" ;;
esac

if [ -n "${LEGACY_WVS:-}" ]; then
  echo "== LEGACY WVS layer =="
  python scripts/apply_gate1.py
  ARGS=""; [ -n "$MODEL" ] && ARGS="--model $MODEL"
  python src/alignment/loop.py --country USA $ARGS
  python src/alignment/loop.py --country GBR $ARGS
  python src/alignment/scenario.py $ARGS
  python src/alignment/compare_tiers.py $ARGS
  python src/alignment/build_demo.py
  echo "Legacy WVS demo rebuilt: demo/app.html"
fi

echo ""
echo "Done. Deployed demo: demo/whose_values_live.html"
