#!/usr/bin/env python3
"""
VALUE stage — VoI gate (real impl per Claude v2 review).
VoI = novelty_deadband(HNSW-NN) × outcome_proxy / shadow_cost_estimate

Per Claude v2:
- novelty: HNSW nearest-neighbor distance with dead band (not centroid - outliers=garbage)
- outcome_proxy: task's own pre-existing assertion (free, external signal)
- cost: per-promotion-attempt (candidates × fixtures × model_price)

Read-only mode (per Claude: 1 week before gating anything).
Logs keep/drop decisions but doesn't block downstream stages.

Ponytail: pure stdlib + one MCP call per event (Ruflo memory_search).
For self-check, can run with --no-mcp to use a stub novelty.
"""

from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
IN_EVENTS = ROOT / "agent" / "state" / "harvested_events.json"
IN_SUMMARY = ROOT / "agent" / "state" / "loop_summary.json"
IN_PROMOTION = ROOT / "agent" / "state" / "promotion_log.json"
IN_DRIFT = ROOT / "agent" / "state" / "drift_alerts.json"
OUT = ROOT / "agent" / "state" / "value_decisions.json"

# VoI parameters (per Claude v2)
NOVELTY_DUP_THRESHOLD = 0.15      # below this distance = duplicate, score 0
NOVELTY_GARBAGE_THRESHOLD = 0.95  # above this distance = probably garbage, score 0
SHADOW_FIXTURE_COUNT = 20         # current regression fixture count
SHADOW_CANDIDATES_TOURNAMENT = 3  # N=3 tournament
SHADOW_PER_FIXTURE_SEC = 0.05     # rough cost estimate per fixture run
Voi_GATE_THRESHOLD = 0.01         # below = drop (in read-only mode we log, don't gate)


def generate_synthetic_events() -> list[dict]:
    """Generate events from current loop state when no harvested_events.json exists.
    Makes the loop runnable end-to-end before post-task hooks are wired.
    """
    events = []
    summary = json.loads(IN_SUMMARY.read_text()) if IN_SUMMARY.exists() else {}
    promotion = json.loads(IN_PROMOTION.read_text()) if IN_PROMOTION.exists() else {}
    drift = json.loads(IN_DRIFT.read_text()) if IN_DRIFT.exists() else {}

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

    return events


