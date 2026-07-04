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

    # If events.jsonl is empty (pre-hook state), synthesize from current loop state.
    # Real impl: post-task hooks write here. Stub: derive from loop_summary/promotion_log/drift_alerts.
    if not events:
        STATE = Path("agent/state")
        summary = json.loads((STATE / "loop_summary.json").read_text()) if (STATE / "loop_summary.json").exists() else {}
        promotion = json.loads((STATE / "promotion_log.json").read_text()) if (STATE / "promotion_log.json").exists() else {}
        drift = json.loads((STATE / "drift_alerts.json").read_text()) if (STATE / "drift_alerts.json").exists() else {}

        for stage_id in summary.get("done", []):
            events.append({
                "event_id": f"loop_{summary.get('ts', 0):.0f}_{stage_id}",
                "type": "stage_completion",
                "stage": stage_id,
                "outcome": "passed",
                "passed": True,
                "context": f"closed-loop stage {stage_id} completed in run @ {summary.get('ts')}",
                "ts": summary.get("ts"),
            })
        for entry in promotion.get("promoted", []):
            events.append({
                "event_id": f"promotion_{entry.get('promoted_at', '')}",
                "type": "promotion",
                "outcome": "promoted",
                "passed": True,
                "context": f"{entry.get('script')}@{entry.get('variant')} promoted at {entry.get('winner_pass_rate')}%",
                "ts": entry.get("promoted_at"),
            })
        for alert in drift.get("alerts", []):
            events.append({
                "event_id": f"drift_{alert.get('ts', '')}",
                "type": "drift_alert",
                "outcome": "demoted",
                "passed": False,
                "context": alert.get("reason", "drift"),
                "ts": alert.get("ts"),
            })

    out = Path("agent/state/harvested_events.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"count": len(events), "events": events, "synthetic": not EVENTS.exists() or EVENTS.stat().st_size == 0}, indent=2))
    src = "events.jsonl" if EVENTS.exists() and EVENTS.stat().st_size > 0 else "synthetic from loop state"
    print(f"[harvest] {len(events)} events → {out} (source: {src})")
    return 0


if __name__ == "__main__":
    sys.exit(main())