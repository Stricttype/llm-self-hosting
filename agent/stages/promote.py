#!/usr/bin/env python3
"""
PROMOTE stage — atomic swap if SHADOW's winner beats incumbent with no regressions.
Per Claude v2: NEVER promote first passer. Tournament winner only.
Per Claude v2: never optimize a metric the system can write. SHADOW score is the verdict.
"""

from __future__ import annotations
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
IN = ROOT / "agent" / "state" / "shadow_scores.json"
CANDIDATES_DIR = ROOT / "agent" / "state" / "candidates"
OUT = ROOT / "agent" / "state" / "promotion_log.json"


def find_winner_source(variant_id: str, target_script: str) -> Path | None:
    snap = CANDIDATES_DIR / f"{target_script}__{variant_id}.py"
    return snap if snap.exists() else None


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(IN.read_text()) if IN.exists() else {}
    verdict = data.get("verdict", "neutral")
    winner_label = data.get("winner")

    # Load existing log to preserve history (append, don't overwrite)
    if OUT.exists():
        existing = json.loads(OUT.read_text())
        prev_promoted = existing.get("promoted", [])
        prev_runs = existing.get("runs", 0)
    else:
        prev_promoted = []
        prev_runs = 0

    log = {
        "promoted": prev_promoted,
        "n_evaluated": data.get("n_candidates", 0),
        "ts": None,
        "runs": prev_runs + 1,
        "last_attempt": None,
    }

    if verdict != "promote" or not winner_label:
        log["ts"] = datetime.now(timezone.utc).isoformat()
        log["last_attempt"] = {"ts": log["ts"], "verdict": verdict, "winner": winner_label}
        log["reason"] = f"verdict={verdict}; no promotion"
        OUT.write_text(json.dumps(log, indent=2))
        print(f"[promote] no promotion (verdict={verdict}, run #{log['runs']})")
        return 0

    src = find_winner_source(winner_label, "prompt_guard")
    if not src:
        log["ts"] = datetime.now(timezone.utc).isoformat()
        log["last_attempt"] = {"ts": log["ts"], "verdict": verdict, "winner": winner_label}
        log["reason"] = f"winner snapshot not found: {winner_label}"
        OUT.write_text(json.dumps(log, indent=2))
        print(f"[promote] FATAL: winner snapshot not found: {src}")
        return 1

    incumbent_path = ROOT / "use-cases" / "prompt_guard.py"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    bak_path = incumbent_path.with_suffix(f".py.bak.{ts}")
    shutil.copy(incumbent_path, bak_path)
    shutil.copy(src, incumbent_path)

    log["promoted"].append({
        "script": "prompt_guard",
        "variant": winner_label,
        "incumbent_pass_rate": data.get("incumbent_pass_rate"),
        "winner_pass_rate": next((s.get("candidate_pass_rate") for s in data["scores"] if s["label"] == winner_label), None),
        "incumbent_backup": str(bak_path),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    })
    log["last_attempt"] = {"ts": log["promoted"][-1]["promoted_at"], "verdict": "promote", "winner": winner_label}
    log["ts"] = log["promoted"][-1]["promoted_at"]
    OUT.write_text(json.dumps(log, indent=2))
    print(f"[promote] PROMOTED {winner_label} → use-cases/prompt_guard.py")
    print(f"[promote] incumbent backup: {bak_path}")
    print(f"[promote] history: {len(log['promoted'])} total promotions, run #{log['runs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())