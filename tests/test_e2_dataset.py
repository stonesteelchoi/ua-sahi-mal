"""E2 v3 dataset layer: dominant-tag labels + in-memory tile store (torch-free)."""

from __future__ import annotations

import zlib

import numpy as np
import pytest

from ua_sahi_mal.peatlas import SectionSpec, build_pe
from ua_sahi_mal.sorel.e2_dataset import (
    TILE_ROWS,
    TILE_WIDTH,
    SorelTileStore,
    build_label_set,
    bytes_to_tiles,
    dominant_tag,
    parse_tag_counts,
)
from ua_sahi_mal.sorel.e2_tiles import TILE_BYTES
from ua_sahi_mal.sorel.manifest import ManifestRow
from ua_sahi_mal.sorel.static_stage import NotDisarmedError, StaticOnlyNotAcknowledgedError


def _row(sha: str, split: str, tag_counts: str, role: str = "primary") -> ManifestRow:
    return ManifestRow(sorel_original_sha256=sha, official_split=split, first_seen_timestamp=0.0,
                       tags=";".join(parse_tag_counts(tag_counts)), detection_count=5,
                       selection_seed="s", selection_role=role, tag_counts=tag_counts)


def test_tag_parsing_and_dominant():
    assert parse_tag_counts("adware=3;packed=1") == {"adware": 3, "packed": 1}
    assert parse_tag_counts("") == {}
    assert dominant_tag({"adware": 3, "packed": 1}) == "adware"
    assert dominant_tag({"packed": 2, "adware": 2}) == "adware"   # tie -> frozen TAGS order
    assert dominant_tag({}) is None


def test_label_set_support_floor_other_and_exclusions():
    rows = ([_row(f"a{i:063d}", "train", "adware=5") for i in range(3)]
            + [_row(f"b{i:063d}", "train", "packed=4") for i in range(3)]
            + [_row("c" * 64, "train", "worm=2")]                 # below support -> other
            + [_row("d" * 64, "train", ""),                        # no tag -> label None
               _row("e" * 64, "test", "adware=9"),
               _row("g" * 64, "test", "adware=1", role="reserve")])  # reserve -> not effective
    ls = build_label_set(rows, min_class_support=2)
    assert ls.class_names == ["adware", "packed", "other"]
    train = ls.split("train", trainable_only=True)
    assert len(train) == 7 and sorted({s.label for s in train}) == [0, 1, 2]
    assert next(s for s in ls.samples if s.sorel_original_sha256 == "d" * 64).label is None
    assert not any(s.role == "reserve" for s in ls.samples)
    assert ls.public_summary()["splits"]["train"] == {"n": 8, "trainable": 7}


def test_bytes_to_tiles_ragged_with_validity():
    data = bytes(range(256)) * (TILE_BYTES * 2 // 256) + b"\x07" * (TILE_BYTES // 2)
    bag = bytes_to_tiles(data)
    assert bag.tiles.shape == (3, TILE_ROWS, TILE_WIDTH)
    assert bag.valid_bytes.tolist() == [TILE_BYTES, TILE_BYTES, TILE_BYTES // 2]
    assert bag.tiles[2].reshape(-1)[TILE_BYTES // 2:].max() == 0          # zero padding
    assert np.isclose(bag.valid_fraction()[2], 0.5)


def test_store_cache_and_guards(iso_dir):
    pe = build_pe(sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400, raw_offset=0x400, raw_size=0x400)],
                  overlay=b"\x00" * 60000, disarm=True)
    (iso_dir / ("1" * 64 + ".zlib")).write_bytes(zlib.compress(pe))
    armed = build_pe(sections=[SectionSpec(".text", rva=0x1000, virtual_size=0x400,
                                           raw_offset=0x400, raw_size=0x400)], disarm=False)
    (iso_dir / ("2" * 64 + ".zlib")).write_bytes(zlib.compress(armed))

    store = SorelTileStore(iso_dir, static_only=True, cache_bytes=10 << 20)
    bag = store.get("1" * 64)
    assert bag.n_tiles == 2 and bag.file_size == len(pe)
    assert store.get("1" * 64) is bag and store.cached_count == 1     # cache hit
    with pytest.raises(NotDisarmedError):
        store.get("2" * 64)                                            # armed sample refused
    with pytest.raises(StaticOnlyNotAcknowledgedError):
        SorelTileStore(iso_dir, static_only=False)


def test_excluded_primary_is_not_effective(iso_dir):
    """A primary that 404'd at preflight (exclusion_reason set, replaced from reserve) has no
    artefact on disk and must be dropped by both the label set and the split SHA list."""
    from ua_sahi_mal.sorel.e2_dataset import shas_for_split
    from ua_sahi_mal.sorel.manifest import write_manifest

    good = _row("a" * 64, "train", "adware=3")
    gone = _row("b" * 64, "train", "adware=3")
    gone.exclusion_reason = "preflight:not_found"
    repl = _row("c" * 64, "train", "adware=3", role="replacement")
    reserve = _row("d" * 64, "train", "adware=3", role="reserve")
    ls = build_label_set([good, gone, repl, reserve], min_class_support=1)
    assert {s.sorel_original_sha256 for s in ls.samples} == {"a" * 64, "c" * 64}

    manifest = iso_dir / "m.csv"
    write_manifest(manifest, [good, gone, repl, reserve])
    assert shas_for_split(manifest, "train") == ["a" * 64, "c" * 64]
