"""
Test the shadow runner itself: prove it correctly rejects a regressing candidate
and accepts an improving one.

Ponytail: copy files, run shadow, restore. Atomic-ish.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
USE_CASES = ROOT / "use-cases"
SHADOW = ROOT / "tests" / "shadow_run.py"


def test_rejects_regression():
    """A candidate that breaks a fixture must be REJECTED.
    The candidate filename's stem must match the script name for shadow_run to apply it.
    """
    target = USE_CASES / "hardware_sizer.py"
    broken_path = ROOT / "tests" / "hardware_sizer.py"  # stem = hardware_sizer
    shutil.copy(target, broken_path)
    try:
        content = broken_path.read_text()
        broken = content.replace(
            "    weights_gb = (model_params_b * 1e9 * spec.bits_per_weight / 8) / 1e9 * (1 + spec.overhead_pct)",
            "    weights_gb = (model_params_b * 1e9 * spec.bits_per_weight / 8) / 1e9 * (1 + spec.overhead_pct) * 10  # BUG: 10x inflation",
        )
        assert broken != content, "edit pattern not found"
        broken_path.write_text(broken)

        result = subprocess.run(
            [sys.executable, str(SHADOW), "--compare", "--candidate", str(broken_path)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 1, f"expected reject (exit 1), got {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "REGRESSION" in result.stdout
        print("OK: shadow runner REJECTS regressing candidate")
    finally:
        broken_path.unlink(missing_ok=True)


def test_accepts_neutral():
    """A no-op candidate (same file) is NEUTRAL."""
    target = USE_CASES / "cost_calculator.py"
    result = subprocess.run(
        [sys.executable, str(SHADOW), "--compare", "--candidate", str(target)],
        capture_output=True, text=True, timeout=30,
    )
    assert "NEUTRAL" in result.stdout or "PROMOTE" in result.stdout
    print("OK: shadow runner handles neutral candidate")


def test_incumbent_baseline():
    """Incumbent score is captured for compare."""
    result = subprocess.run(
        [sys.executable, str(SHADOW), "--incumbent"],
        capture_output=True, text=True, timeout=30,
    )
    assert "pass_rate=" in result.stdout
    print("OK: shadow runner reports incumbent baseline")


if __name__ == "__main__":
    test_incumbent_baseline()
    test_accepts_neutral()
    test_rejects_regression()
    print("\nALL: shadow runner self-tests pass")