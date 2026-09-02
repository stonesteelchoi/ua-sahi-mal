from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ua_sahi_mal.malevis_experiment import (
    MaleVisExperimentError,
    audit_malevis_dataset,
    build_paired_malevis_manifest,
    classification_metrics,
    stratified_holdout_indices,
)


def test_classification_metrics_are_imbalance_aware() -> None:
    probabilities = np.asarray(
        [
            [0.9, 0.1],
            [0.8, 0.2],
            [0.7, 0.3],
            [0.6, 0.4],
            [0.6, 0.4],
            [0.6, 0.4],
        ],
        dtype=np.float64,
    )
    labels = np.asarray([0, 0, 0, 0, 0, 1], dtype=np.int64)
    summary, per_class, matrix = classification_metrics(
        probabilities,
        labels,
        ["majority", "minority"],
        ece_bins=5,
    )

    assert summary["accuracy"] == pytest.approx(5 / 6)
    assert summary["macro_recall"] == pytest.approx(0.5)
    assert summary["macro_f1"] < summary["accuracy"]
    assert per_class[1]["recall"] == 0.0
    assert matrix.tolist() == [[5, 0], [1, 0]]


def test_stratified_holdout_keeps_each_class() -> None:
    targets = [0] * 5 + [1] * 5 + [2] * 5
    train, holdout = stratified_holdout_indices(
        targets,
        num_classes=3,
        holdout_per_class=2,
        seed=42,
    )

    assert len(train) == 9
    assert len(holdout) == 6
    assert sorted(targets[index] for index in holdout) == [0, 0, 1, 1, 2, 2]
    assert set(train).isdisjoint(holdout)


def _write_image(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(value, value, value)).save(path)


def test_audit_detects_exact_cross_split_duplicate(tmp_path: Path) -> None:
    for split in ("train", "val"):
        for class_name, value in (("a", 10), ("b", 20)):
            _write_image(tmp_path / split / class_name / "sample.png", value)

    audit = audit_malevis_dataset(
        tmp_path,
        expected_image_size=8,
        hash_files=True,
        verify_images=True,
    )

    assert audit["split_counts"] == {"train": 2, "val": 2}
    assert audit["cross_split_duplicate_group_count"] == 2
    assert audit["deduplication_plan"]["excluded_by_split"] == {"train": 2, "val": 0}
    assert audit["deduplication_plan"]["label_conflict_group_count"] == 0


def test_audit_rejects_mismatched_classes(tmp_path: Path) -> None:
    _write_image(tmp_path / "train" / "a" / "sample.png", 10)
    _write_image(tmp_path / "val" / "b" / "sample.png", 20)

    with pytest.raises(MaleVisExperimentError, match="do not match"):
        audit_malevis_dataset(tmp_path, hash_files=False, verify_images=False)


def test_paired_manifest_uses_canonical_split_and_union_dedup(tmp_path: Path) -> None:
    root_224 = tmp_path / "r224"
    root_300 = tmp_path / "r300"
    layouts = {
        root_224: {
            "train": {"a": [("one.png", 10)], "b": [("three.png", 30)]},
            "val": {"a": [("two.png", 10)], "b": [("four.png", 40)]},
        },
        root_300: {
            "train": {"a": [("two.png", 10)], "b": [("three.png", 30)]},
            "val": {"a": [("one.png", 10)], "b": [("four.png", 40)]},
        },
    }
    for root, splits in layouts.items():
        size = 224 if root == root_224 else 300
        for split, classes in splits.items():
            for class_name, samples in classes.items():
                for filename, value in samples:
                    path = root / split / class_name / filename
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (size, size), color=(value, value, value)).save(path)

    document = build_paired_malevis_manifest(root_224, root_300)

    assert len(document["cross_resolution_split_mismatches"]) == 2
    assert document["eligible_sample_count"] == 3
    assert document["eligible_split_counts"] == {"train": 1, "val": 2}
    assert {sample["sample_id"] for sample in document["samples"]} == {
        "two.png",
        "three.png",
        "four.png",
    }
