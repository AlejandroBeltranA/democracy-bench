"""Shared run-metadata block for every output artifact (NEXT_EXPERIMENT_DESIGN "Required Run
Metadata").

Without a record of how an artifact was produced — command, code version, target file, sample
size, temperature — a surprising result cannot be told apart from a prompt artifact, a provider
change, or sample noise. Every driver stamps its report with `run_block(...)` so the artifacts
are self-describing and reproducible.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def code_ref(root: Path | None = None) -> str:
    """Git SHA if this is a checkout, else an explicit no-git marker (this repo ships without git)."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root or ROOT,
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return "no-git"


def display_path(path: Path | str) -> str:
    """A repo-relative path string where possible, for stable, portable artifacts."""
    p = Path(path)
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def run_block(*, command: str | None = None, target_file=None, item_file=None,
              samples: int | None = None, temperature: float | None = 0.8,
              models=None, schema_version: int = 1, extra: dict | None = None) -> dict:
    """Build the top-level `run` block. Only the fields a driver supplies are included, plus the
    always-present generated_at / command / code_ref / schema_version. `extra` merges in any
    driver-specific keys (e.g. shuffle_options, simulated, prompt modes)."""
    block: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": command or " ".join(sys.argv),
        "code_ref": code_ref(),
        "schema_version": schema_version,
    }
    if target_file is not None:
        block["target_file"] = display_path(target_file)
    if item_file is not None:
        block["item_file"] = display_path(item_file)
    if samples is not None:
        block["samples_requested"] = samples
    if temperature is not None:
        block["temperature"] = temperature
    if models is not None:
        block["models"] = models
    if extra:
        block.update(extra)
    return block
