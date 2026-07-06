#!/usr/bin/env bash
# REP4 extension: re-download gemma-2-9b (broken cache), then score gemma + mistral-nemo.
# Smoke-first per family; never overwrites out/*.json (evidcond_run errors on existing --out).
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate

SCRATCH="/private/tmp/claude-504/-Users-abeltran-Documents-GitHub-democracy-bench/a4069ca6-b180-4b49-ad4d-039ef0b2ef97/scratchpad"

echo "############ STEP 0: (re)download gemma-2-9b ############"
python - <<'PY'
from huggingface_hub import snapshot_download
p = snapshot_download("mlx-community/gemma-2-9b-it-4bit")
print("gemma-2-9b snapshot at:", p)
PY
echo "download rc=$?"

MODELS=(
  "gemma9b|mlx-community/gemma-2-9b-it-4bit"
  "mistralnemo|mlx-community/Mistral-Nemo-Instruct-2407-4bit"
)

run () {  # mode tag model
  local mode="$1"; local tag="$2"; local model="$3"
  local out="out/evidcond_${mode}_${tag}.json"
  if [[ -f "$out" ]]; then echo "SKIP $out (exists)"; return 0; fi
  echo ">>> [$tag] $mode -> $out"
  python -m alignment.evidcond_run --${mode} --model "$model" --out "$out" 2>&1 | tail -14
  echo "<<< [$tag] $mode done (rc=${PIPESTATUS[0]})"
}

for entry in "${MODELS[@]}"; do
  tag="${entry%%|*}"; model="${entry#*|}"
  echo "############ MODEL $tag ($model) ############"
  echo ">>> [$tag] smoke"
  python -m alignment.evidcond_run --baseline --model "$model" \
    --smoke-out "$SCRATCH/smoke_${tag}.json" 2>&1 | tail -10
  if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    echo "!!! [$tag] SMOKE FAILED — dropping this model"; continue
  fi
  run baseline "$tag" "$model"
  run tracking "$tag" "$model"
  run floors   "$tag" "$model"
  echo "############ MODEL $tag COMPLETE ############"
done
echo "===== REP4 extra driver finished ====="
