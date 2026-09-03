"""Synthetic control construction, corpus bookkeeping, statistics, and the decision table."""

from __future__ import annotations

import json

import numpy as np
import pytest

from ua_sahi_mal.evidence import corpus, criteria, metrics, protocol, routing, synthetic

# ---------------------------------------------------------------------------
# synthetic control set
# ---------------------------------------------------------------------------


def family_bytes(size, *, low, high, seed):
    rng = np.random.default_rng(seed)
    return rng.integers(low, high, size=size, dtype=np.uint8)


def test_graft_replaces_in_place_and_keeps_the_host_length():
    host = family_bytes(100_000, low=0, high=64, seed=0)
    donor = family_bytes(100_000, low=192, high=256, seed=1)
    grafted, piece = synthetic.graft(host, donor, start=8192, length=4096)

    assert grafted.size == host.size
    np.testing.assert_array_equal(grafted[8192:12288], piece)
    np.testing.assert_array_equal(grafted[:8192], host[:8192])
    np.testing.assert_array_equal(grafted[12288:], host[12288:])


def test_graft_that_does_not_fit_is_refused():
    host = family_bytes(10_000, low=0, high=64, seed=0)
    donor = family_bytes(10_000, low=0, high=64, seed=1)
    with pytest.raises(ValueError, match="does not fit"):
        synthetic.graft(host, donor, start=9000, length=4096)


def test_a_donor_whose_seam_gives_it_away_is_rejected():
    host = np.zeros(200_000, dtype=np.uint8)  # entropy 0
    donor = family_bytes(200_000, low=0, high=256, seed=1)  # entropy 8
    with pytest.raises(synthetic.DonorRejected, match="seam entropy"):
        synthetic.build_sample(
            host=host,
            host_id="h",
            host_label=0,
            donor=donor,
            donor_id="d",
            donor_label=1,
            start=8192,
            length=16384,
            kind=synthetic.POSITIVE,
            query_label=1,
        )


def test_matched_pair_shares_host_offset_and_length():
    host = family_bytes(400_000, low=0, high=256, seed=0)
    pool = synthetic.DonorPool.from_items(
        [
            ("d0a", 0, family_bytes(400_000, low=0, high=256, seed=10)),
            ("d1a", 1, family_bytes(400_000, low=0, high=256, seed=11)),
        ]
    )
    positive, negative = synthetic.build_pair(
        host=host, host_id="h", host_label=0, pool=pool, rng=np.random.default_rng(0)
    )

    assert positive.injection == negative.injection
    assert positive.is_positive and not negative.is_positive
    assert positive.donor_label != positive.host_label
    assert negative.donor_label == negative.host_label
    assert positive.query_label == negative.query_label  # both asked the same question


def test_control_set_round_trips_through_disk(tmp_path):
    host = family_bytes(400_000, low=0, high=256, seed=0)
    pool = synthetic.DonorPool.from_items(
        [
            ("d0a", 0, family_bytes(400_000, low=0, high=256, seed=10)),
            ("d1a", 1, family_bytes(400_000, low=0, high=256, seed=11)),
        ]
    )
    samples, rejections = synthetic.build_control_set(
        [("h", 0, host)], pool, seed=0
    )
    assert len(samples) == 2 and not rejections

    manifest = synthetic.save_control_set(samples, rejections, tmp_path, save_rasters=False)
    restored, document = synthetic.load_control_set(tmp_path)

    assert document["positives"] == 1 and document["negatives"] == 1
    assert "not executable" in document["safety"]
    np.testing.assert_array_equal(restored[0].data, samples[0].data)
    assert json.loads(manifest.read_text(encoding="utf-8"))["count"] == 2


