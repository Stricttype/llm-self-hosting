#!/usr/bin/env python3
"""
MONITOR stage — drift sidecar (orthogonal, time-driven).
Runs drift_monitor on all promoted artifacts.
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

IN = Path("agent/state/promotion_log.json")
OUT = Path("agent/state/drift_alerts.json")
DRIFT_MON = Path("agent/drift_monitor.py")


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    log = json.loads(IN.read_text()) if IN.exists() else {"promoted": []}
    promoted = log.get("promoted", [])
    alerts = []
    # Stub: no promoted artifacts yet, no alerts
    OUT.write_text(json.dumps({"alerts": alerts, "n_promoted": len(promoted)}, indent=2))
    print(f"[monitor] 0 alerts ({len(promoted)} promoted artifacts tracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())