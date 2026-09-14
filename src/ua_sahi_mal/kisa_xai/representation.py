"""``interval-binned-v1``: whole-file 1x224x224 raster with a pixel <-> file-offset map.

This is the KISA-XAI-v5 input representation (protocol
``KISA_XAI_V5_0_DRAFT.yaml`` -> ``representation``). It is **deliberately not a
lossless byte encoding**: the model sees a fixed 224x224 grayscale image of the
whole file, and every pixel keeps a deterministic half-open file-offset interval
so that model attributions (Grad-CAM) can be projected back to source bytes and
PE structure. The paper wording for this is "deterministic file-offset interval
projection", never "exact byte recovery".

Definitions (``P = 224 * 224 = 50176`` pixels, ``L = file size in bytes``, pixel
index ``p`` is row-major):

* ``L >= P`` (``contiguous_interval_mean_pool``): the file is cut into ``P``
  contiguous half-open intervals ``[floor(p*L/P), floor((p+1)*L/P))``. The
  intervals partition ``[0, L)`` exactly and their lengths differ by at most one.
  The pixel value is the arithmetic mean of the bytes in its interval (exact
  integer sum divided by the length, stored as float32 in ``[0, 255]``).
* ``L < P`` (``nearest_byte_repetition``): pixel ``p`` carries the single source
  byte ``floor(p*L/P)``, i.e. interval ``[b, b+1)``. Consecutive pixels repeat the
  same byte ``floor(P/L)`` or ``ceil(P/L)`` times; every byte is hit at least once
  (the map ``p -> floor(p*L/P)`` is surjective onto ``[0, L)`` when ``P >= L``).
* ``L == 0`` has no representation and raises ``ValueError``.

The rounding is fixed to floor so that the map is a pure function of ``(L, P)``,
so ``map_sha256`` is reproducible from the file size alone and the union of all
pixel intervals is always exactly ``[0, L)``. Both regimes use the same start
formula ``floor(p*L/P)``; only the end differs (partition end vs ``start + 1``).

Invariants checked by :meth:`IntervalBinnedMap.check_invariants` (protocol
``EXPERIMENT_PROTOCOL.md`` section 4):

1. every source offset is covered by at least one pixel interval;
2. every pixel has a non-empty interval inside ``[0, L)``;
3. the union of all pixel intervals equals ``[0, L)``;
4. interval starts are non-decreasing in row-major pixel order.

Budgeted selection (:func:`select_source_bytes_by_budget`) implements protocol
section 8: pixels are ranked by score descending with row-major index as the tie
break; only strictly positive scores are eligible; intervals are accumulated as a
union of *unique* source bytes until the requested byte budget is reached. Because
one pixel can represent several bytes, the last interval may overshoot the budget;
both the requested and the achieved byte counts are recorded, and the last
interval is kept in ``overshoot_interval`` so controls can be matched to the
achieved budget. A sample with no positive score is not dropped: it is returned
with ``cam_empty=True`` and an empty selection.

Sensitivity: for ``L <= P`` the raster is a byte-exact copy (repeated) of the
file, and for ``L`` slightly above ``P`` it is nearly so. Treat rasters as
malware-derived sensitive artifacts (see ``SECURITY.md``); never commit them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any

import numpy as np

from ..peatlas.intervals import Interval, IntervalSet

REPRESENTATION_ID = "interval-binned-v1"
SIDE = 224
PIXELS = SIDE * SIDE
POLICY_MEAN_POOL = "contiguous_interval_mean_pool"
POLICY_NEAREST = "nearest_byte_repetition"
TIE_BREAK_ROW_MAJOR = "score_desc_then_row_major_index"


def _require_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    return int(value)


@dataclass(frozen=True, eq=False)
class IntervalBinnedMap:
    """Per-pixel half-open file-offset intervals for one file of ``file_size`` bytes.

    ``starts``/``ends`` are int64 arrays of length ``pixel_count`` indexed by
    row-major pixel index. The object is immutable; arrays are exposed read-only.
    """

    representation_id: str
    file_size: int
    side: int
    pixel_count: int
    policy: str
    starts: np.ndarray
    ends: np.ndarray

    def __post_init__(self) -> None:
        for name in ("starts", "ends"):
            arr = getattr(self, name)
            if arr.dtype != np.int64 or arr.ndim != 1 or arr.shape[0] != self.pixel_count:
                raise ValueError(f"{name} must be a 1-D int64 array of length {self.pixel_count}")
            arr.setflags(write=False)

    # -- per-pixel access ----------------------------------------------------
    def pixel_interval(self, pixel: int) -> Interval:
        pixel = _require_int(pixel, "pixel")
        if not 0 <= pixel < self.pixel_count:
            raise ValueError(f"pixel {pixel} outside [0, {self.pixel_count})")
        return Interval(int(self.starts[pixel]), int(self.ends[pixel]))

    def pixel_lengths(self) -> np.ndarray:
        return self.ends - self.starts

    @property
    def max_pixel_length(self) -> int:
        return int(self.pixel_lengths().max())

    # -- projections ---------------------------------------------------------
    def pixels_to_bytes(self, pixels: Iterable[int] | IntervalSet) -> IntervalSet:
        """Union of the file-offset intervals of the given pixels.

        ``pixels`` may be an iterable of row-major pixel indices or an
        :class:`IntervalSet` over pixel indices. Out-of-range pixels raise.
        """
        if isinstance(pixels, IntervalSet):
            idx_parts = [np.arange(iv.start, iv.end, dtype=np.int64) for iv in pixels]
            idx = np.concatenate(idx_parts) if idx_parts else np.zeros(0, dtype=np.int64)
        else:
            idx = np.fromiter((_require_int(p, "pixel") for p in pixels), dtype=np.int64)
        if idx.size == 0:
            return IntervalSet.empty()
        if idx.min() < 0 or idx.max() >= self.pixel_count:
            raise ValueError(f"pixel indices must lie in [0, {self.pixel_count})")
        return IntervalSet(zip(self.starts[idx].tolist(), self.ends[idx].tolist(), strict=True))

    def bytes_to_pixels(self, byte_offsets: IntervalSet) -> IntervalSet:
        """Pixels whose interval overlaps any of the given file-offset intervals.

        Returned as an :class:`IntervalSet` over row-major pixel indices. Because
        starts are non-decreasing and intervals are contiguous, the covering pixels
        of one byte interval form one contiguous pixel run.
        """
        out: list[Interval] = []
        for iv in byte_offsets:
            lo = max(0, iv.start)
            hi = min(self.file_size, iv.end)
            if lo >= hi:
                continue
            # first pixel whose end > lo ; one past last pixel whose start < hi
            first = int(np.searchsorted(self.ends, lo, side="right"))
            last = int(np.searchsorted(self.starts, hi, side="left"))
            if first < last:
                out.append(Interval(first, last))
        return IntervalSet(out)

    # -- integrity -----------------------------------------------------------
    def check_invariants(self) -> None:
        """Raise ``AssertionError`` describing the first violated invariant."""
        lengths = self.pixel_lengths()
        if not (lengths >= 1).all():
            raise AssertionError("invariant 2 violated: a pixel has an empty interval")
        if not ((self.starts >= 0).all() and (self.ends <= self.file_size).all()):
            raise AssertionError("invariant 2 violated: a pixel interval leaves [0, file_size)")
        if not (np.diff(self.starts) >= 0).all():
            raise AssertionError("invariant 4 violated: pixel starts are not non-decreasing")
        union = IntervalSet(zip(self.starts.tolist(), self.ends.tolist(), strict=True))
        if union != IntervalSet.single(0, self.file_size):
            raise AssertionError("invariant 1/3 violated: pixel intervals do not cover [0, file_size) exactly")

    def map_sha256(self) -> str:
        """SHA-256 of the canonical little-endian int64 ``starts||ends`` arrays."""
        digest = hashlib.sha256()
        digest.update(self.starts.astype("<i8", copy=False).tobytes())
        digest.update(self.ends.astype("<i8", copy=False).tobytes())
        return digest.hexdigest()

    def metadata(self) -> dict[str, Any]:
        """Manifest fields (no arrays): representation, size, policy and map hash."""
        return {
            "representation_version": self.representation_id,
            "file_size": self.file_size,
            "side": self.side,
            "pixel_count": self.pixel_count,
            "policy": self.policy,
            "max_pixel_length": self.max_pixel_length,
            "map_sha256": self.map_sha256(),
        }


def build_interval_map(file_size: int, *, side: int = SIDE) -> IntervalBinnedMap:
    """Pure function ``(file_size, side) -> IntervalBinnedMap`` (no file access)."""
    file_size = _require_int(file_size, "file_size")
    side = _require_int(side, "side")
    if side < 1:
        raise ValueError("side must be >= 1")
    if file_size < 1:
        raise ValueError(f"{REPRESENTATION_ID} requires at least one source byte (file_size={file_size})")
    pixels = side * side
    p = np.arange(pixels + 1, dtype=np.int64)
    # floor(p * L / P) with exact integer arithmetic (no float rounding).
    boundaries = (p * np.int64(file_size)) // np.int64(pixels)
    starts = boundaries[:-1]
    if file_size >= pixels:
        ends = boundaries[1:]
        policy = POLICY_MEAN_POOL
    else:
        ends = starts + 1
        policy = POLICY_NEAREST
    return IntervalBinnedMap(
        representation_id=REPRESENTATION_ID,
        file_size=file_size,
        side=side,
        pixel_count=pixels,
        policy=policy,
        starts=np.ascontiguousarray(starts, dtype=np.int64),
        ends=np.ascontiguousarray(ends, dtype=np.int64),
    )


def encode_interval_binned(
    data: bytes | bytearray | memoryview, *, side: int = SIDE
) -> tuple[np.ndarray, IntervalBinnedMap]:
    """Encode raw file bytes as a ``(side, side)`` float32 raster plus its interval map.

    The raster value of pixel ``p`` is the exact mean of ``data[start_p:end_p]``
    (exact integer segment sums, then one float division), so the result is
    bit-reproducible across platforms. No resize library is involved.
    """
    view = np.frombuffer(bytes(data) if not isinstance(data, (bytes, bytearray)) else data, dtype=np.uint8)
    imap = build_interval_map(view.size, side=side)
    if imap.policy == POLICY_MEAN_POOL:
        # starts are strictly increasing and ends[i] == starts[i+1]: exact segment sums in one
        # pass. The int64 copy costs 8x the file size in RAM but is ~10x faster than the
        # dtype-casting reduceat or a cumulative sum (measured on 64 MiB: 0.15 s vs 2 s).
        sums = np.add.reduceat(view.astype(np.int64), imap.starts)
    else:
        sums = view[imap.starts].astype(np.int64)
    lengths = imap.ends - imap.starts
    raster = (sums / lengths).astype(np.float32).reshape(side, side)
    raster.setflags(write=False)
    return raster, imap


def raster_sha256(raster: np.ndarray) -> str:
    """SHA-256 of the raster as canonical little-endian float32 bytes, plus its shape."""
    arr = np.ascontiguousarray(raster, dtype="<f4")
    digest = hashlib.sha256()
    digest.update(json.dumps(list(arr.shape)).encode("ascii"))
    digest.update(arr.tobytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class BudgetSelection:
    """Result of projecting a ranked pixel map to a unique-source-byte budget."""

    representation_id: str
    file_size: int
    requested_fraction: float
    requested_bytes: int
    achieved_bytes: int
    achieved_fraction: float
    selected_pixels: tuple[int, ...]
    intervals: IntervalSet
    overshoot_interval: Interval | None
    overshoot_bytes: int
    cam_empty: bool
    positive_pixels_exhausted: bool
    tie_break: str = TIE_BREAK_ROW_MAJOR

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["intervals"] = [[iv.start, iv.end] for iv in self.intervals]
        d["overshoot_interval"] = (
            None if self.overshoot_interval is None else [self.overshoot_interval.start, self.overshoot_interval.end]
        )
        d["selected_pixel_count"] = len(self.selected_pixels)
        d["interval_count"] = len(self.intervals)
        d.pop("selected_pixels")
        return d


def select_source_bytes_by_budget(
    scores: np.ndarray,
    imap: IntervalBinnedMap,
    budget_fraction: float,
) -> BudgetSelection:
    """Rank pixels by score and accumulate unique source bytes up to ``budget_fraction``.

    ``scores`` is a ``(side, side)`` or flat ``(pixel_count,)`` array (e.g. an
    upsampled Grad-CAM). Only strictly positive scores are eligible; ties are broken
    by row-major pixel index. Accumulation stops as soon as the union of selected
    intervals holds at least ``requested_bytes = ceil(budget_fraction * file_size)``
    unique bytes. The requested budget is expressed in *unique source bytes* of the
    original file, never in pixels.
    """
    if not 0.0 < budget_fraction <= 1.0:
        raise ValueError("budget_fraction must be in (0, 1]")
    flat = np.asarray(scores, dtype=np.float64).reshape(-1)
    if flat.shape[0] != imap.pixel_count:
        raise ValueError(f"scores must have {imap.pixel_count} pixels, got {flat.shape[0]}")
    if not np.isfinite(flat).all():
        raise ValueError("scores must be finite")
    # Decimal semantics for the budget (0.1 means exactly one tenth), independent of float error.
    requested_bytes = math.ceil(Fraction(repr(float(budget_fraction))) * imap.file_size)
    requested_bytes = max(1, min(requested_bytes, imap.file_size))

    positive = np.flatnonzero(flat > 0)
    if positive.size == 0:
        return BudgetSelection(
            representation_id=imap.representation_id,
            file_size=imap.file_size,
            requested_fraction=float(budget_fraction),
            requested_bytes=requested_bytes,
            achieved_bytes=0,
            achieved_fraction=0.0,
            selected_pixels=(),
            intervals=IntervalSet.empty(),
            overshoot_interval=None,
            overshoot_bytes=0,
            cam_empty=True,
            positive_pixels_exhausted=True,
        )
    # stable sort on (-score) keeps row-major order among ties
    order = positive[np.argsort(-flat[positive], kind="stable")]

    selected: list[int] = []
    achieved = 0
    last_iv: Interval | None = None
    exhausted = True
    if imap.policy == POLICY_MEAN_POOL:
        # intervals partition the file: unique bytes == sum of selected lengths
        lengths = imap.pixel_lengths()
        for p in order.tolist():
            selected.append(p)
            achieved += int(lengths[p])
            last_iv = imap.pixel_interval(p)
            if achieved >= requested_bytes:
                exhausted = False
                break
    else:
        # nearest repetition: many pixels share one byte; count distinct bytes
        seen = np.zeros(imap.file_size, dtype=bool)
        for p in order.tolist():
            b = int(imap.starts[p])
            selected.append(p)
            if not seen[b]:
                seen[b] = True
                achieved += 1
                last_iv = imap.pixel_interval(p)
            if achieved >= requested_bytes:
                exhausted = False
                break
    intervals = imap.pixels_to_bytes(selected)
    assert intervals.total_length == achieved, "unique-byte accounting mismatch"
    overshoot = max(0, achieved - requested_bytes)
    return BudgetSelection(
        representation_id=imap.representation_id,
        file_size=imap.file_size,
        requested_fraction=float(budget_fraction),
        requested_bytes=requested_bytes,
        achieved_bytes=achieved,
        achieved_fraction=achieved / imap.file_size,
        selected_pixels=tuple(selected),
        intervals=intervals,
        overshoot_interval=last_iv if overshoot > 0 else None,
        overshoot_bytes=overshoot,
        cam_empty=False,
        positive_pixels_exhausted=exhausted,
    )
