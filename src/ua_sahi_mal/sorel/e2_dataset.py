"""E2 v3 dataset layer: labels from the isolated manifest + an in-memory tile store.

Supervision (``E2_prereg_v3``) is the SOREL **dominant behavior tag** — the
argmax of the 11 per-tag detection counts recorded in the private manifest — and
never the silver evidence, so a learned selector evaluated against silver is not
circular. Classes are the tags with at least ``min_class_support`` training
samples; the rest collapse to ``other``; no-tag samples get ``label=None`` and
are excluded from training (they may still be localization-evaluated).

:class:`SorelTileStore` turns an isolated ``<sha>.zlib`` into fixed-size tiles
entirely in memory: decompress, verify the disarming (refuse otherwise), zero-pad
the ragged final tile, and report each tile's number of *valid* bytes so
downstream code can ignore padding (the audit issue the old BIG2015 store had).
Nothing decompressed is ever written to disk; the optional cache is RAM only.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from ua_sahi_mal.sorel.e2_tiles import DEFAULT_GEOMETRY, Geometry
from ua_sahi_mal.sorel.manifest import ManifestRow, read_manifest
from ua_sahi_mal.sorel.paths import assert_isolated_binary_dir
from ua_sahi_mal.sorel.replace import effective_rows
from ua_sahi_mal.sorel.select import TAGS
from ua_sahi_mal.sorel.static_stage import NotDisarmedError, StaticOnlyNotAcknowledgedError, verify_disarmed

OTHER_CLASS = "other"
TILE_ROWS = 64
TILE_WIDTH = DEFAULT_GEOMETRY.tile_bytes // TILE_ROWS   # 768 bytes per row (256 px * stride 3)


# --------------------------------------------------------------------------
# labels
# --------------------------------------------------------------------------


def parse_tag_counts(text: str) -> dict[str, int]:
    """``"adware=3;packed=1"`` -> ``{"adware": 3, "packed": 1}`` (empty -> {})."""
    out: dict[str, int] = {}
    for part in (text or "").split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            try:
                out[name.strip()] = int(value)
            except ValueError:
                continue
    return out


def dominant_tag(tag_counts: dict[str, int]) -> str | None:
    """Argmax tag; ties broken by the frozen ``TAGS`` order; ``None`` if no tag."""
    best: str | None = None
    best_count = 0
    for name in TAGS:  # fixed order -> deterministic tie-break
        count = tag_counts.get(name, 0)
        if count > best_count:
            best, best_count = name, count
    return best


@dataclass(frozen=True)
class LabeledSample:
    sorel_original_sha256: str      # private; isolated use only
    split: str                      # train | validation | test
    role: str                       # primary | replacement
    dominant: str | None            # dominant tag name or None
    label: int | None               # class index or None (no tag -> not trainable)


@dataclass
class LabelSet:
    class_names: list[str]
    samples: list[LabeledSample]
    train_support: dict[str, int] = field(default_factory=dict)

    def split(self, name: str, *, trainable_only: bool = False) -> list[LabeledSample]:
        out = [s for s in self.samples if s.split == name]
        return [s for s in out if s.label is not None] if trainable_only else out

    @property
    def class_count(self) -> int:
        return len(self.class_names)

    def public_summary(self) -> dict[str, object]:
        """SHA-free counts for the console / run record."""
        by_split: dict[str, dict[str, int]] = {}
        for s in self.samples:
            d = by_split.setdefault(s.split, {"n": 0, "trainable": 0})
            d["n"] += 1
            d["trainable"] += int(s.label is not None)
        return {"classes": self.class_names, "train_support": self.train_support, "splits": by_split}


def build_label_set(rows: Iterable[ManifestRow], *, min_class_support: int = 150,
                    effective_only: bool = True) -> LabelSet:
    """Dominant-tag classes with a support floor, computed on the TRAIN split only.

    ``effective_only`` keeps exactly the rows that constitute the sample — primary
    or replacement AND not excluded (the canonical ``replace.effective_rows``
    definition). A primary that 404'd at preflight carries ``exclusion_reason`` and
    has no ``.zlib`` on disk, so it must not become a training sample.
    """
    rows = list(rows)
    picked = effective_rows(rows) if effective_only else rows
    dominants = {r.sorel_original_sha256: dominant_tag(parse_tag_counts(r.tag_counts)) for r in picked}

    train_support: dict[str, int] = {t: 0 for t in TAGS}
    for r in picked:
        d = dominants[r.sorel_original_sha256]
        if r.official_split == "train" and d is not None:
            train_support[d] += 1

    kept = [t for t in TAGS if train_support[t] >= min_class_support]
    needs_other = any(train_support[t] > 0 and t not in kept for t in TAGS)
    class_names = kept + ([OTHER_CLASS] if needs_other else [])
    index = {name: i for i, name in enumerate(class_names)}

    samples: list[LabeledSample] = []
    for r in picked:
        d = dominants[r.sorel_original_sha256]
        if d is None:
            label = None
        elif d in index:
            label = index[d]
        else:
            label = index.get(OTHER_CLASS)
        samples.append(LabeledSample(r.sorel_original_sha256, r.official_split, r.selection_role, d, label))
    return LabelSet(class_names=class_names, samples=samples,
                    train_support={t: n for t, n in train_support.items() if n})


def load_label_set(manifest_path: str | Path, **kwargs) -> LabelSet:
    return build_label_set(read_manifest(manifest_path), **kwargs)


def shas_for_split(manifest_path: str | Path, split: str, *, effective_only: bool = True) -> list[str]:
    """Effective SHAs of one official split, in manifest order (private; isolated use).
    Excluded (e.g. 404-replaced) primaries are dropped, matching ``replace.effective_rows``."""
    rows = read_manifest(manifest_path)
    picked = effective_rows(rows) if effective_only else rows
    return [r.sorel_original_sha256 for r in picked if r.official_split == split]


# --------------------------------------------------------------------------
# in-memory tile store
# --------------------------------------------------------------------------


@dataclass
class TileBag:
    """One file as tiles. ``tiles[i]`` is ``(TILE_ROWS, TILE_WIDTH)`` uint8, zero-padded;
    ``valid_bytes[i]`` says how many leading bytes of tile ``i`` are real."""

    tiles: np.ndarray            # (n_tiles, TILE_ROWS, TILE_WIDTH) uint8
    valid_bytes: np.ndarray      # (n_tiles,) int64
    file_size: int

    @property
    def n_tiles(self) -> int:
        return int(self.tiles.shape[0])

    @property
    def nbytes(self) -> int:
        return int(self.tiles.nbytes)

    def valid_fraction(self) -> np.ndarray:
        return self.valid_bytes / float(self.tiles.shape[1] * self.tiles.shape[2])


def bytes_to_tiles(data: bytes | np.ndarray, *, geom: Geometry = DEFAULT_GEOMETRY,
                   tile_rows: int = TILE_ROWS) -> TileBag:
    """Reshape a byte buffer into ``tile_bytes`` tiles (ragged last tile zero-padded)."""
    array = np.frombuffer(data, dtype=np.uint8) if isinstance(data, (bytes, bytearray, memoryview)) else data
    if array.dtype != np.uint8:
        raise TypeError(f"data must be uint8, got {array.dtype}")
    tile_bytes = geom.tile_bytes
    if tile_bytes % tile_rows:
        raise ValueError(f"tile_bytes {tile_bytes} not divisible by tile_rows {tile_rows}")
    width = tile_bytes // tile_rows
    n = geom.tile_count(array.size)
    padded = np.zeros(n * tile_bytes, dtype=np.uint8)
    padded[: array.size] = array
    starts = np.arange(n, dtype=np.int64) * tile_bytes
    valid = np.clip(array.size - starts, 0, tile_bytes)
    return TileBag(tiles=padded.reshape(n, tile_rows, width), valid_bytes=valid, file_size=int(array.size))


class SorelTileStore:
    """Static-only, in-memory access to tiles of isolated ``<sha>.zlib`` artefacts.

    * refuses to construct without ``static_only=True``;
    * refuses a directory inside the repo or a sync folder;
    * refuses (raises :class:`NotDisarmedError`) any sample that is not disarmed;
    * caches decoded :class:`TileBag`s in RAM up to ``cache_bytes`` (FIFO), never on disk.
    """

    def __init__(self, compressed_dir: str | Path, *, static_only: bool, geom: Geometry = DEFAULT_GEOMETRY,
                 tile_rows: int = TILE_ROWS, cache_bytes: int = 8 << 30) -> None:
        if not static_only:
            raise StaticOnlyNotAcknowledgedError("SorelTileStore decompresses in memory; static_only=True required")
        self.root = assert_isolated_binary_dir(compressed_dir)
        self.geom = geom
        self.tile_rows = tile_rows
        self.cache_bytes = int(cache_bytes)
        self._cache: dict[str, TileBag] = {}
        self._cache_order: list[str] = []
        self._cached_bytes = 0

    def path_for(self, sha256: str) -> Path:
        return self.root / f"{sha256}.zlib"

    def decode(self, sha256: str) -> TileBag:
        """Decompress + verify + tile, bypassing the cache."""
        compressed = self.path_for(sha256).read_bytes()
        data = zlib.decompress(compressed)
        try:
            if not verify_disarmed(data):
                raise NotDisarmedError("sample is not disarmed (Machine/Subsystem != 0); refusing")
            return bytes_to_tiles(data, geom=self.geom, tile_rows=self.tile_rows)
        finally:
            del data  # scrub the decompressed buffer reference

    def get(self, sha256: str) -> TileBag:
        bag = self._cache.get(sha256)
        if bag is not None:
            return bag
        bag = self.decode(sha256)
        self._remember(sha256, bag)
        return bag

    def _remember(self, sha256: str, bag: TileBag) -> None:
        if bag.nbytes > self.cache_bytes:
            return  # too large to cache; served uncached
        while self._cache_order and self._cached_bytes + bag.nbytes > self.cache_bytes:
            oldest = self._cache_order.pop(0)
            self._cached_bytes -= self._cache.pop(oldest).nbytes
        self._cache[sha256] = bag
        self._cache_order.append(sha256)
        self._cached_bytes += bag.nbytes

    @property
    def cached_count(self) -> int:
        return len(self._cache)
