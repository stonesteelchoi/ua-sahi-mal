"""V1.2 shape control checks on synthetic bytes and PE only."""
import hashlib

import numpy as np
import pytest

from scripts.psa_perturb import (ADDENDUM_PASSES, FROZEN_ADDENDUM_SHA256,
                                 filter_addendum_budgets, load_addendum, offset_seed, ordered_sample_blocks, prepare_sample,
                                 raster_slots, region_ids, shape_audit,
                                 shape_matched_offsets, verify_control_offsets)
from ua_sahi_mal.kisa_xai.representation import build_interval_map, encode_interval_binned, raster_sha256
from ua_sahi_mal.peatlas.pebuild import SectionSpec, build_pe


def spans_for(size, cuts=()):
    bounds = [0, *cuts, size]
    return [{"start": a, "end": b, "region": "same"}
            for a, b in zip(bounds[:-1], bounds[1:], strict=True)]


@pytest.mark.parametrize("target_size", [50176, 75000, None])
def test_synthetic_pe_representation_matching(target_size):
    base = build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)],
                    overlay=b"V12")
    size = target_size or len(base)
    data = base + bytes(size - len(base))
    _, imap = encode_interval_binned(data, side=224)
    spans = spans_for(len(data), (min(512, len(data) - 1),))
    regions = region_ids(spans, len(data))
    selected = np.array([1, 2, 3, 510, 511, 512, len(data) - 3, len(data) - 2])
    moved, flags = shape_matched_offsets(selected, regions, imap, spans,
        np.random.default_rng(offset_seed(42, "synthetic.pe", .1, "shape_matched_random", 4)))
    before, after = shape_audit(selected, regions, imap), shape_audit(moved, regions, imap)
    assert before["total_selected_unique_source_bytes"] == after["total_selected_unique_source_bytes"]
    assert before["region_byte_counts"] == after["region_byte_counts"]
    assert before["run_length_multiset"] == flags["placed_run_lengths"]
    assert not flags["placement_fallback"]
    assert before["pixels_intact"] >= 0 and after["pixels_intact"] >= 0
    if target_size == 50176:
        assert before["pixels_intact"] == after["pixels_intact"]


@pytest.mark.parametrize("size", [50176, 75000, 113])
def test_shape_matching_and_determinism(size):
    side = 224
    imap = build_interval_map(size, side=side)
    spans = spans_for(size)
    regions = region_ids(spans, size)
    selected = np.array([1, 2, 3, 20, 21, size - 4, size - 3], dtype=np.int64)
    seed = offset_seed(42, "synthetic", .1, "shape_matched_random", 7)
    first, flags = shape_matched_offsets(selected, regions, imap, spans, np.random.default_rng(seed))
    again, _ = shape_matched_offsets(selected, regions, imap, spans, np.random.default_rng(seed))
    assert np.array_equal(first, again)
    assert len(first) == len(np.unique(first))
    assert {key: flags[key] for key in ("run_split", "placement_fallback", "unplaced_byte_count")} == {
        "run_split": False, "placement_fallback": False, "unplaced_byte_count": 0}
    original, moved = shape_audit(selected, regions, imap), shape_audit(first, regions, imap)
    for key in ("total_selected_unique_source_bytes", "region_byte_counts"):
        assert original[key] == moved[key]
    assert original["run_length_multiset"] == flags["placed_run_lengths"]
    assert 0 <= original["pixels_intact"] <= original["pixels_touched"]
    assert 0 <= moved["pixels_intact"] <= moved["pixels_touched"]


def test_segment_split_and_unplaceable_run():
    size = 12
    imap = build_interval_map(size, side=4)
    spans = spans_for(size, (5, 10))
    regions = region_ids(spans, size)
    selected = np.arange(3, 9, dtype=np.int64)
    moved, flags = shape_matched_offsets(selected, regions, imap, spans, np.random.default_rng(2))
    assert flags["run_split"] is True
    assert flags["placement_fallback"] is False
    assert len(moved) == len(selected)
    assert shape_audit(moved, regions, imap)["region_byte_counts"] == shape_audit(selected, regions, imap)["region_byte_counts"]

    fallback_spans = spans_for(18, (6, 12))
    fallback_regions = region_ids(fallback_spans, 18)
    fallback_selected = np.array([0, 1, 2, 3, 6, 7, 8, 10, 11, 12, 14, 15, 16])
    failed, flags = shape_matched_offsets(fallback_selected, fallback_regions,
        build_interval_map(18, side=4), fallback_spans, np.random.default_rng(14))
    assert flags["placement_fallback"] and flags["unplaced_byte_count"] > 0
    assert len(failed) + flags["unplaced_byte_count"] == len(fallback_selected)


