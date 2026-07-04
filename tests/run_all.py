"""
Test runner for all use-case self-checks.
Runs each module as a subprocess and reports pass/fail.
Ponytail: stdlib only, subprocess + json-free parsing.
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path

USE_CASES = Path(__file__).parent.parent / "use-cases"
ROOT = Path(__file__).parent.parent


def run(name: str) -> tuple[bool, str]:
    path = USE_CASES / f"{name}.py"
    if not path.exists():
        return False, f"missing {path}"
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False, f"exit={result.returncode}\nstderr: {result.stderr[-500:]}"
        # Look for "OK:" line as success marker
        last_ok = [ln for ln in result.stdout.splitlines() if ln.startswith("OK:")]
        if not last_ok:
            return False, f"no 'OK:' marker\nstdout: {result.stdout[-500:]}"
        return True, last_ok[-1]
    except subprocess.TimeoutExpired:
        return False, "timeout (>30s)"


def main() -> int:
    cases = sorted(p.stem for p in USE_CASES.glob("*.py"))
    print(f"Running {len(cases)} use-case self-checks:\n")
    passed = 0
    failed = []
    for name in cases:
        ok, msg = run(name)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {name:25s} {msg}")
        if ok:
            passed += 1
        else:
            failed.append(name)
    print(f"\n{passed}/{len(cases)} passed")

    # Fixtures
    print(f"\nFrozen regression fixtures:")
    result = subprocess.run([sys.executable, str(Path(__file__).parent / "fixtures.py")],
                            capture_output=True, text=True, timeout=30)
    print(f"  {result.stdout.strip().splitlines()[0]}")
    fix_pass = result.returncode == 0

    # Shadow runner self-tests
    print(f"\nShadow runner self-tests:")
    shadow_test = Path(__file__).parent / "test_shadow_run.py"
    result = subprocess.run([sys.executable, str(shadow_test)],
                            capture_output=True, text=True, timeout=30)
    for line in result.stdout.strip().splitlines():
        print(f"  {line}")
    shadow_pass = result.returncode == 0

    # Holdout (Step 0 — north-star metric)
    print(f"\nHoldout (Step 0, north-star metric):")
    result = subprocess.run([sys.executable, str(Path(__file__).parent / "holdout.py")],
                            capture_output=True, text=True, timeout=30)
    for line in result.stdout.strip().splitlines():
        print(f"  {line}")
    holdout_pass = result.returncode == 0

    # Agent stubs (Step 0.5 provenance + Step 1.5 drift monitor)
    print(f"\nAgent stubs (Step 0.5 + 1.5):")
    for stub in ["provenance", "drift_monitor"]:
        path = ROOT / "agent" / f"{stub}.py"
        if not path.exists():
            continue
        result = subprocess.run([sys.executable, str(path)],
                                capture_output=True, text=True, timeout=30)
        for line in result.stdout.strip().splitlines():
            print(f"  [{stub}] {line}")
        if result.returncode != 0:
            return 1

    # Closed-loop workflow run (Ruflo-orchestrated, locally executed)
    print(f"\nClosed-loop workflow (Ruflo swarm + DAA, autonomous run):")
    loop_path = ROOT / "agent" / "run_loop.py"
    result = subprocess.run([sys.executable, str(loop_path)],
                            capture_output=True, text=True, timeout=120)
    for line in result.stdout.strip().splitlines()[-10:]:
        print(f"  {line}")
    loop_pass = result.returncode == 0

    return 0 if (not failed and fix_pass and shadow_pass and holdout_pass and loop_pass) else 1


if __name__ == "__main__":
    sys.exit(main())