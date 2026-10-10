"""A grow-only counter (G-Counter) CRDT, plus helpers for a map of counters.

A G-Counter keeps one non-negative slot per replica. A replica only ever
increments its own slot, and the counter's value is the sum of all slots.
Two counters merge by taking the per-slot maximum. That merge is commutative,
associative and idempotent, so replicas can exchange state in any order, any
number of times, and still converge on the same value.
"""

from __future__ import annotations

from collections.abc import Mapping


class GCounter:
    """State-based grow-only counter."""

    __slots__ = ("_slots",)

    def __init__(self, slots: Mapping[str, int] | None = None) -> None:
        self._slots: dict[str, int] = {}
        for replica, count in (slots or {}).items():
            if count < 0:
                raise ValueError(f"slot {replica!r} cannot be negative: {count}")
            if count:
                self._slots[replica] = int(count)

    def increment(self, replica: str, amount: int = 1) -> None:
        """Add ``amount`` to ``replica``'s own slot."""
        if amount < 1:
            raise ValueError(f"amount must be a positive integer, got {amount}")
        self._slots[replica] = self._slots.get(replica, 0) + amount

    def value(self) -> int:
        """The counter's value: the sum of every replica's slot."""
        return sum(self._slots.values())

    def slot(self, replica: str) -> int:
        """How many increments ``replica`` has contributed."""
        return self._slots.get(replica, 0)

    def slots(self) -> dict[str, int]:
        """A copy of the per-replica slots, zero slots omitted."""
        return dict(self._slots)

    def merge(self, other: GCounter) -> bool:
        """Merge ``other`` into this counter in place.

        Returns True when at least one slot grew.
        """
        changed = False
        for replica, count in other._slots.items():
            if count > self._slots.get(replica, 0):
                self._slots[replica] = count
                changed = True
        return changed

    def copy(self) -> GCounter:
        return GCounter(self._slots)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GCounter):
            return NotImplemented
        return self._slots == other._slots

    def __repr__(self) -> str:
        return f"GCounter({self._slots!r})"


def merge_counters(
    mine: dict[str, GCounter], theirs: Mapping[str, GCounter]
) -> set[str]:
    """Merge a map of counters into ``mine`` in place, key by key.

    Keys missing from ``mine`` are copied over. Returns the keys whose
    counter changed.
    """
    changed: set[str] = set()
    for key, counter in theirs.items():
        if key not in mine:
            mine[key] = counter.copy()
            changed.add(key)
        elif mine[key].merge(counter):
            changed.add(key)
    return changed


def copy_counters(counters: Mapping[str, GCounter]) -> dict[str, GCounter]:
    """A deep copy of a map of counters, safe to ship inside a message."""
    return {key: counter.copy() for key, counter in counters.items()}