@pytest.mark.parametrize("size,shift,repeat", [(75000, 2, 2), (113, 7, 7)])
def test_pixel_intact_difference_is_measured(size, shift, repeat):
    imap = build_interval_map(size, side=224)
    spans = spans_for(size)
    regions = region_ids(spans, size)
    selected = np.array([1 + shift, 2 + shift, 3 + shift, 20 + shift,
                         21 + shift, size - 4, size - 3])
    seed = offset_seed(42, "synthetic", .1, "shape_matched_random", repeat)
    moved, _ = shape_matched_offsets(selected, regions, imap, spans, np.random.default_rng(seed))
    for arm in (selected, moved):
        audit = shape_audit(arm, regions, imap)
        assert 0 <= audit["pixels_intact"] <= audit["pixels_touched"]


def synthetic_task(tmp_path, status):
    data = build_pe(sections=[SectionSpec(".text", 0x1000, 0x200, 0x200, 0x200)], overlay=b"V12")
    path = tmp_path / "synthetic.pe"
    path.write_bytes(data)
    side = 16
    raster, imap = encode_interval_binned(data, side=side)
    spans = spans_for(len(data))
    entries = [{"sample_id": path.name, "file_size": len(data), "group": "synthetic",
                "benign_logit": 0.0, "malicious_logit": 1.0, "structure_status": status,
                "budget": {"requested_fraction": budget, "intervals": [[0, 4]], "achieved_bytes": 4}}
               for budget in (.1, .2)]
    return (entries, path, {"sha256": hashlib.sha256(data).hexdigest()},
            {"file_size": str(len(data)), "raster_sha256": raster_sha256(raster),
             "map_sha256": imap.map_sha256()},
            {"status": status, "structure": {"spans": spans}}, raster.reshape(-1), side,
            ["structure_conditioned_resampling"], ["shape_matched_random"], 20,
            (5, 5), 42, 1, True)


def test_addendum_filters_four_budget_ledger_before_grouping(tmp_path):
    ledger = []
    tasks = {}
    for name in ("first", "second"):
        folder = tmp_path / name
        folder.mkdir()
        task = list(synthetic_task(folder, "agreement"))
        task[1] = task[1].rename(folder / f"{name}.pe")
        task[0] = [dict(entry, sample_id=task[1].name) for entry in task[0]]
        tasks[task[1].name] = task
        for budget in (.05, .10 + 5e-10, .20, .40):
            for entry in task[0][:1]:
                ledger.append(dict(entry, budget=dict(entry["budget"], requested_fraction=budget)))
    filtered = filter_addendum_budgets(ledger, [.10, .20])
    assert len(filtered) == 4
    assert {row["budget"]["requested_fraction"] for row in filtered} == {.10 + 5e-10, .20}
    for sid, entries in ordered_sample_blocks(filtered, "sample_id"):
        task = tasks[sid]
        with raster_slots(1, task[6], ADDENDUM_PASSES) as slots:
            rows, targets, ineligible, used = prepare_sample((entries, *task[1:], slots[0].name, 0))
        assert len(rows) == 40
        assert used == len(targets) == ADDENDUM_PASSES
        assert ineligible == 0
        assert {row["budget"] for row in rows} == {.10 + 5e-10, .20}


@pytest.mark.parametrize("incomplete", [(.05, .10, .40), (.05, .10, .20, .20, .40)])
def test_addendum_rejects_missing_or_duplicate_budget_per_sample(incomplete):
    ledger = [{"sample_id": sid, "budget": {"requested_fraction": budget}}
              for sid, budgets in (("complete", (.05, .10, .20, .40)),
                                   ("incomplete", incomplete))
              for budget in budgets]
    with pytest.raises(ValueError, match="lacks exactly one row"):
        filter_addendum_budgets(ledger, [.10, .20])