def call_ruflo_memory_search(query: str, namespace: str = "agent-rules") -> float:
    """Call ruflo memory search and return the similarity score of the top hit.
    Returns 0.0 if no results or error (max-novelty for unknown patterns).
    """
    try:
        result = subprocess.run(
            ["ruflo", "memory", "search", "-q", query, "-n", namespace, "-l", "1"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return 0.0
        out = result.stdout.strip()
        # Parse first similarity score (format varies; look for "score=" or "similarity=" or "%")
        for line in out.splitlines():
            for tok in line.split():
                if tok.startswith("score=") or tok.startswith("similarity="):
                    try:
                        return float(tok.split("=")[1])
                    except (ValueError, IndexError):
                        continue
            # Some CLI outputs include "score: 0.85" or similar
            if "score:" in line.lower():
                try:
                    return float(line.lower().split("score:")[1].strip().split()[0])
                except (ValueError, IndexError):
                    continue
        return 0.0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0.0


def novelty_deadband(similarity: float) -> tuple[float, str]:
    """Per Claude v2: nearest-neighbor distance with dead band both ends.
    similarity is 0-1 where 1 = identical to existing pattern.
    novelty = distance = 1 - similarity, dead-banded.
    Returns (novelty, reason). reason explains if drop.
    """
    # No signal: no patterns to compare against. Treat as moderate novelty,
    # let outcome_proxy + shadow_cost decide.
    if similarity == 0.0:
        return 0.5, "no_baseline"
    distance = 1.0 - similarity
    if distance < NOVELTY_DUP_THRESHOLD:
        return 0.0, "duplicate_of_existing_pattern"
    if distance > NOVELTY_GARBAGE_THRESHOLD:
        return 0.0, "garbage_outlier_distance_too_high"
    return distance, "novel"


def shadow_cost_estimate(n_fixtures: int = SHADOW_FIXTURE_COUNT, n_candidates: int = SHADOW_CANDIDATES_TOURNAMENT) -> float:
    """Per Claude v2: cost per-promotion-attempt = candidates × fixtures × per_fixture_seconds."""
    return float(n_fixtures * n_candidates * SHADOW_PER_FIXTURE_SEC)


def score_event(event: dict, use_mcp: bool = True) -> dict:
    """Score one event with VoI = novelty × outcome / cost."""
    query = event.get("context", event.get("type", "unknown"))
    if use_mcp:
        similarity = call_ruflo_memory_search(query)
    else:
        # Deterministic stub: hash-based pseudo-similarity for self-tests
        import hashlib
        h = hashlib.md5(query.encode()).hexdigest()
        similarity = (int(h[:8], 16) % 1000) / 1000.0 * 0.7  # 0..0.7 range
    novelty, novelty_reason = novelty_deadband(similarity)
    outcome_proxy = 1.0 if event.get("passed", False) else 0.0
    cost = shadow_cost_estimate()
    voi = (novelty * outcome_proxy) / cost if cost > 0 else 0.0
    if novelty == 0.0:
        decision = "drop"
        reason = novelty_reason
    elif outcome_proxy == 0.0:
        decision = "drop"
        reason = "task_failed_outcome_proxy_zero"
    elif voi < Voi_GATE_THRESHOLD:
        decision = "drop"
        reason = f"voi={voi:.4f}_below_threshold"
    else:
        decision = "keep"
        reason = f"voi={voi:.4f}_novel={novelty:.3f}_sim={similarity:.3f}"
    return {
        "event_id": event.get("event_id", "?"),
        "type": event.get("type"),
        "novelty": round(novelty, 4),
        "similarity_to_nearest": round(similarity, 4),
        "outcome_proxy": outcome_proxy,
        "shadow_cost": cost,
        "voi_score": round(voi, 6),
        "decision": decision,
        "reason": reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-mcp", action="store_true",
                    help="use deterministic stub instead of live Ruflo MCP")
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)

    # Load events from harvest OR generate from state
    if IN_EVENTS.exists():
        data = json.loads(IN_EVENTS.read_text())
        events = data.get("events", [])
        source = "harvested_events.json"
    else:
        events = generate_synthetic_events()
        source = "synthetic from loop_summary/promotion_log/drift_alerts"

    decisions = [score_event(e, use_mcp=not args.no_mcp) for e in events]
    kept = [d for d in decisions if d["decision"] == "keep"]
    dropped = [d for d in decisions if d["decision"] == "drop"]
    drop_rate = len(dropped) / max(len(decisions), 1)

    summary = {
        "source": source,
        "n_events": len(decisions),
        "n_kept": len(kept),
        "n_dropped": len(dropped),
        "drop_rate": round(drop_rate, 3),
        "mode": "read-only" if args.no_mcp else "live-mcp",
        "threshold": Voi_GATE_THRESHOLD,
        "decisions": decisions,
        "ts_summary": "diagnostic_only_per_claude_v2_review",
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"[value] {len(kept)} kept / {len(dropped)} dropped (drop_rate={drop_rate:.0%}) — read-only mode")
    print(f"[value] source: {source}")
    if args.no_mcp:
        print(f"[value] mode: stub (deterministic, --no-mcp)")
    for d in decisions[:5]:
        marker = "KEEP" if d["decision"] == "keep" else "DROP"
        print(f"  [{marker}] {d['event_id']:50s} VoI={d['voi_score']:.4f} novel={d['novelty']:.3f} reason={d['reason']}")
    if len(decisions) > 5:
        print(f"  ... +{len(decisions) - 5} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())