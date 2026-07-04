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
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())