def test_adjacent_placements_record_realized_merge(tmp_path, monkeypatch):
    task = list(synthetic_task(tmp_path, "agreement"))
    task[0] = [dict(entry, budget=dict(entry["budget"], intervals=[[0, 1], [2, 3]],
                                        achieved_bytes=2)) for entry in task[0]]

    def adjacent(*args):
        return np.array([0, 1], dtype=np.int64), {
            "run_split": False, "placement_fallback": False,
            "unplaced_byte_count": 0, "placed_run_lengths": [1, 1]}

    monkeypatch.setattr("scripts.psa_perturb.shape_matched_offsets", adjacent)
    with raster_slots(1, task[6], ADDENDUM_PASSES) as slots:
        rows, _, _, _ = prepare_sample((*task, slots[0].name, 0))
    assert all(row["control_shape"]["n_runs"] == 2 for row in rows)
    assert all(row["control_shape"]["mean_run_len"] == 1.0 for row in rows)
    assert all(row["control_shape"]["run_length_multiset"] == [1, 1] for row in rows)
    assert all(row["control_shape"]["control_realized_n_runs"] == 1 for row in rows)
    assert all(row["control_shape"]["control_realized_mean_run_len"] == 2.0 for row in rows)
    assert all(row["control_shape"]["control_realized_run_length_multiset"] == [2] for row in rows)
    assert all(row["run_length_multiset_match"] is True for row in rows)


@pytest.mark.parametrize("status,passes", [("agreement", ADDENDUM_PASSES),
                                            ("accepted_unknown_fallback", 0)])
def test_forty_rows_and_slot_passes(tmp_path, status, passes):
    task = synthetic_task(tmp_path, status)
    with raster_slots(1, task[6], ADDENDUM_PASSES) as slots:
        rows, targets, ineligible, used = prepare_sample((*task, slots[0].name, 0))
    assert len(rows) == 40
    assert len(targets) == used == passes
    assert ineligible == (0 if passes else 40)
    if passes:
        assert all(row["total_bytes_match"] and row["region_bytes_match"] for row in rows)
        assert all(row["run_length_multiset_match"] is True for row in rows)
        spans = task[4]["structure"]["spans"]
        assert verify_control_offsets(rows[0], task[1].read_bytes(), np.arange(4),
                                      region_ids(spans, int(task[3]["file_size"])),
                                      spans=spans, side=task[6])
    else:
        assert all(row["eligible"] is False and row["structure_ineligible"] for row in rows)


def test_fallback_rows_keep_forward_passes(tmp_path, monkeypatch):
    task = list(synthetic_task(tmp_path, "agreement"))
    size = int(task[3]["file_size"])
    task[4] = {"status": "agreement", "structure": {"spans": [
        {"start": 0, "end": 6, "region": "same"},
        {"start": 6, "end": 12, "region": "same"},
        {"start": 12, "end": 18, "region": "same"},
        {"start": 18, "end": size, "region": "other"}]}}
    task[0] = [dict(entry, budget={"requested_fraction": entry["budget"]["requested_fraction"],
                                    "intervals": [[0, 4], [6, 9], [10, 13], [14, 17]],
                                    "achieved_bytes": 13}) for entry in task[0]]
    monkeypatch.setattr("scripts.psa_perturb.offset_seed", lambda *args: 1)
    with raster_slots(1, task[6], ADDENDUM_PASSES) as slots:
        rows, targets, ineligible, used = prepare_sample((*task, slots[0].name, 0))
    assert len(rows) == 40 and used == len(targets) == ADDENDUM_PASSES and ineligible == 0
    assert all(row["placement_fallback"] and row["unplaced_byte_count"] > 0 for row in rows)
    assert all(not row["total_bytes_match"] for row in rows)


def test_addendum_hash_mismatch_rejected(tmp_path):
    from scripts.psa_perturb import ROOT
    path = ROOT / "paper/v5-kisa-xai/protocol/PSA_XAI_V1_2_ADDENDUM.yaml"
    assert load_addendum(path, FROZEN_ADDENDUM_SHA256)["experiment"]["control"] == "shape_matched_random"
    with pytest.raises(ValueError, match="addendum SHA-256 mismatch"):
        load_addendum(path, "0" * 64)
    altered = tmp_path / "altered.yaml"
    altered.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="addendum SHA-256 mismatch"):
        load_addendum(altered, FROZEN_ADDENDUM_SHA256)
