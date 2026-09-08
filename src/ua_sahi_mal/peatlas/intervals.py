"""Half-open interval-union algebra for PEAtlas.

The canonical coordinate of the v3 plan is a *union of half-open file-offset
intervals* ``[start, end)`` (see ``paper/plan/RESEARCH_PLAN_v3.md`` and
``docs/PEATLAS_CONTRACT.md``). This module implements the exact set algebra over
those intervals so that every downstream view (masks, pixels, functions) is a
projection of one authoritative interval union.

Design choices:

- Intervals are half-open ``[start, end)`` with integer bounds and ``end > start``;
  empty intervals are not representable (construction raises ValueError).
- An :class:`IntervalSet` is always kept **normalized**: sorted, pairwise
  disjoint, and with touching intervals merged (``[0, 4)`` and ``[4, 9)`` become
  ``[0, 9)``). This makes equality meaningful and set ops O(n log n) / O(n).
- The algebra is pure and dependency-free; mask conversion is provided for
  interoperability with the existing numpy mask helpers in
  ``ua_sahi_mal.evidence`` without importing numpy here.

This module deliberately knows nothing about PE files, RVAs, or pixels; it is the
shared coordinate primitive those layers build on.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Interval:
    """A single half-open interval ``[start, end)`` with ``end > start``."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if type(self.start) is not int or type(self.end) is not int:
            raise TypeError("interval bounds must be int")
        if self.end <= self.start:
            raise ValueError(f"interval must be non-empty half-open [start, end): got [{self.start}, {self.end})")

    @property
    def length(self) -> int:
        return self.end - self.start

    def contains(self, point: int) -> bool:
        _require_integer(point, "point")
        return self.start <= point < self.end

    def overlaps(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def touches(self, other: Interval) -> bool:
        """True if adjacent or overlapping (so the union is a single interval)."""
        return self.start <= other.end and other.start <= self.end

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"[{self.start}, {self.end})"


def _coerce(item: object) -> Interval:
    if isinstance(item, Interval):
        return item
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return Interval(item[0], item[1])
    raise TypeError(f"cannot interpret {item!r} as an interval")


class IntervalSet:
    """A normalized union of disjoint, merged half-open intervals."""

    __slots__ = ("_intervals",)

    def __init__(self, intervals: Iterable[object] = ()) -> None:
        coerced = [_coerce(x) for x in intervals]
        self._intervals: tuple[Interval, ...] = _normalize(coerced)

    # -- construction -----------------------------------------------------
    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[int, int]]) -> IntervalSet:
        return cls(pairs)

    @classmethod
    def single(cls, start: int, end: int) -> IntervalSet:
        return cls([Interval(start, end)])

    @classmethod
    def empty(cls) -> IntervalSet:
        return cls([])

    # -- inspection -------------------------------------------------------
    @property
    def intervals(self) -> tuple[Interval, ...]:
        return self._intervals

    @property
    def total_length(self) -> int:
        return sum(iv.length for iv in self._intervals)

    @property
    def span(self) -> Interval | None:
        """Smallest single interval covering the whole set, or None if empty."""
        if not self._intervals:
            return None
        return Interval(self._intervals[0].start, self._intervals[-1].end)

    def is_empty(self) -> bool:
        return not self._intervals

    def contains_point(self, point: int) -> bool:
        _require_integer(point, "point")
        # Sets are small in practice; linear scan is fine and dependency-free.
        for iv in self._intervals:
            if iv.contains(point):
                return True
            if iv.start > point:
                break
        return False

    def __iter__(self) -> Iterator[Interval]:
        return iter(self._intervals)

    def __len__(self) -> int:
        return len(self._intervals)

    def __bool__(self) -> bool:
        return bool(self._intervals)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IntervalSet):
            return NotImplemented
        return self._intervals == other._intervals

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "IntervalSet(" + ", ".join(repr(iv) for iv in self._intervals) + ")"

    # -- algebra ----------------------------------------------------------
    def union(self, other: IntervalSet) -> IntervalSet:
        return IntervalSet([*self._intervals, *other._intervals])

    def intersection(self, other: IntervalSet) -> IntervalSet:
        result: list[Interval] = []
        i = j = 0
        a, b = self._intervals, other._intervals
        while i < len(a) and j < len(b):
            lo = max(a[i].start, b[j].start)
            hi = min(a[i].end, b[j].end)
            if lo < hi:
                result.append(Interval(lo, hi))
            if a[i].end <= b[j].end:
                i += 1
            else:
                j += 1
        return IntervalSet(result)

    def difference(self, other: IntervalSet) -> IntervalSet:
        result: list[Interval] = []
        j = 0
        for iv in self._intervals:
            cursor = iv.start
            while j < len(other._intervals) and other._intervals[j].end <= cursor:
                j += 1
            k = j
            while k < len(other._intervals) and other._intervals[k].start < iv.end:
                sub = other._intervals[k]
                if sub.start > cursor:
                    result.append(Interval(cursor, min(sub.start, iv.end)))
                cursor = max(cursor, sub.end)
                if cursor >= iv.end:
                    break
                k += 1
            j = k
            if cursor < iv.end:
                result.append(Interval(cursor, iv.end))
        return IntervalSet(result)

    def clamp(self, start: int, end: int) -> IntervalSet:
        """Intersect with a single window ``[start, end)``."""
        _require_integer(start, "clamp bound")
        _require_integer(end, "clamp bound")
        if end <= start:
            return IntervalSet.empty()
        return self.intersection(IntervalSet.single(start, end))

    def overlaps(self, other: IntervalSet) -> bool:
        return not self.intersection(other).is_empty()

    # -- mask interop -----------------------------------------------------
    def to_mask(self, length: int) -> bytearray:
        """Boolean coverage mask of size ``length`` (1 where covered).

        Intervals are clamped to ``[0, length)``; out-of-range parts are ignored
        here (callers that must flag out-of-range coordinates use the PE atlas
        failure states, not this projection).
        """
        _require_integer(length, "mask length")
        if length < 0:
            raise ValueError("length must be non-negative")
        mask = bytearray(length)
        for iv in self._intervals:
            lo = max(0, iv.start)
            hi = min(length, iv.end)
            if lo < hi:
                mask[lo:hi] = b"\x01" * (hi - lo)
        return mask

    @classmethod
    def from_mask(cls, mask: Iterable[int]) -> IntervalSet:
        """Inverse of :meth:`to_mask`: contiguous truthy runs become intervals."""
        intervals: list[Interval] = []
        run_start: int | None = None
        idx = -1
        for idx, value in enumerate(mask):
            if value:
                if run_start is None:
                    run_start = idx
            elif run_start is not None:
                intervals.append(Interval(run_start, idx))
                run_start = None
        if run_start is not None:
            intervals.append(Interval(run_start, idx + 1))
        return cls(intervals)

    def jaccard(self, other: IntervalSet) -> float:
        """1-D IoU (Jaccard) between two interval unions; 1.0 if both are empty."""
        inter = self.intersection(other).total_length
        union = self.union(other).total_length
        if union == 0:
            return 1.0
        return inter / union


def _normalize(intervals: list[Interval]) -> tuple[Interval, ...]:
    if not intervals:
        return ()
    ordered = sorted(intervals, key=lambda iv: (iv.start, iv.end))
    merged: list[Interval] = [ordered[0]]
    for iv in ordered[1:]:
        last = merged[-1]
        if iv.start <= last.end:  # overlapping or touching -> merge
            if iv.end > last.end:
                merged[-1] = Interval(last.start, iv.end)
        else:
            merged.append(iv)
    return tuple(merged)


def _require_integer(value: int, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be int")
