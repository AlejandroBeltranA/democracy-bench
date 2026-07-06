#!/usr/bin/env bash
# REP4 cross-family panel driver (Phase 5). Thermal-safe: one model at a time,
# smoke-first per family, >=120s idle cooldown between models. Never overwrites
# out/*.json (evidcond_run errors on an existing --out). Qwen-7B already ran
# (uncommitted); this finishes Mistral / Gemma / Phi.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate

SCRATCH="/private/tmp/claude-504/-Users-abeltran-Documents-GitHub-democracy-bench/a4069ca6-b180-4b49-ad4d-039ef0b2ef97/scratchpad"
COOLDOWN=120

# tag  ->  model id
MODELS=(
  "mistral7b|mlx-community/Mistral-7B-Instruct-v0.3-4bit"
  "phi4mini|mlx-community/Phi-4-mini-instruct-8bit"
  "gemma9b|mlx-community/gemma-2-9b-it-4bit"
)

run () {  # mode tag model extra...
  local mode="$1"; local tag="$2"; local model="$3"; shift 3
  local out="out/evidcond_${mode}_${tag}.json"
  if [[ -f "$out" ]]; then echo "SKIP $out (exists)"; return 0; fi
  echo ">>> [$tag] $mode -> $out"
  python -m alignment.evidcond_run --${mode} --model "$model" --out "$out" "$@" \
    2>&1 | tail -20
  echo "<<< [$tag] $mode done (rc=${PIPESTATUS[0]})"
}

first=1
for entry in "${MODELS[@]}"; do
  tag="${entry%%|*}"; model="${entry#*|}"
  if [[ $first -eq 0 ]]; then echo "=== cooldown ${COOLDOWN}s ==="; sleep "$COOLDOWN"; fi
  first=0
  echo "############ MODEL $tag ($model) ############"

  # smoke-first: a family whose template smokes degenerate is dropped with a note
  echo ">>> [$tag] smoke"
  python -m alignment.evidcond_run --baseline --model "$model" \
    --smoke-out "$SCRATCH/smoke_${tag}.json" 2>&1 | tail -8
  if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
    echo "!!! [$tag] SMOKE FAILED — dropping this model"; continue
  fi

  run baseline "$tag" "$model"
  run tracking "$tag" "$model"
  run floors   "$tag" "$model"
  echo "############ MODEL $tag COMPLETE ############"
done
echo "===== REP4 panel driver finished ====="
