"""Synthetic PE checks; no held-out payload is opened."""
import hashlib
import json

import numpy as np
import pytest

from scripts.psa_perturb import (compress_offsets, control_offsets, fill_values, nll,
                                 local_median_grid, offsets, pair_seed, perturbed_raster,
                                 offset_seed, prepare_sample, raster_cache, region_ids,
                                 full_fill, replacement_sums, paired_rasters,
                                 control_offsets_sha256, verify_control_offsets,
                                 completed_samples, raster_delta, selected_pixel_map)
from ua_sahi_mal.kisa_xai.representation import encode_interval_binned, raster_sha256
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def synthetic():
    return build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)], overlay=b"SYNTHETIC")


@pytest.mark.parametrize("status, expected_rows, expected_passes, expected_ineligible", [
    ("agreement", 18, 72, 0),
    ("accepted_unknown_fallback", 18, 48, 6),
])
def test_prepare_sample_returns_contiguous_rasters_for_synthetic_pe(
        tmp_path, status, expected_rows, expected_passes, expected_ineligible):
    data = synthetic()
    sample_path = tmp_path / "synthetic.pe"
    sample_path.write_bytes(data)
    side = 16
    original, imap = encode_interval_binned(data, side=side)
    entry = {
        "sample_id": "synthetic.pe", "file_size": len(data), "group": "synthetic",
        "benign_logit": 0.0, "malicious_logit": 1.0, "structure_status": status,
        "budget": {"requested_fraction": 0.1, "intervals": [[0, 2]], "achieved_bytes": 2},
    }
    structure = {"status": status, "structure": {"spans": [
        {"start": 0, "end": len(data), "region": "synthetic"}]}}
    task = ([entry], sample_path, {"sha256": hashlib.sha256(data).hexdigest()},
            {"file_size": str(len(data)), "raster_sha256": raster_sha256(original),
             "map_sha256": imap.map_sha256()}, structure, original.reshape(-1), side,
            ["zero", "local_median", "structure_conditioned_resampling"],
            ["uniform_random_20_repeats", "front_position", "entropy",
             "structure_matched_random_20_repeats"], 2, (5, 5), 42, 1)
    rows, rasters, targets, ineligible = prepare_sample(task)
    assert len(rows) == expected_rows
    assert rasters.shape == (expected_passes, side, side)
    assert rasters.dtype == np.float32
    assert rasters.flags.c_contiguous
    assert len(targets) == expected_passes
    assert ineligible == expected_ineligible
    assert sum(not row["eligible"] for row in rows) == expected_ineligible
    for row in rows:
        assert "control_intervals" not in row and "gradcam_intervals" not in row
        if row["eligible"]:
            assert row["control_offsets_n"] == 2
            assert verify_control_offsets(row, data, np.array([0, 1]),
                                          region_ids(structure["structure"]["spans"], len(data))
                                          if status == "agreement" else None)


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


def test_vectorized_perturbation_matches_original_byte_loop_bitwise():
    data = synthetic()
    side = 16
    regions = region_ids([{"start": 0, "end": 0x200, "region": "headers"},
                          {"start": 0x200, "end": len(data), "region": "section"}], len(data))
    selected = np.array([0, 1, 15, 16, 31, 511, 512, len(data) - 1], dtype=np.int64)

    def original_raster(mode, fill, seed):
        mask = np.zeros(len(data), dtype=bool)
        mask[selected] = True
        change = selected if mode == "deletion" else np.flatnonzero(~mask)
        raw = np.frombuffer(data, dtype=np.uint8)
        values = np.empty(len(change), dtype=np.uint8)
        if fill == "zero":
            values.fill(0)
        elif fill == "structure_conditioned_resampling":
            rng = np.random.default_rng(seed)
            for rid in np.unique(regions[change]):
                destination = np.flatnonzero(regions[change] == rid)
                pool = np.flatnonzero(regions == rid)
                values[destination] = raw[rng.choice(pool, size=len(destination), replace=True)]
        else:
            for j, pos in enumerate(change):
                row, col = divmod(int(pos), side)
                neighbors = [raw[r * side + c] for r in range(max(0, row - 2), row + 3)
                             for c in range(max(0, col - 2), min(side, col + 3)) if r * side + c < len(raw)]
                values[j] = int(np.median(neighbors))
        modified = bytearray(data)
        for pos, value in zip(change, values, strict=True):
            modified[int(pos)] = int(value)
        return encode_interval_binned(modified, side=side)[0]

    for fill in ("zero", "local_median", "structure_conditioned_resampling"):
        for mode in ("deletion", "keep_only"):
            actual = perturbed_raster(data, selected, mode, fill, np.random.default_rng(19),
                                      regions, (5, 5), side)
            assert actual.tobytes() == original_raster(mode, fill, 19).tobytes()


