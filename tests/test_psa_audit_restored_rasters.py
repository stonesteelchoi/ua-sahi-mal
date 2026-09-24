"""Synthetic-only tests; no dataset PE payload is opened."""

import hashlib

import numpy as np
import pytest

from scripts.psa_audit_restored_rasters import audit
from ua_sahi_mal.kisa_xai.representation import (
    PIXELS,
    encode_interval_binned,
    raster_sha256,
)


def test_restored_source_matches_existing_raster(tmp_path):
    source_dir = tmp_path / "samples"
    source_dir.mkdir()
    data = b"synthetic-not-a-pe"
    (source_dir / "7").write_bytes(data)
    raster, imap = encode_interval_binned(data)
    path = tmp_path / "rasters.npy"
    array = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(1, PIXELS))
    array[0] = raster.reshape(-1)
    del array
    targets = {"7": (len(data), hashlib.sha256(data).hexdigest())}
    index = {"7": {"row": "0", "split": "train", "label": "1",
                   "file_size": str(len(data)), "policy": imap.policy,
                   "raster_sha256": raster_sha256(raster), "map_sha256": imap.map_sha256()}}

    report = audit(targets, index, source_dir, path)

    assert report["target_count"] == 1
    assert report["counts"]["raster_matches_restored_source_true"] == 1
    assert report["counts"]["index_size_matches_source_true"] == 1


def test_stale_raster_is_reported_without_modification(tmp_path):
    source_dir = tmp_path / "samples"
    source_dir.mkdir()
    data = b"restored-source"
    (source_dir / "7").write_bytes(data)
    original, imap = encode_interval_binned(b"damaged-source")
    path = tmp_path / "rasters.npy"
    array = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(1, PIXELS))
    array[0] = original.reshape(-1)
    del array
    targets = {"7": (len(data), hashlib.sha256(data).hexdigest())}
    index = {"7": {"row": "0", "split": "val", "label": "1",
                   "file_size": "14", "policy": imap.policy,
                   "raster_sha256": raster_sha256(original), "map_sha256": imap.map_sha256()}}

    report = audit(targets, index, source_dir, path)

    assert report["counts"]["raster_matches_restored_source_false"] == 1
    assert report["counts"]["index_size_matches_source_false"] == 1
    assert np.array_equal(np.load(path)[0], original.reshape(-1))


def test_noncanonical_restored_source_rejected(tmp_path):
    source_dir = tmp_path / "samples"
    source_dir.mkdir()
    (source_dir / "7").write_bytes(b"wrong")
    path = tmp_path / "rasters.npy"
    array = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(1, PIXELS))
    del array
    targets = {"7": (5, hashlib.sha256(b"right").hexdigest())}
    index = {"7": {"row": "0", "split": "train", "label": "1"}}

    with pytest.raises(ValueError, match="integrity check"):
        audit(targets, index, source_dir, path)
