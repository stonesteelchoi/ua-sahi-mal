"""Synthetic PE checks; no held-out payload is opened."""
import numpy as np
import pytest

from scripts.psa_perturb import (compress_offsets, control_offsets, fill_values, nll,
                                 offsets, pair_seed, perturbed_raster, region_ids)
from ua_sahi_mal.kisa_xai.representation import encode_interval_binned
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def synthetic():
    return build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)], overlay=b"SYNTHETIC")


def test_matched_budget_and_structure_on_synthetic_pe():
    data = synthetic()
    chosen = np.array([0, 3, 16, 500, 520], dtype=np.int64)
    spans = [{"start": 0, "end": 0x200, "region": "dos_and_pe_headers"},
             {"start": 0x200, "end": len(data), "region": "executable_sections"}]
    regions = region_ids(spans, len(data))
    for control in ("uniform_random_20_repeats", "front_position", "entropy",
                    "structure_matched_random_20_repeats"):
        selected = control_offsets(control, data, len(chosen), np.random.default_rng(42), chosen, regions)
        assert len(selected) == len(chosen)
        assert np.array_equal(offsets(compress_offsets(selected), len(data)), selected)
        if control == "structure_matched_random_20_repeats":
            assert np.array_equal(np.bincount(regions[selected]), np.bincount(regions[chosen]))
    with pytest.raises(ValueError, match="requires agreement"):
        control_offsets("structure_matched_random_20_repeats", data, len(chosen),
                        np.random.default_rng(42), chosen, None)


def test_static_fills_and_reencoding_on_synthetic_pe():
    data = synthetic()
    before = bytes(data)
    selected = np.array([0, 1, 520], dtype=np.int64)
    regions = region_ids([{"start": 0, "end": len(data), "region": "unknown"}], len(data))
    for fill in ("structure_conditioned_resampling", "local_median", "zero"):
        for mode in ("deletion", "keep_only"):
            raster = perturbed_raster(data, selected, mode, fill, np.random.default_rng(7), regions, (5, 5), 16)
            assert raster.shape == (16, 16)
            assert np.isfinite(raster).all()
    assert data == before
    zero = perturbed_raster(data, selected, "deletion", "zero", np.random.default_rng(7), regions, (5, 5), 16)
    modified = bytearray(data)
    for pos in selected:
        modified[pos] = 0
    assert np.array_equal(zero, encode_interval_binned(modified, side=16)[0])
    assert np.array_equal(fill_values(data, selected, "structure_conditioned_resampling",
                                      np.random.default_rng(3), regions, (5, 5), 16),
                          fill_values(data, selected, "structure_conditioned_resampling",
                                      np.random.default_rng(3), regions, (5, 5), 16))
    assert pair_seed(42, "synthetic", .1, "zero", "entropy", 0) == pair_seed(42, "synthetic", .1, "zero", "entropy", 0)
    assert nll(np.array([0.0, 2.0]), 1) < nll(np.array([2.0, 0.0]), 1)


def test_training_transform_is_shared_with_gradcam_input(tmp_path):
    torch = pytest.importorskip("torch")
    from scripts.psa_train import RasterDataset, preprocess_raster
    data = np.arange(224 * 224, dtype=np.float32).reshape(1, -1) % 256
    path = tmp_path / "rasters.npy"
    np.save(path, data)
    trained, label = RasterDataset(str(path), [0], [1])[0]
    inferred = preprocess_raster(data[0])
    assert label == 1
    assert torch.equal(trained, inferred)
    assert trained.shape == (1, 224, 224)
