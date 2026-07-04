#!/usr/bin/env python3
"""
PROMOTE stage stub — atomic swap + incumbent.bak rollback.
Real impl: only promotes when shadow beats incumbent + no regressions.
For now: no-op (no candidates to promote in stub mode).
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

IN = Path("agent/state/shadow_scores.json")
OUT = Path("agent/state/promotion_log.json")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scores = json.loads(IN.read_text()) if IN.exists() else {}
    n_candidates = len(scores.get("candidates", []))
    promoted = []
    OUT.write_text(json.dumps({"promoted": promoted, "n_candidates_evaluated": n_candidates}, indent=2))
    print(f"[promote] 0 promoted (stub — {n_candidates} candidates evaluated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())