def test_control_set_records_rejected_hosts_instead_of_hiding_them():
    pool = synthetic.DonorPool.from_items(
        [("d1a", 1, family_bytes(400_000, low=0, high=256, seed=11))]
    )
    samples, rejections = synthetic.build_control_set(
        [("tiny", 0, family_bytes(1000, low=0, high=256, seed=0))], pool, seed=0
    )
    assert not samples
    assert rejections and "too short" in rejections[0]["reason"]


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def test_labels_are_shifted_to_zero_based(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text('"Id","Class"\n"aaa",1\n"bbb",9\n', encoding="utf-8")
    labels = corpus.read_labels(path)
    assert labels == {"aaa": 0, "bbb": 8}


def test_out_of_range_class_is_refused(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text('"Id","Class"\n"aaa",12\n', encoding="utf-8")
    with pytest.raises(ValueError, match="outside the documented range"):
        corpus.read_labels(path)


def test_stratified_selection_caps_large_families_and_keeps_small_ones_whole():
    labels = {f"big{i}": 0 for i in range(500)}
    labels.update({f"small{i}": 1 for i in range(7)})
    selection = corpus.stratified_selection(labels, per_family=100, seed=0)

    counts = {label: sum(1 for value in selection.values() if value == label) for label in (0, 1)}
    assert counts == {0: 100, 1: 7}


def test_stratified_selection_is_reproducible_from_the_seed():
    labels = {f"s{i}": i % 3 for i in range(300)}
    first = corpus.stratified_selection(labels, per_family=10, seed=42)
    second = corpus.stratified_selection(labels, per_family=10, seed=42)
    third = corpus.stratified_selection(labels, per_family=10, seed=43)
    assert first == second
    assert first != third


def test_split_follows_content_so_a_renamed_duplicate_cannot_straddle():
    digest = corpus.content_hash(np.arange(100, dtype=np.uint8))
    assert corpus.assign_split(digest) == corpus.assign_split(digest)


def test_splits_land_in_roughly_the_requested_proportions():
    splits = [
        corpus.assign_split(corpus.content_hash(np.array([index], dtype=np.uint8) * 7))
        for index in range(255)
    ]
    train_share = splits.count(corpus.SPLIT_TRAIN) / len(splits)
    assert 0.6 < train_share < 0.8


def test_conversion_drops_duplicates_and_records_them(tmp_path):
    body = " ".join(f"{value % 256:02X}" for value in range(16))
    lines = [f"{0x401000 + 16 * row:08X} {body}" for row in range(8192)]
    for name in ("aaa", "bbb"):
        (tmp_path / f"{name}.bytes").write_text("\r\n".join(lines), encoding="latin-1")

    report = corpus.convert_dumps(
        sorted(tmp_path.glob("*.bytes")),
        {"aaa": 0, "bbb": 0},
        tmp_path / "rasters",
        min_bytes=1024,
    )
    assert len(report.converted) == 1
    assert report.duplicates and report.duplicates[0]["duplicate_of"] == "aaa"


def test_manifest_round_trips(tmp_path):
    entry = corpus.CorpusEntry(
        sample_id="aaa",
        label=3,
        split=corpus.SPLIT_TRAIN,
        byte_count=100_000,
        valid_fraction=0.99,
        content_sha256="deadbeef",
        raster_path="aaa.png",
    )
    report = corpus.ConversionReport(converted=[entry], duplicates=[], failures=[])
    path = corpus.write_manifest(report, tmp_path / "manifest.json", per_family=200, seed=0)
    entries, document = corpus.read_manifest(path)

    assert entries == [entry]
    assert document["per_family_cap"] == 200
    assert document["family_split_counts"]["3"]["train"] == 1


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def test_three_seed_interval_uses_the_exact_t_coefficient():
    assert metrics.T_CRITICAL_95[3] == pytest.approx(4.302653, abs=1e-6)
    interval = metrics.mean_interval_t([1.0, 1.1, 0.9])
    assert interval.estimate == pytest.approx(1.0)
    assert interval.low < 1.0 < interval.high


def test_paired_bootstrap_detects_a_consistent_difference():
    treatment = [1.0, 1.2, 1.1, 1.3, 1.15] * 10
    control = [0.2, 0.25, 0.15, 0.3, 0.22] * 10
    interval = metrics.paired_bootstrap_difference(treatment, control, seed=0)
    assert interval.estimate > 0.8
    assert interval.excludes_zero


def test_paired_bootstrap_does_not_claim_a_difference_that_is_not_there():
    rng = np.random.default_rng(0)
    values = rng.normal(0, 1, 60)
    interval = metrics.paired_bootstrap_difference(values, values + rng.normal(0, 1e-9, 60), seed=0)
    assert not interval.excludes_zero or abs(interval.estimate) < 1e-6


def test_kendall_tau_is_one_for_identical_rankings_and_negative_when_reversed():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert metrics.kendall_tau(values, values) == pytest.approx(1.0)
    assert metrics.kendall_tau(values, values[::-1]) == pytest.approx(-1.0)


def test_evidence_recall_ignores_blocks_that_helped_the_classifier():
    deltas = [1.0, -5.0, 2.0, 0.0]
    assert metrics.evidence_mass(deltas) == pytest.approx(3.0)
    assert metrics.evidence_recall_at_budget(deltas, [0, 2]) == pytest.approx(1.0)
    assert metrics.evidence_recall_at_budget(deltas, [1, 3]) == pytest.approx(0.0)


def test_evidence_recall_is_not_a_number_when_there_is_no_evidence_to_recall():
    assert np.isnan(metrics.evidence_recall_at_budget([0.0, -1.0], [0]))


def test_top_k_breaks_ties_by_index_so_runs_are_reproducible():
    assert metrics.top_k_indices([1.0, 1.0, 1.0, 0.0], 2).tolist() == [0, 1]


def test_byte_iou_matches_the_hand_computed_value():
    assert metrics.byte_iou([(0, 100)], [(50, 150)], 1000) == pytest.approx(50 / 150)
    assert metrics.byte_iou([(0, 100)], [(200, 300)], 1000) == 0.0


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------


def test_budget_size_never_rounds_down_to_nothing():
    assert routing.budget_size(10, 1 / 16) == 1
    assert routing.budget_size(160, 1 / 16) == 10
    assert routing.budget_size(5, 1.0) == 5


def test_upsamplers_all_reach_the_requested_length():
    coarse = np.array([0.0, 1.0, 0.25])
    guide = np.linspace(0, 1, 12)
    for method in (routing.UPSAMPLE_NEAREST, routing.UPSAMPLE_LINEAR, routing.UPSAMPLE_JBU):
        assert routing.upsample(coarse, 12, method, guide).shape == (12,)


def test_nearest_upsampling_preserves_the_coarse_values_exactly():
    coarse = np.array([0.0, 1.0, 0.25])
    assert set(np.unique(routing.upsample_nearest(coarse, 12))) == {0.0, 1.0, 0.25}


def test_jbu_follows_the_guide_at_a_sharp_boundary():
    coarse = np.array([0.0, 1.0])
    guide = np.concatenate([np.zeros(8), np.ones(8)])
    result = routing.upsample_jbu(coarse, 16, guide, sigma_range=0.05)
    assert result[:8].mean() < 0.25
    assert result[8:].mean() > 0.75


def test_ua_refuses_rather_than_quietly_substituting_another_method():
    with pytest.raises(routing.UpsamplerUnavailable, match="CUDA"):
        routing.upsample(np.array([0.0, 1.0]), 8, routing.UPSAMPLE_UA, np.zeros(8))


def test_entropy_guide_is_high_for_noise_and_low_for_padding():
    rng = np.random.default_rng(0)
    data = np.concatenate([rng.integers(0, 256, 4096, dtype=np.uint8), np.zeros(4096, np.uint8)])
    guide = routing.block_entropy_guide(data, 4096)
    assert guide[0] > 0.95 and guide[1] == 0.0


# ---------------------------------------------------------------------------
# decision table
# ---------------------------------------------------------------------------


def test_thresholds_match_the_pre_registered_plan():
    assert criteria.BYTE_IOU_FLOOR == 0.50
    assert criteria.KENDALL_TAU_FLOOR == 0.60
    assert criteria.EVIDENCE_RECALL_FLOOR == 0.70
    assert criteria.UA_MARGIN_POINTS == 3.0
    assert criteria.PRIMARY_BUDGET == pytest.approx(1 / 16)
    assert criteria.PRIMARY_BLOCK_BYTES == 4096


def test_paper_stands_when_the_three_critical_criteria_pass():
    table = criteria.assemble(
        [
            criteria.d1_synthetic_iou(0.61),
            criteria.d2_cross_model(0.4, 0.1),
            criteria.d3_cross_representation(0.3, 0.05),
            criteria.d4_fill_agreement(0.72),
            criteria.d5_evidence_recall(0.81),
            criteria.d6_upsampler_margin(None, measured=False),
        ]
    )
    assert table["paper_standing"] == "supported"
    assert table["failed"] == []
    assert table["unmeasured"] == ["D6"]
    assert table["title_keeps_ua"] is False


def test_a_failing_critical_criterion_is_reported_not_absorbed():
    table = criteria.assemble(
        [
            criteria.d1_synthetic_iou(0.20),
            criteria.d2_cross_model(0.4, 0.1),
            criteria.d3_cross_representation(0.02, -0.01),
            criteria.d4_fill_agreement(0.72),
            criteria.d5_evidence_recall(0.40),
            criteria.d6_upsampler_margin(1.0),
        ]
    )
    assert table["paper_standing"] == "not-supported"
    assert table["failed"] == ["D1", "D3", "D5", "D6"]


def test_a_confidence_interval_touching_zero_does_not_count_as_a_pass():
    assert criteria.d2_cross_model(0.5, -0.01).passed is False
    assert criteria.d2_cross_model(0.5, 0.01).passed is True


def test_decision_table_is_assembled_from_stage_summaries():
    calibration = protocol.StageResult(name="c", summary={"mean_byte_iou_positive": 0.66})
    ablation = protocol.StageResult(
        name="a",
        summary={
            "arms": [
                {"router": routing.ROUTE_COARSE, "upsampler": routing.UPSAMPLE_LINEAR, "mean_evidence_recall": 0.78},
                {"router": routing.ROUTE_ENTROPY, "upsampler": None, "mean_evidence_recall": 0.55},
            ]
        },
    )
    cross = protocol.StageResult(
        name="x",
        summary={
            "models": {
                "thumbnail": {"difference": {"estimate": 0.4, "low": 0.1}},
                "text": {"difference": {"estimate": 0.2, "low": 0.05}},
            }
        },
    )
    agreement = protocol.StageResult(name="f", summary={"mean_kendall_tau": 0.68})

    table = protocol.build_decision_table(
        calibration=calibration, ablation=ablation, cross=cross, agreement=agreement
    )
    assert table["paper_standing"] == "supported"
    observed = {row["key"]: row["observed"] for row in table["criteria"]}
    assert observed["D1"] == pytest.approx(0.66)
    assert observed["D5"] == pytest.approx(0.78)
    assert observed["D6"] is None
