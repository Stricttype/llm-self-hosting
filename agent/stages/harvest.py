#!/usr/bin/env python3
"""
HARVEST stage stub — collects events from the event log.
Step 2/3 implementation: reads agent/events.jsonl, filters by surprise/recovery/novel-type.
For now: just dumps the file. Real logic = ~50 LOC.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

EVENTS = Path("agent/events.jsonl")


def main() -> int:
    if not EVENTS.exists():
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        EVENTS.touch()
    events = []
    with EVENTS.open() as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    out = Path("agent/state/harvested_events.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"count": len(events), "events": events}, indent=2))
    print(f"[harvest] {len(events)} events → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())