def test_incremental_raster_matches_full_reencoding_for_random_bytes():
    rng = np.random.default_rng(6102)
    side = 8
    for size in (1, 17, 63, 64, 65, 71, 129, 513):
        data = rng.integers(0, 256, size=size, dtype=np.uint8).tobytes()
        cache = raster_cache(data, side)
        regions = np.zeros(size, dtype=np.int16)
        selected = np.sort(rng.choice(size, size=max(1, size // 7), replace=False))
        for mode in ("deletion", "keep_only"):
            for fill in ("zero", "local_median", "structure_conditioned_resampling"):
                seed = 719
                mask = np.zeros(size, dtype=bool)
                mask[selected] = True
                change = selected if mode == "deletion" else np.flatnonzero(~mask)
                values = fill_values(data, change, fill, np.random.default_rng(seed),
                                     regions, (5, 5), side)
                modified = np.frombuffer(data, dtype=np.uint8).copy()
                modified[change] = values
                expected = encode_interval_binned(modified.tobytes(), side=side)[0]
                actual = perturbed_raster(data, selected, mode, fill, np.random.default_rng(seed),
                                          regions, (5, 5), side, cache=cache)
                assert actual.tobytes() == expected.tobytes()


def test_local_median_grid_random_bytes_and_partial_last_row():
    rng = np.random.default_rng(318)
    side = 8
    for size in (1, 7, 8, 9, 17, 31, 55, 57, 63, 64, 65):
        raw = rng.integers(0, 256, size=size, dtype=np.uint8)
        actual = local_median_grid(raw.tobytes(), side, (5, 5))
        expected = []
        for pos in range(size):
            row, col = divmod(pos, side)
            neighbors = [raw[r * side + c] for r in range(max(0, row - 2), row + 3)
                         for c in range(max(0, col - 2), min(side, col + 3))
                         if r * side + c < size]
            expected.append(int(np.median(neighbors)))
        assert actual.tobytes() == np.asarray(expected, dtype=np.uint8).tobytes()


def test_control_offsets_share_seed_across_fills():
    data = synthetic()
    chosen = np.array([0, 3, 16, 500, 520], dtype=np.int64)
    seed = offset_seed(42, "synthetic", .1, "uniform_random_20_repeats", 7)
    offsets_by_fill = [control_offsets("uniform_random_20_repeats", data, len(chosen),
                                     np.random.default_rng(seed), chosen)
                       for _ in ("zero", "local_median", "structure_conditioned_resampling")]
    assert all(np.array_equal(offsets_by_fill[0], item) for item in offsets_by_fill[1:])
    assert pair_seed(42, "synthetic", .1, "zero", "uniform_random_20_repeats", 7) != pair_seed(
        42, "synthetic", .1, "local_median", "uniform_random_20_repeats", 7)


def test_shared_full_file_fill_matches_full_reencoding_bitwise():
    rng = np.random.default_rng(9317)
    side = 8
    for size in (1, 17, 63, 64, 65, 129, 513):
        raw = rng.integers(0, 256, size=size, dtype=np.uint8)
        data = raw.tobytes()
        cache = raster_cache(data, side)
        regions = np.arange(size, dtype=np.int16) % 3
        medians = local_median_grid(data, side, (5, 5))
        selected = [np.sort(rng.choice(size, size=max(1, size // 7), replace=False))
                    for _ in range(2)]
        for fill in ("zero", "local_median", "structure_conditioned_resampling"):
            replacements = full_fill(raw, fill, np.random.default_rng(45), regions, medians)
            fill_sums = replacement_sums(replacements, cache)
            for chosen in selected:
                actual_deletion, actual_keep = paired_rasters(cache, chosen, replacements, side, fill_sums)
                deleted = raw.copy()
                deleted[chosen] = replacements[chosen]
                kept = replacements.copy()
                kept[chosen] = raw[chosen]
                assert actual_deletion.tobytes() == encode_interval_binned(deleted.tobytes(), side=side)[0].tobytes()
                assert actual_keep.tobytes() == encode_interval_binned(kept.tobytes(), side=side)[0].tobytes()


def test_cached_pixel_map_pair_matches_previous_pair_bitwise():
    rng = np.random.default_rng(9403)
    side = 8
    for size in (1, 17, 64, 65, 513):
        raw = rng.integers(0, 256, size=size, dtype=np.uint8)
        cache = raster_cache(raw.tobytes(), side)
        for _ in range(4):
            selected = np.sort(rng.choice(size, size=max(1, size // 5), replace=False))
            pixel_map = selected_pixel_map(cache, selected)
            for _ in range(3):
                replacements = rng.integers(0, 256, size=size, dtype=np.uint8)
                fill_sums = replacement_sums(replacements, cache)
                delta = replacements[selected].astype(np.int64) - raw[selected].astype(np.int64)
                previous = (raster_delta(cache, selected, delta, side),
                            raster_delta(cache, selected, -delta, side, fill_sums))
                actual = paired_rasters(cache, selected, replacements, side, fill_sums, pixel_map)
                assert all(a.tobytes() == b.tobytes() for a, b in zip(actual, previous, strict=True))


def test_completed_samples_accepts_non_sorted_contiguous_blocks(tmp_path):
    output = tmp_path / "perturb.jsonl"
    rows = [{"sample_id": sid, "eligible": True} for sid in ("z", "z", "a", "a", "m")]
    output.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    complete, counts = completed_samples(output, {"a": 2, "m": 2, "z": 2})
    assert complete == {"a", "z"}
    assert counts["samples"] == 2
    assert [json.loads(line)["sample_id"] for line in output.read_text(encoding="utf-8").splitlines()] == ["z", "z", "a", "a"]


def test_control_offset_digest_is_sorted_int64_and_verifiable():
    data = bytes(range(64))
    chosen = np.array([1, 3, 7], dtype=np.int64)
    row = {"eligible": True, "control": "uniform_random_20_repeats", "achieved_bytes": 3,
           "checkpoint_seed": 42, "sample_id": "synthetic", "budget": .1, "repeat": 2}
    positions = control_offsets(row["control"], data, 3,
        np.random.default_rng(offset_seed(42, "synthetic", .1, row["control"], 2)), chosen)
    row["control_offsets_n"] = len(positions)
    row["control_offsets_sha256"] = control_offsets_sha256(positions[::-1])
    assert row["control_offsets_sha256"] == hashlib.sha256(
        np.sort(positions).astype("<i8").tobytes()).hexdigest()
    assert verify_control_offsets(row, data, chosen)
    row["control_offsets_sha256"] = "0" * 64
    assert not verify_control_offsets(row, data, chosen)
