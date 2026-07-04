"""
Drift monitor — live-precision decay tracker for promoted artifacts.
Step 1.5 of the self-improvement loop.

Rule: a promoted artifact is NOT done when SHADOW passes it. It's only proven
if live application precision stays above a floor over a rolling window.
Decay below floor → auto-demote, restore incumbent.bak, log why.

We haven't promoted anything yet, so this is a STUB that documents the contract
and provides a minimal interface. When Step 3 starts promoting scripts, this
gets real data.

Ponytail: dataclass + tiny API surface, zero deps, runnable check.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timezone


@dataclass(frozen=True)
class ApplicationEvent:
    artifact_id: str
    passed: bool
    timestamp: str   # ISO 8601
    context: str     # short tag of where applied


@dataclass
class DriftMonitor:
    artifact_id: str
    window_days: int = 14
    floor_precision: float = 0.6
    min_samples: int = 5            # don't trigger with too little data
    _events: deque[ApplicationEvent] = field(default_factory=deque)
    _demoted_at: str | None = None
    _demote_reason: str | None = None

    def record(self, event: ApplicationEvent) -> None:
        self._events.append(event)

    def precision(self) -> float | None:
        if not self._events:
            return None
        passed = sum(1 for e in self._events if e.passed)
        return passed / len(self._events)

    def should_demote(self) -> tuple[bool, str | None]:
        """Returns (should_demote, reason). No-op if data insufficient."""
        if self._demoted_at:
            return False, None  # already demoted
        if len(self._events) < self.min_samples:
            return False, None
        p = self.precision()
        if p is None or p >= self.floor_precision:
            return False, None
        return True, f"live_precision={p:.2f} below floor {self.floor_precision} over {len(self._events)} samples"

    def demote(self, reason: str) -> None:
        self._demoted_at = datetime.now(timezone.utc).isoformat()
        self._demote_reason = reason

    def status(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "samples": len(self._events),
            "precision": self.precision(),
            "floor": self.floor_precision,
            "demoted": self._demoted_at is not None,
            "demote_reason": self._demote_reason,
        }


def monitor_for(artifact_id: str, **kwargs) -> DriftMonitor:
    return DriftMonitor(artifact_id=artifact_id, **kwargs)


if __name__ == "__main__":
    # Self-check: simulate an artifact losing precision → should_demote triggers
    from datetime import timedelta

    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    m = monitor_for("cost_calculator_v2", floor_precision=0.6, min_samples=5)

    # 8 events: 5 pass, 3 fail → precision = 0.625 → above floor (no demote)
    for i in range(8):
        m.record(ApplicationEvent(
            artifact_id="cost_calculator_v2",
            passed=(i < 5),
            timestamp=(base + timedelta(days=i)).isoformat(),
            context=f"test_run_{i}",
        ))
    assert m.precision() == 0.625
    demote, reason = m.should_demote()
    assert not demote, f"should not demote at 0.625: {reason}"
    print(f"OK: precision {m.precision():.2f} above floor, no demote")

    # Now 5 fail, 5 pass → 0.5 → below floor → demote
    m2 = monitor_for("prompt_guard_v3", floor_precision=0.6, min_samples=5)
    for i in range(10):
        m2.record(ApplicationEvent(
            artifact_id="prompt_guard_v3",
            passed=(i < 5),
            timestamp=(base + timedelta(days=i)).isoformat(),
            context=f"test_run_{i}",
        ))
    demote, reason = m2.should_demote()
    assert demote, f"should demote at 0.5"
    assert "below floor" in reason
    print(f"OK: precision 0.50 triggers demote: {reason}")

    # After demote, demoting again is idempotent
    m2.demote(reason)
    demote2, _ = m2.should_demote()
    assert not demote2
    print("OK: demote is idempotent")