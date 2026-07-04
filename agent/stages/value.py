#!/usr/bin/env python3
"""
VALUE stage stub — VoI gate (read-only per Claude v2 review).
Real impl: novelty_deadband(HNSW-NN) × outcome_proxy / shadow_cost.
For now: pass-through all harvested events, log what would be kept vs dropped.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

IN = Path("agent/state/harvested_events.json")
OUT = Path("agent/state/value_decisions.json")


def main() -> int:
    data = json.loads(IN.read_text()) if IN.exists() else {"events": []}
    events = data.get("events", [])
    # Stub: keep everything, log drop rate (will be high in real impl)
    decisions = [
        {"event_id": i, "decision": "keep", "voi_score": 1.0, "reason": "stub: read-only mode"}
        for i in range(len(events))
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"kept": len(decisions), "dropped": 0, "decisions": decisions}, indent=2))
    print(f"[value] {len(decisions)} kept / 0 dropped (read-only stub)")
    return 0


if __name__ == "__main__":
    sys.exit(main())