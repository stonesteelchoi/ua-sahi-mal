"""Occlusion of byte ranges, and the artifact controls that make it measurable.

Masking changes byte statistics.  If a classifier reacts to the *trace of the
mask* rather than to the *removed information*, every number downstream is
meaningless.  Measurements on real BIG2015 samples (``docs/results/big2015/``)
showed that a constant fill (``0x00``, ``0xCC``) and a uniform random fill both
land outside the sample's own 4 KB block-entropy distribution, while sampling
from the sample's global byte histogram lands inside it.  So the primary fill is
the histogram fill, and the other two exist to show the ranking survives the
choice (pre-registered criterion D4).

Every occlusion also needs a random-location control of the same geometry.
Without it, "masking the candidate range hurts the classifier" cannot be
distinguished from "masking anything hurts the classifier".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

FILL_HISTOGRAM = "histogram"
FILL_ZERO = "zero"
FILL_INT3 = "int3"
FILL_UNIFORM = "uniform"

PRIMARY_FILL = FILL_HISTOGRAM
ROBUSTNESS_FILLS = (FILL_HISTOGRAM, FILL_ZERO, FILL_UNIFORM)
SUPPORTED_FILLS = frozenset({FILL_HISTOGRAM, FILL_ZERO, FILL_INT3, FILL_UNIFORM})


@dataclass(frozen=True)
class FillPlan:
    """How to fill occluded positions for one sample."""

    name: str
    histogram: np.ndarray | None = None  # float64 (256,), only for FILL_HISTOGRAM

    def __post_init__(self) -> None:
        if self.name not in SUPPORTED_FILLS:
            raise ValueError(f"unknown fill {self.name!r}; expected one of {sorted(SUPPORTED_FILLS)}")
        if self.name == FILL_HISTOGRAM:
            if self.histogram is None:
                raise ValueError("histogram fill requires a histogram")
            if self.histogram.shape != (256,):
                raise ValueError(f"histogram must have shape (256,), got {self.histogram.shape}")
            total = float(self.histogram.sum())
            if not np.isfinite(total) or total <= 0:
                raise ValueError("histogram must be finite and sum to a positive value")

    def draw(self, count: int, rng: np.random.Generator) -> np.ndarray:
        """Draw ``count`` fill bytes."""
        if count < 0:
            raise ValueError(f"count must be non-negative, got {count}")
        if count == 0:
            return np.zeros(0, dtype=np.uint8)
        if self.name == FILL_ZERO:
            return np.zeros(count, dtype=np.uint8)
        if self.name == FILL_INT3:
            return np.full(count, 0xCC, dtype=np.uint8)
        if self.name == FILL_UNIFORM:
            return rng.integers(0, 256, size=count, dtype=np.uint8)
        probabilities = np.asarray(self.histogram, dtype=np.float64)
        probabilities = probabilities / probabilities.sum()
        return rng.choice(256, size=count, p=probabilities).astype(np.uint8)


def byte_histogram(data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """Global byte histogram over the valid bytes of a sample."""
    values = data if valid is None else data[valid]
    if values.size == 0:
        # A dump with no valid byte cannot inform a fill; fall back to uniform.
        return np.full(256, 1.0 / 256.0)
    counts = np.bincount(values, minlength=256).astype(np.float64)
    return counts / counts.sum()


def make_fill_plan(name: str, data: np.ndarray, valid: np.ndarray | None = None) -> FillPlan:
    if name == FILL_HISTOGRAM:
        return FillPlan(name=name, histogram=byte_histogram(data, valid))
    return FillPlan(name=name)


def _normalize_ranges(ranges: Iterable[Sequence[int]], byte_count: int) -> np.ndarray:
    array = np.asarray(list(ranges), dtype=np.int64).reshape(-1, 2)
    if array.size == 0:
        return array.reshape(0, 2)
    if (array[:, 0] < 0).any():
        raise ValueError("range starts must be non-negative")
    if (array[:, 1] > byte_count).any():
        raise ValueError(f"range ends must not exceed byte_count {byte_count}")
    if (array[:, 1] <= array[:, 0]).any():
        raise ValueError("every range must be non-empty ([start, end) with end > start)")
    return array


def range_mask(ranges: Iterable[Sequence[int]], byte_count: int) -> np.ndarray:
    """Boolean mask, True where a byte falls inside one of ``ranges``."""
    mask = np.zeros(byte_count, dtype=bool)
    for start, end in _normalize_ranges(ranges, byte_count):
        mask[start:end] = True
    return mask


def occlude(
    data: np.ndarray,
    ranges: Iterable[Sequence[int]],
    plan: FillPlan,
    rng: np.random.Generator,
    *,
    keep_only: bool = False,
) -> np.ndarray:
    """Return a copy of ``data`` with ``ranges`` replaced by fill bytes.

    With ``keep_only=True`` the complement is filled instead: everything outside
    ``ranges`` is masked, which is how sufficiency is measured.
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    mask = range_mask(ranges, data.size)
    if keep_only:
        mask = ~mask
    out = data.copy()
    count = int(mask.sum())
    if count:
        out[mask] = plan.draw(count, rng)
    return out


