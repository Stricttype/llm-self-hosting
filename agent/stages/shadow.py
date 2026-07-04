#!/usr/bin/env python3
"""
SHADOW stage — scores incumbent + every candidate variant on frozen fixtures.
Picks the best candidate (highest pass rate, no regressions) for PROMOTE.

Per Claude v2: tournaments scored on the same fixture set. Reject any candidate
that regresses any existing fixture. If all tie, return NEUTRAL (no promotion).
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
IN = ROOT / "agent" / "state" / "candidates.json"
SHADOW = ROOT / "tests" / "shadow_run.py"
CANDIDATES_DIR = ROOT / "agent" / "state" / "candidates"
OUT = ROOT / "agent" / "state" / "shadow_scores.json"


def score_one(label: str, candidate_path: Path | None, target_script: str) -> dict:
    """Run shadow_run --compare against one candidate path.
    Use --script to explicitly map the candidate to its target script (override filename stem).
    """
    cmd = [sys.executable, str(SHADOW), "--compare"]
    if candidate_path is not None:
        cmd.extend(["--candidate", str(candidate_path), "--script", target_script])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    # Parse pass rate from "incumbent: pass_rate=XX.X% (N/M) ..." line
    out = {"label": label, "rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    for line in result.stdout.splitlines():
        if line.startswith("incumbent:"):
            # e.g. "incumbent:  pass_rate=90.0% (18/20) regressions=2 errors=0"
            parts = line.split()
            for p in parts[1:]:
                if p.startswith("pass_rate="):
                    out["incumbent_pass_rate"] = float(p.split("=")[1].rstrip("%"))
                elif p.startswith("regressions="):
                    out["incumbent_regressions"] = int(p.split("=")[1])
        elif line.startswith("candidate:"):
            parts = line.split()
            for p in parts[1:]:
                if p.startswith("pass_rate="):
                    out["candidate_pass_rate"] = float(p.split("=")[1].rstrip("%"))
                elif p.startswith("regressions="):
                    out["candidate_regressions"] = int(p.split("=")[1])
        elif line.startswith("delta:"):
            # e.g. "delta:      +2 passes, 0 new regressions"
            tokens = line.split()
            # tokens: ['delta:', '+2', 'passes,', '0', 'new', 'regressions']
            try:
                passes_idx = tokens.index("passes,")
                if passes_idx > 0:
                    out["delta_passes"] = int(tokens[passes_idx - 1].replace("+", ""))
                regs_idx = tokens.index("regressions")
                if regs_idx > 0:
                    out["delta_regressions"] = int(tokens[regs_idx - 1])
            except (ValueError, IndexError):
                pass
        elif line.startswith("PROMOTE"):
            out["verdict"] = "promote"
        elif line.startswith("NEUTRAL"):
            out["verdict"] = "neutral"
        elif line.startswith("REGRESSION"):
            out["verdict"] = "reject"
    return out


def main() -> int:
    candidates_data = json.loads(IN.read_text()) if IN.exists() else {"candidates": []}
    candidates = candidates_data.get("candidates", [])

    if not candidates:
        print("[shadow] no candidates to score (incumbent-only)")
        OUT.write_text(json.dumps({"scores": [], "winner": None}, indent=2))
        return 0

    scores = []
    # Score each variant's snapshot
    snapshots = sorted(CANDIDATES_DIR.glob("*__v*.py"))
    target_script = candidates_data.get("target_script", "prompt_guard")
    for snap in snapshots:
        vid = snap.stem.split("__")[-1]  # e.g. "v1_more_patterns"
        s = score_one(vid, snap, target_script)
        scores.append(s)

    # Pick winner: highest pass rate, zero regressions, most improvement over incumbent
    incumbent_pass_rate = scores[0].get("incumbent_pass_rate", 0.0) if scores else 0.0
    eligible = [s for s in scores if s.get("candidate_regressions", 99) == 0
                                       and s.get("delta_passes", 0) > 0
                                       and s.get("verdict") == "promote"]
    if eligible:
        winner = max(eligible, key=lambda s: s.get("candidate_pass_rate", 0))
        verdict = "promote"
    elif any(s.get("verdict") == "reject" for s in scores):
        verdict = "reject"
    else:
        verdict = "neutral"
        winner = None

    summary = {
        "scores": scores,
        "incumbent_pass_rate": incumbent_pass_rate,
        "winner": winner["label"] if winner else None,
        "verdict": verdict,
        "n_candidates": len(candidates),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"[shadow] {len(scores)} variants scored. incumbent={incumbent_pass_rate:.1f}% verdict={verdict}")
    if winner:
        print(f"[shadow] winner: {winner['label']} ({winner.get('candidate_pass_rate', 0):.1f}%)")
    for s in scores:
        v = s.get("verdict", "?")
        ip = s.get("incumbent_pass_rate", 0)
        cp = s.get("candidate_pass_rate", 0)
        dr = s.get("delta_regressions", "?")
        print(f"  {s['label']:25s} incumbent={ip:.1f}% candidate={cp:.1f}% verdict={v} regressions={dr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())