"""
Shadow runner: score a candidate against the frozen regression harness.

Usage:
  python3 tests/shadow_run.py                            # score incumbent (current code)
  python3 tests/shadow_run.py --candidate path/to/script.py  # score a proposed variant

Ponytail: subprocess the candidate's file as a module, then re-run fixtures against it.
Reports pass_rate, regressions (fixtures that pass on incumbent but fail on candidate).
"""

from __future__ import annotations
import argparse
import importlib.util
import sys
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).parent.parent
USE_CASES = ROOT / "use-cases"


@dataclass
class ShadowScore:
    passed: int
    total: int
    pass_rate: float
    regressions: list[str]   # names that should have passed but didn't
    errors: list[str]

    def beats_incumbent(self, incumbent: "ShadowScore") -> bool:
        return (
            self.passed > incumbent.passed
            and not self.regressions
        )

    def __str__(self) -> str:
        return (
            f"pass_rate={self.pass_rate:.1%} ({self.passed}/{self.total}) "
            f"regressions={len(self.regressions)} errors={len(self.errors)}"
        )


def _load_fixture_module(script_name: str, override_path: Path | None = None):
    """Load a use-cases module, optionally overriding the file path."""
    import sys as _sys
    path = override_path if override_path else (USE_CASES / f"{script_name}.py")
    if not path.exists():
        raise FileNotFoundError(f"candidate not found: {path}")
    spec = importlib.util.spec_from_file_location(f"_uc_{script_name}", path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = mod  # Py3.14 dataclasses requires module in sys.modules
    spec.loader.exec_module(mod)
    return mod


def score(candidate_overrides: dict[str, Path] | None = None) -> ShadowScore:
    """Run all fixtures. candidate_overrides maps script_name -> file path under test."""
    sys.path.insert(0, str(ROOT))
    from tests.fixtures import FIXTURES  # noqa: E402

    passed = 0
    regressions = []
    errors = []

    for f in FIXTURES:
        try:
            override = candidate_overrides.get(f.script) if candidate_overrides else None
            mod = _load_fixture_module(f.script, override)
            # Mirror fixtures.py safe builtins
            from tests.fixtures import _SAFE_BUILTINS
            if eval(f.assertion, {"__builtins__": _SAFE_BUILTINS}, {f.script: mod}):
                passed += 1
            else:
                # If this fixture passed on incumbent (default path) and we're shadow-testing,
                # it's a regression. Caller compares with incumbent score.
                regressions.append(f.name)
        except Exception as e:
            errors.append(f"{f.name}: {type(e).__name__}: {e}")

    total = len(FIXTURES)
    return ShadowScore(
        passed=passed,
        total=total,
        pass_rate=passed / total if total else 0.0,
        regressions=regressions,
        errors=errors,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", type=Path, action="append", default=[],
                    help="path to candidate file; can repeat. Script name inferred from filename, or set explicitly with --script.")
    ap.add_argument("--script", action="append", default=[],
                    help="explicit script name for the corresponding --candidate (positional pairing).")
    ap.add_argument("--incumbent", action="store_true",
                    help="score the incumbent (default = no overrides)")
    ap.add_argument("--compare", action="store_true",
                    help="score both incumbent and candidate, report delta")
    args = ap.parse_args()

    # Build overrides map from --candidate flags
    overrides: dict[str, Path] = {}
    explicit_scripts = list(args.script)
    for i, path in enumerate(args.candidate):
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        # If explicit --script was given for this position, use it; else fall back to filename stem
        if i < len(explicit_scripts):
            script_name = explicit_scripts[i]
        else:
            script_name = path.stem
        overrides[script_name] = path

    if args.compare and overrides:
        # Snapshot incumbent files BEFORE loading candidate (since candidate may live in use-cases/)
        import tempfile, shutil
        snap_dir = Path(tempfile.mkdtemp(prefix="incumbent_snapshot_"))
        incumbent_copies: dict[str, Path] = {}
        try:
            for script_name in overrides:
                src = USE_CASES / f"{script_name}.py"
                if src.exists():
                    dst = snap_dir / f"{script_name}.py"
                    shutil.copy(src, dst)
                    incumbent_copies[script_name] = dst
            # Score incumbent using the snapshots
            incumbent = score(candidate_overrides=incumbent_copies if incumbent_copies else None)
            # Score candidate using the live overrides (which may be the actual modified files)
            candidate = score(candidate_overrides=overrides)
        finally:
            shutil.rmtree(snap_dir, ignore_errors=True)
        print(f"incumbent:  {incumbent}")
        print(f"candidate:  {candidate}")
        delta_passed = candidate.passed - incumbent.passed
        new_regressions = [r for r in candidate.regressions if r not in incumbent.regressions]
        print(f"delta:      {delta_passed:+d} passes, {len(new_regressions)} new regressions")
        if new_regressions:
            print("REGRESSION (reject candidate):")
            for r in new_regressions:
                print(f"  - {r}")
            return 1
        if delta_passed > 0:
            print("PROMOTE: candidate beats incumbent with no regressions.")
            return 0
        print("NEUTRAL: no improvement, no regression. Decide based on other criteria.")
        return 0

    s = score(candidate_overrides=overrides if overrides else None)
    print(f"shadow: {s}")
    if s.errors:
        for e in s.errors:
            print(f"  ERR {e}")
    return 0 if not s.regressions and not s.errors else 1


if __name__ == "__main__":
    sys.exit(main())