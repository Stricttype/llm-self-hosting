#!/usr/bin/env python3
"""
PROPOSE stage — generates candidate variants for ALL registered scripts.
Per Claude v2 review: param variation first, structural mutation second, foreign import third.

Ponytail: N=3 tournament per script, iterates over tunable.py registry.
Each candidate is a self-contained .py file in agent/state/candidates/ with stem
matching the script name so shadow_runner can apply it as an override.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
USE_CASES = ROOT / "use-cases"
CANDIDATES_DIR = ROOT / "agent" / "state" / "candidates"
OUT = ROOT / "agent" / "state" / "candidates.json"

sys.path.insert(0, str(ROOT))
from agent.stages.tunable import TUNABLES, all_scripts, get_variants  # noqa: E402


def main() -> int:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

    # Wipe old candidates (clean slate per loop iteration)
    for old in CANDIDATES_DIR.glob("*.py"):
        old.unlink()

    all_candidates = []
    by_script: dict[str, list[dict]] = {}

    for script_name in all_scripts():
        incumbent_path = USE_CASES / f"{script_name}.py"
        if not incumbent_path.exists():
            print(f"[propose] skip {script_name}: incumbent not found")
            continue
        source = incumbent_path.read_text()
        candidates = []
        for vid, mutator, description in get_variants(script_name):
            mutated = mutator(source)
            # If mutator returned unchanged source AND it's not the control,
            # this is an idempotent no-op (already promoted). Allow it but skip
            # writing a useless snapshot file.
            if mutated == source and vid != "v0_control":
                # Still log for transparency — the loop knows the feature exists.
                candidates.append({
                    "variant_id": vid,
                    "script": script_name,
                    "description": description + " [already-promoted, no-op]",
                    "path": None,
                    "size_bytes": 0,
                    "noop": True,
                })
                continue
            variant_footer = f'\n__variant_id__ = "{script_name}__{vid}"\n'
            mutated_with_tag = mutated.rstrip() + variant_footer
            snap = CANDIDATES_DIR / f"{script_name}__{vid}.py"
            snap.write_text(mutated_with_tag)
            candidates.append({
                "variant_id": vid,
                "script": script_name,
                "description": description,
                "path": str(snap),
                "size_bytes": len(mutated_with_tag),
            })
        by_script[script_name] = candidates
        all_candidates.extend(candidates)

    summary = {
        "tournament_size_per_script": 3,
        "scripts": list(by_script.keys()),
        "by_script": by_script,
        "candidates": all_candidates,
        "n_total": len(all_candidates),
        "mode": "real_multi_script",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2))
    print(f"[propose] {len(all_candidates)} candidates across {len(by_script)} scripts → {CANDIDATES_DIR}/")
    for s, cs in by_script.items():
        print(f"  {s}:")
        for c in cs:
            print(f"    - {c['variant_id']}: {c['description']} ({c['size_bytes']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())