def random_control_ranges(
    ranges: Iterable[Sequence[int]],
    byte_count: int,
    rng: np.random.Generator,
    *,
    max_attempts: int = 64,
) -> np.ndarray:
    """Same number of ranges, same lengths, placed at random non-overlapping offsets.

    Falls back to allowing overlap if the sample is too short to place them
    disjointly, so the control always exists; the caller can detect this by
    comparing the covered byte count with the requested one.
    """
    array = _normalize_ranges(ranges, byte_count)
    lengths = (array[:, 1] - array[:, 0]).astype(np.int64)
    placed: list[tuple[int, int]] = []
    for length in lengths:
        if length > byte_count:
            raise ValueError(f"range of length {length} does not fit in {byte_count} bytes")
        for _ in range(max_attempts):
            start = int(rng.integers(0, byte_count - length + 1))
            end = start + int(length)
            if all(end <= other_start or start >= other_end for other_start, other_end in placed):
                placed.append((start, end))
                break
        else:
            start = int(rng.integers(0, byte_count - length + 1))
            placed.append((start, start + int(length)))
    return np.asarray(sorted(placed), dtype=np.int64).reshape(-1, 2)


def block_entropy(data: np.ndarray, block_bytes: int) -> np.ndarray:
    """Shannon entropy (bits/byte) of each ``block_bytes``-sized block."""
    if block_bytes <= 0:
        raise ValueError(f"block_bytes must be positive, got {block_bytes}")
    n = data.size // block_bytes
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    blocks = data[: n * block_bytes].reshape(n, block_bytes)
    # bincount per row without a Python loop: offset each row into its own bin range.
    offsets = (np.arange(n, dtype=np.int64) * 256)[:, None]
    counts = np.bincount((blocks.astype(np.int64) + offsets).reshape(-1), minlength=n * 256)
    counts = counts.reshape(n, 256).astype(np.float64)
    probabilities = counts / float(block_bytes)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(probabilities > 0, probabilities * np.log2(probabilities), 0.0)
    return -terms.sum(axis=1)


def fill_is_in_distribution(
    data: np.ndarray,
    plan: FillPlan,
    rng: np.random.Generator,
    *,
    block_bytes: int = 4096,
    low_percentile: float = 5.0,
    high_percentile: float = 95.0,
) -> dict[str, float | bool]:
    """Check whether a filled block's entropy sits inside the sample's own range.

    This is the measurement that chose the histogram fill; keeping it in the
    library lets every run re-verify the choice on its own data instead of
    trusting a number recorded once.
    """
    observed = block_entropy(data, block_bytes)
    if observed.size == 0:
        raise ValueError(f"sample is shorter than one {block_bytes}-byte block")
    filled = plan.draw(block_bytes, rng)
    filled_entropy = float(block_entropy(filled, block_bytes)[0])
    low = float(np.percentile(observed, low_percentile))
    high = float(np.percentile(observed, high_percentile))
    return {
        "fill": plan.name,
        "fill_entropy": filled_entropy,
        "sample_median_entropy": float(np.median(observed)),
        "sample_low": low,
        "sample_high": high,
        "in_distribution": bool(low <= filled_entropy <= high),
    }
