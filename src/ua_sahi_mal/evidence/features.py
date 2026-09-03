"""Turn a byte array into the three representations the classifiers consume.

Three representations exist because the protocol needs them to disagree
independently (research plan v2 §2):

``tiles``
    Fixed-size crops at native byte resolution.  Classifier A reads these.  A
    4 KB occlusion changes exactly one tile, so re-scoring a masked candidate
    costs one tile forward pass instead of a whole-sample pass.

``thumbnail``
    The whole sample area-averaged into a fixed square.  Classifier B reads
    this.  It is the standard malware-image representation and, crucially, it
    is *not* how A sees the file: a range that only A needs will not survive
    here.

``text``
    Byte histogram plus hashed byte bigrams -- no image at all.  Classifier
    C_text reads this, and it is what answers "is the evidence an artifact of
    rasterizing?".

None of these functions disassembles, imports, loads, or executes anything.
"""

from __future__ import annotations

import numpy as np

DEFAULT_WIDTH = 512
DEFAULT_TILE_ROWS = 512
"""512 rows x 512 bytes = one 256 KB tile."""

DEFAULT_THUMBNAIL = 256
BIGRAM_BUCKETS = 1024
TEXT_FEATURE_DIM = 256 + BIGRAM_BUCKETS


def tile_bytes(tile_rows: int = DEFAULT_TILE_ROWS, width: int = DEFAULT_WIDTH) -> int:
    return tile_rows * width


def tile_count(byte_count: int, *, tile_rows: int = DEFAULT_TILE_ROWS, width: int = DEFAULT_WIDTH) -> int:
    span = tile_bytes(tile_rows, width)
    return max(1, (byte_count + span - 1) // span)


def tile_byte_ranges(
    byte_count: int, *, tile_rows: int = DEFAULT_TILE_ROWS, width: int = DEFAULT_WIDTH
) -> np.ndarray:
    """``(n, 2)`` array of ``[start, end)`` byte ranges, one per tile."""
    span = tile_bytes(tile_rows, width)
    n = tile_count(byte_count, tile_rows=tile_rows, width=width)
    starts = np.arange(n, dtype=np.int64) * span
    ends = np.minimum(starts + span, byte_count)
    return np.stack([starts, ends], axis=1)


def tiles_touched(
    ranges: np.ndarray, *, tile_rows: int = DEFAULT_TILE_ROWS, width: int = DEFAULT_WIDTH
) -> np.ndarray:
    """Indices of the tiles any of ``ranges`` overlaps."""
    array = np.asarray(ranges, dtype=np.int64).reshape(-1, 2)
    if array.size == 0:
        return np.zeros(0, dtype=np.int64)
    span = tile_bytes(tile_rows, width)
    first = array[:, 0] // span
    last = (array[:, 1] - 1) // span
    touched = {int(t) for lo, hi in zip(first, last, strict=False) for t in range(int(lo), int(hi) + 1)}
    return np.asarray(sorted(touched), dtype=np.int64)


def to_tiles(
    data: np.ndarray, *, tile_rows: int = DEFAULT_TILE_ROWS, width: int = DEFAULT_WIDTH
) -> np.ndarray:
    """``(n_tiles, tile_rows, width)`` uint8 view, zero-padded at the end."""
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    span = tile_bytes(tile_rows, width)
    n = tile_count(data.size, tile_rows=tile_rows, width=width)
    padded = np.zeros(n * span, dtype=np.uint8)
    padded[: data.size] = data
    return padded.reshape(n, tile_rows, width)


def _area_resample(rows: np.ndarray, target: int) -> np.ndarray:
    """Area-average ``rows`` (2-D, float) along axis 0 down or up to ``target``."""
    source = rows.shape[0]
    if source == target:
        return rows
    if source > target:
        edges = np.linspace(0, source, target + 1)
        cumulative = np.concatenate([np.zeros((1, rows.shape[1])), np.cumsum(rows, axis=0)])
        lower = np.floor(edges[:-1]).astype(np.int64)
        upper = np.ceil(edges[1:]).astype(np.int64)
        upper = np.maximum(upper, lower + 1)
        upper = np.minimum(upper, source)
        totals = cumulative[upper] - cumulative[lower]
        counts = (upper - lower).astype(np.float64)[:, None]
        return totals / counts
    index = np.minimum((np.arange(target) * source) // target, source - 1)
    return rows[index]


def thumbnail(
    data: np.ndarray,
    *,
    width: int = DEFAULT_WIDTH,
    size: int = DEFAULT_THUMBNAIL,
) -> np.ndarray:
    """Whole sample as a ``size`` x ``size`` float32 image in ``[0, 1]``.

    Both axes are area-averaged, so a masked range still moves the pixels it
    falls in -- weakly for a large file, which is exactly the sensitivity the
    experiment is meant to quantify rather than assume away.
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    height = max(1, (data.size + width - 1) // width)
    padded = np.zeros(height * width, dtype=np.uint8)
    padded[: data.size] = data
    image = padded.reshape(height, width).astype(np.float64)

    rows = _area_resample(image, size)
    columns = _area_resample(rows.T, size).T
    return (columns / 255.0).astype(np.float32)


def text_features(data: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
    """Byte histogram plus hashed bigrams, L1-normalized, as float32.

    Deliberately blind to the raster: this is the representation that decides
    whether an evidence range is information in the file or an artifact of
    turning the file into a picture.
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    values = data if valid is None else data[valid]
    unigram = np.bincount(values, minlength=256).astype(np.float64)
    total = unigram.sum()
    unigram = unigram / total if total > 0 else np.full(256, 1.0 / 256.0)

    if values.size >= 2:
        pairs = (values[:-1].astype(np.int32) << 8) | values[1:].astype(np.int32)
        buckets = np.bincount(pairs % BIGRAM_BUCKETS, minlength=BIGRAM_BUCKETS).astype(np.float64)
        bigram_total = buckets.sum()
        bigram = buckets / bigram_total if bigram_total > 0 else np.zeros(BIGRAM_BUCKETS)
    else:
        bigram = np.zeros(BIGRAM_BUCKETS, dtype=np.float64)

    return np.concatenate([unigram, bigram]).astype(np.float32)


def row_statistics(data: np.ndarray, *, width: int = DEFAULT_WIDTH) -> np.ndarray:
    """``(height, 3)`` float32: per-row mean, Shannon entropy, distinct-byte ratio.

    Used for the routing score and as the guidance channel that the boundary
    experiment showed to matter (entropy separates regions, raw byte value does
    not -- ``docs/results/big2015/guide_discriminability.json``).
    """
    if data.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {data.dtype}")
    height = max(1, (data.size + width - 1) // width)
    padded = np.zeros(height * width, dtype=np.uint8)
    padded[: data.size] = data
    rows = padded.reshape(height, width)

    offsets = (np.arange(height, dtype=np.int64) * 256)[:, None]
    counts = np.bincount((rows.astype(np.int64) + offsets).reshape(-1), minlength=height * 256)
    counts = counts.reshape(height, 256).astype(np.float64)

    probabilities = counts / float(width)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(probabilities > 0, probabilities * np.log2(probabilities), 0.0)
    entropy = -terms.sum(axis=1)
    distinct = (counts > 0).sum(axis=1) / 256.0
    mean = rows.mean(axis=1) / 255.0

    return np.stack([mean, entropy / 8.0, distinct], axis=1).astype(np.float32)
