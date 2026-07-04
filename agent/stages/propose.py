#!/usr/bin/env python3
"""
PROPOSE stage stub — generates N=3 candidate variants.
Real impl: param variation first, structural mutation second, foreign import third.
For now: no-op (empty candidate set, shadow will report neutral).
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

OUT = Path("agent/state/candidates.json")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Stub: no candidates until Step 3 lands
    OUT.write_text(json.dumps({"candidates": [], "tournament_size": 3, "mode": "stub"}, indent=2))
    print("[propose] 0 candidates (stub — Step 3 unimplemented)")
    return 0


if __name__ == "__main__":
    sys.exit(main())