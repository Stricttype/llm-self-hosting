#!/usr/bin/env python3
"""
SHADOW stage — runs shadow runner against any candidates + reports incumbent baseline.
Real impl: per-candidate shadow_run, incumbent snapshot, regression check.
For now: score incumbent only (no candidates from PROPOSE yet).
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

OUT = Path("agent/state/shadow_scores.json")
SHADOW = Path("tests/shadow_run.py")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(SHADOW), "--incumbent"],
        capture_output=True, text=True, timeout=30,
    )
    incumbent_score = result.stdout.strip().split("\n")[0] if result.stdout else "shadow: unknown"
    scores = {
        "incumbent": incumbent_score,
        "candidates": [],
        "rc": result.returncode,
    }
    OUT.write_text(json.dumps(scores, indent=2))
    print(f"[shadow] incumbent: {incumbent_score}")
    return 0


if __name__ == "__main__":
    sys.exit(main())