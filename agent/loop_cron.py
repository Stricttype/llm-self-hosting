#!/usr/bin/env python3
"""
Cron entry point for the closed-loop.
Checks if interval elapsed since last run, if yes → executes run_loop.py.
Idempotent: safe to invoke from launchd/cron/systemd timer at any frequency.

Usage:
  # Run immediately
  python3 agent/loop_cron.py --force

  # Cron with 1h interval (default)
  python3 agent/loop_cron.py --interval 3600

  # Setup launchd (macOS) or systemd timer (Linux)
  # See docs/cron-setup.md for details.

Per Claude v2: nightly cron = 'CONSENSUS + drift check + question workflows pass'.
Lower frequency than the event-driven spine. Recommended: 1h - 24h depending on
how fast you want to react to the system.
"""

from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
STATE = ROOT / "agent" / "state"
LAST_RUN_FILE = STATE / "last_cron_run.json"


def should_run(interval_s: int) -> tuple[bool, dict]:
    """Check if interval has elapsed since last successful run."""
    if not LAST_RUN_FILE.exists():
        return True, {"reason": "no last run recorded"}
    try:
        last = json.loads(LAST_RUN_FILE.read_text())
        last_ts = last.get("ts", 0)
        elapsed = time.time() - last_ts
        if elapsed >= interval_s:
            return True, {"reason": f"interval elapsed ({elapsed:.0f}s >= {interval_s}s)", "last_run": last_ts}
        return False, {"reason": f"too soon ({elapsed:.0f}s < {interval_s}s)", "last_run": last_ts}
    except Exception as e:
        return True, {"reason": f"error reading last run: {e}"}


def record_run(rc: int, duration_s: float, n_promoted: int) -> None:
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_FILE.write_text(json.dumps({
        "ts": time.time(),
        "rc": rc,
        "duration_s": duration_s,
        "n_promoted": n_promoted,
    }, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=3600,
                    help="minimum seconds between runs (default 3600 = 1h)")
    ap.add_argument("--force", action="store_true",
                    help="run regardless of interval")
    args = ap.parse_args()

    if not args.force:
        should, info = should_run(args.interval)
        print(f"[loop_cron] {'RUN' if should else 'SKIP'} — {info['reason']}")
        if not should:
            return 0

    t0 = time.time()
    print(f"[loop_cron] invoking run_loop.py (interval={args.interval}s)")
    result = subprocess.run(
        [sys.executable, str(ROOT / "agent" / "run_loop.py")],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT),
    )
    duration = time.time() - t0
    print(f"[loop_cron] run_loop.py rc={result.returncode} duration={duration:.1f}s")
    if result.stdout:
        # Print last few lines for visibility
        for line in result.stdout.strip().splitlines()[-5:]:
            print(f"  {line}")

    # Count promotions this run from promotion_log
    n_promoted = 0
    plog = STATE / "promotion_log.json"
    if plog.exists():
        plog_data = json.loads(plog.read_text())
        n_promoted = len(plog_data.get("promoted", []))

    record_run(result.returncode, duration, n_promoted)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())