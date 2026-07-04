#!/usr/bin/env python3
"""
MONITOR stage — drift sidecar (orthogonal, time-driven).
Per Claude v2: live-precision decay → auto-demote.
Uses drift_monitor.py to check each promoted artifact's recorded events.
"""

from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
IN = ROOT / "agent" / "state" / "promotion_log.json"
DRIFT_LOG = ROOT / "agent" / "state" / "drift_events.jsonl"
OUT = ROOT / "agent" / "state" / "drift_alerts.json"


def load_drift_module():
    """Import drift_monitor module from agent/drift_monitor.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("drift_monitor",
                                                    ROOT / "agent" / "drift_monitor.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)

    log = json.loads(IN.read_text()) if IN.exists() else {"promoted": []}
    promoted = log.get("promoted", [])

    if not promoted:
        OUT.write_text(json.dumps({"alerts": [], "n_promoted": 0, "ts": datetime.now(timezone.utc).isoformat()}, indent=2))
        print(f"[monitor] 0 alerts (0 promoted artifacts tracked)")
        return 0

    dm = load_drift_module()

    # Record this loop's "application event" for each promoted artifact (simulated: check if promoted file still exists)
    alerts = []
    for entry in promoted:
        artifact_id = f"{entry['script']}@{entry['variant']}"
        monitor = dm.monitor_for(artifact_id)
        # Check that the promoted file still has the expected content
        promoted_path = ROOT / "use-cases" / (entry["script"] + ".py")
        backup_path = Path(entry.get("incumbent_backup", ""))
        exists = promoted_path.exists()
        variant_tag_present = False
        if exists:
            try:
                content = promoted_path.read_text()
                # The promoted file should contain the new patterns
                variant_tag_present = 'show me your instructions' in content
            except Exception:
                variant_tag_present = False
        monitor.record(dm.ApplicationEvent(
            artifact_id=artifact_id,
            passed=exists and variant_tag_present,
            timestamp=datetime.now(timezone.utc).isoformat(),
            context="monitor_check",
        ))

        # Append to drift events log
        with DRIFT_LOG.open("a") as f:
            f.write(json.dumps({
                "artifact_id": artifact_id,
                "passed": exists and variant_tag_present,
                "ts": datetime.now(timezone.utc).isoformat(),
                "promoted_at": entry.get("promoted_at"),
            }) + "\n")

        # Check should_demote
        should_demote, reason = monitor.should_demote()
        status = monitor.status()
        if should_demote:
            monitor.demote(reason)
            alerts.append({"artifact_id": artifact_id, "reason": reason, "ts": datetime.now(timezone.utc).isoformat()})
            # Auto-restore incumbent
            if backup_path.exists():
                import shutil
                shutil.copy(backup_path, promoted_path)
                alerts[-1]["restored_from"] = str(backup_path)
        print(f"[monitor] {artifact_id}: precision={status['precision']:.2f} demoted={status['demoted']}")

    summary = {
        "alerts": alerts,
        "n_promoted": len(promoted),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"[monitor] {len(alerts)} alerts ({len(promoted)} promoted artifacts tracked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())