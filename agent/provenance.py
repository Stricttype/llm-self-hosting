"""
Provenance tagging — prevents self-catalysis in the novelty baseline.
Step 0.5 of the self-improvement loop.

Rule: novelty is measured against HUMAN-generated patterns only.
Loop-generated patterns don't enter the baseline — otherwise the system
measures distance to its own echo, not to actual knowledge.

Ponytail: a tag + a filter, one file, zero deps.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Provenance(str, Enum):
    HUMAN = "human"
    LOOP_GENERATED = "loop-generated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProvenanceTag:
    source: Provenance
    origin_event_id: str | None    # event that produced this artifact, if applicable
    parent_pattern_id: str | None  # if derived from an existing pattern, which one


def human(event_id: str | None = None) -> ProvenanceTag:
    return ProvenanceTag(Provenance.HUMAN, event_id, None)


def from_loop(parent_pattern_id: str | None = None, origin_event_id: str | None = None) -> ProvenanceTag:
    return ProvenanceTag(Provenance.LOOP_GENERATED, origin_event_id, parent_pattern_id)


def is_eligible_for_baseline(tag: ProvenanceTag) -> bool:
    """Return True if this artifact should count toward the novelty baseline.
    Only human-sourced patterns enter the baseline.
    """
    return tag.source == Provenance.HUMAN


if __name__ == "__main__":
    # Self-check
    assert is_eligible_for_baseline(human("evt_001"))
    assert not is_eligible_for_baseline(from_loop(parent_pattern_id="p_abc"))
    print("OK: provenance tagging — human in baseline, loop-generated excluded")