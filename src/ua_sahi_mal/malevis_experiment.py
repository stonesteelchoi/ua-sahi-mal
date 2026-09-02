"""Reproducible DECODE-inspired classification experiments for MaleVis.

MaleVis supplies image-level family labels, not object bounding boxes.  This
module therefore implements a closed-set classification transfer experiment
instead of pretending that the dataset can support DECODE/SAHI localization
metrics.  The model keeps the DECODE feature-learning ideas that are meaningful
for this modality (convolutional features, dropout, center loss, and Monte Carlo
dropout), while using a compact backbone that can be trained in an offline CPU
environment.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import statistics
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import yaml
from PIL import Image

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"})
SCHEMA = "ua-sahi-mal-malevis-transfer-v1"


class MaleVisExperimentError(ValueError):
    """Raised when a MaleVis experiment would be ambiguous or irreproducible."""


@dataclass(frozen=True)
class MaleVisSettings:
    experiment_id: str
    image_size: int
    internal_validation_per_class: int
    epochs: int
    batch_size: int
    learning_rate: float
    weight_decay: float
    center_loss_weight: float
    label_smoothing: float
    patience: int
    embedding_dim: int
    dropout: float
    mc_dropout_passes: int
    bootstrap_replicates: int
    ece_bins: int
    timing_warmup_batches: int
    timing_repeats: int
    num_workers: int
    torch_threads: int

    def validate(self) -> None:
        if not self.experiment_id.strip():
            raise MaleVisExperimentError("experiment_id must not be empty")
        integer_positive = {
            "image_size": self.image_size,
            "internal_validation_per_class": self.internal_validation_per_class,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "patience": self.patience,
            "embedding_dim": self.embedding_dim,
            "mc_dropout_passes": self.mc_dropout_passes,
            "bootstrap_replicates": self.bootstrap_replicates,
            "ece_bins": self.ece_bins,
            "timing_repeats": self.timing_repeats,
            "torch_threads": self.torch_threads,
        }
        for name, value in integer_positive.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise MaleVisExperimentError(f"{name} must be a positive integer")
        if self.timing_warmup_batches < 0 or self.num_workers < 0:
            raise MaleVisExperimentError("timing_warmup_batches and num_workers must be non-negative")
        for name, value in {
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "center_loss_weight": self.center_loss_weight,
        }.items():
            if not math.isfinite(value) or value < 0:
                raise MaleVisExperimentError(f"{name} must be finite and non-negative")
        if self.learning_rate == 0:
            raise MaleVisExperimentError("learning_rate must be positive")
        if not 0 <= self.label_smoothing < 1:
            raise MaleVisExperimentError("label_smoothing must be in [0, 1)")
        if not 0 <= self.dropout < 1:
            raise MaleVisExperimentError("dropout must be in [0, 1)")


def load_malevis_settings(path: Path) -> MaleVisSettings:
    """Load the strict, versioned experiment configuration."""

    if not path.is_file():
        raise MaleVisExperimentError(f"experiment config does not exist: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise MaleVisExperimentError(f"cannot read experiment config: {exc}") from exc
    if not isinstance(raw, dict):
        raise MaleVisExperimentError("experiment config must be a YAML mapping")
    expected_root = {"schema_version", "experiment_id", "model", "training", "evaluation"}
    if set(raw) != expected_root:
        raise MaleVisExperimentError(
            f"experiment config root differs; missing={sorted(expected_root - set(raw))}, "
            f"unknown={sorted(set(raw) - expected_root)}"
        )
    if raw["schema_version"] != 1:
        raise MaleVisExperimentError("schema_version must be 1")
    for section in ("model", "training", "evaluation"):
        if not isinstance(raw[section], dict):
            raise MaleVisExperimentError(f"{section} must be a mapping")
    model = raw["model"]
    training = raw["training"]
    evaluation = raw["evaluation"]
    expected_model = {"architecture", "image_size", "embedding_dim", "dropout"}
    expected_training = {
        "internal_validation_per_class",
        "epochs",
        "batch_size",
        "learning_rate",
        "weight_decay",
        "center_loss_weight",
        "label_smoothing",
        "patience",
        "num_workers",
        "torch_threads",
    }
    expected_evaluation = {
        "mc_dropout_passes",
        "bootstrap_replicates",
        "ece_bins",
        "timing_warmup_batches",
        "timing_repeats",
    }
    for section_name, section, expected in (
        ("model", model, expected_model),
        ("training", training, expected_training),
        ("evaluation", evaluation, expected_evaluation),
    ):
        if set(section) != expected:
            raise MaleVisExperimentError(
                f"{section_name} fields differ; missing={sorted(expected - set(section))}, "
                f"unknown={sorted(set(section) - expected)}"
            )
    if model["architecture"] != "decode-compact-dropout-cnn-v1":
        raise MaleVisExperimentError(
            "model.architecture must remain decode-compact-dropout-cnn-v1"
        )
    settings = MaleVisSettings(
        experiment_id=str(raw["experiment_id"]),
        image_size=int(model["image_size"]),
        internal_validation_per_class=int(training["internal_validation_per_class"]),
        epochs=int(training["epochs"]),
        batch_size=int(training["batch_size"]),
        learning_rate=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        center_loss_weight=float(training["center_loss_weight"]),
        label_smoothing=float(training["label_smoothing"]),
        patience=int(training["patience"]),
        embedding_dim=int(model["embedding_dim"]),
        dropout=float(model["dropout"]),
        mc_dropout_passes=int(evaluation["mc_dropout_passes"]),
        bootstrap_replicates=int(evaluation["bootstrap_replicates"]),
        ece_bins=int(evaluation["ece_bins"]),
        timing_warmup_batches=int(evaluation["timing_warmup_batches"]),
        timing_repeats=int(evaluation["timing_repeats"]),
        num_workers=int(training["num_workers"]),
        torch_threads=int(training["torch_threads"]),
    )
    settings.validate()
    return settings


def _image_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _class_directories(split_root: Path) -> list[Path]:
    if not split_root.is_dir():
        raise MaleVisExperimentError(f"dataset split directory is missing: {split_root}")
    classes = sorted(path for path in split_root.iterdir() if path.is_dir())
    if not classes:
        raise MaleVisExperimentError(f"dataset split contains no class directories: {split_root}")
    return classes


def audit_malevis_dataset(
    dataset_root: Path,
    *,
    expected_image_size: int | None = None,
    hash_files: bool = True,
    verify_images: bool = True,
    include_records: bool = False,
) -> dict[str, Any]:
    """Audit class counts, image validity, dimensions, and exact split duplicates."""

    root = dataset_root.resolve()
    split_classes = {
        split: _class_directories(root / split)
        for split in ("train", "val")
    }
    class_names = [path.name for path in split_classes["train"]]
    if [path.name for path in split_classes["val"]] != class_names:
        raise MaleVisExperimentError("train and val class directories do not match exactly")

    records: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    modes: dict[str, int] = {}
    dimensions: dict[str, int] = {}
    manifest = hashlib.sha256()
    hashes: dict[str, list[tuple[str, str]]] = {}
    invalid_images: list[dict[str, str]] = []

    for split in ("train", "val"):
        counts[split] = {}
        for class_dir in split_classes[split]:
            files = _image_files(class_dir)
            if not files:
                raise MaleVisExperimentError(f"class directory contains no supported images: {class_dir}")
            counts[split][class_dir.name] = len(files)
            for path in files:
                relative = path.relative_to(root).as_posix()
                file_hash = _sha256_file(path) if hash_files else None
                manifest.update(relative.encode("utf-8"))
                manifest.update(b"\0")
                manifest.update(str(path.stat().st_size).encode("ascii"))
                manifest.update(b"\0")
                if file_hash is not None:
                    manifest.update(file_hash.encode("ascii"))
                    hashes.setdefault(file_hash, []).append((split, relative))
                try:
                    with Image.open(path) as image:
                        size = tuple(int(value) for value in image.size)
                        mode = image.mode
                        if verify_images:
                            image.verify()
                except (OSError, ValueError) as exc:
                    invalid_images.append({"path": relative, "error": str(exc)})
                    continue
                size_key = f"{size[0]}x{size[1]}"
                dimensions[size_key] = dimensions.get(size_key, 0) + 1
                modes[mode] = modes.get(mode, 0) + 1
                if expected_image_size is not None and size != (
                    expected_image_size,
                    expected_image_size,
                ):
                    invalid_images.append(
                        {
                            "path": relative,
                            "error": (
                                f"expected {expected_image_size}x{expected_image_size}, "
                                f"found {size[0]}x{size[1]}"
                            ),
                        }
                    )
                records.append(
                    {
                        "split": split,
                        "class_name": class_dir.name,
                        "relative_path": relative,
                        "bytes": path.stat().st_size,
                        "sha256": file_hash,
                        "width": size[0],
                        "height": size[1],
                        "mode": mode,
                    }
                )

    records_by_hash: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record["sha256"] is not None:
            records_by_hash.setdefault(record["sha256"], []).append(record)
    duplicate_record_groups = [
        group for group in records_by_hash.values() if len(group) > 1
    ]
    duplicate_groups = [locations for locations in hashes.values() if len(locations) > 1]
    cross_split_duplicates = [
        locations
        for locations in duplicate_groups
        if len({split for split, _ in locations}) > 1
    ]
    duplicate_examples = [
        [{"split": split, "path": path} for split, path in locations]
        for locations in duplicate_groups[:20]
    ]
    cross_split_examples = [
        [{"split": split, "path": path} for split, path in locations]
        for locations in cross_split_duplicates[:20]
    ]
    excluded_records: list[dict[str, Any]] = []
    retained_duplicate_records: list[dict[str, Any]] = []
    label_conflict_groups: list[dict[str, Any]] = []
    if hash_files:
        for group in duplicate_record_groups:
            class_names_in_group = sorted({str(record["class_name"]) for record in group})
            if len(class_names_in_group) > 1:
                label_conflict_groups.append(
                    {
                        "sha256": group[0]["sha256"],
                        "class_names": class_names_in_group,
                        "records": [
                            {
                                "split": record["split"],
                                "class_name": record["class_name"],
                                "relative_path": record["relative_path"],
                            }
                            for record in group
                        ],
                    }
                )
                excluded_records.extend(group)
                continue
            # Preserve one final-test occurrence when a hash crosses splits, then remove
            # every matching train occurrence.  This avoids training on a final-test image.
            ordered = sorted(
                group,
                key=lambda record: (
                    0 if record["split"] == "val" else 1,
                    record["relative_path"],
                ),
            )
            retained_duplicate_records.append(ordered[0])
            excluded_records.extend(ordered[1:])
    excluded_by_split = {
        split: sum(record["split"] == split for record in excluded_records)
        for split in ("train", "val")
    }
    exclusion_plan = {
        "available": hash_files,
        "policy": (
            "For same-label duplicates retain one val occurrence when present, otherwise one "
            "train occurrence; exclude every other copy. Exclude every record in a conflicting-label "
            "hash group. Original dataset files are never changed."
            if hash_files
            else "unavailable_without_content_hashes"
        ),
        "excluded_record_count": len(excluded_records),
        "excluded_by_split": excluded_by_split,
        "retained_duplicate_record_count": len(retained_duplicate_records),
        "label_conflict_group_count": len(label_conflict_groups),
        "excluded_records": [
            {
                "split": record["split"],
                "class_name": record["class_name"],
                "relative_path": record["relative_path"],
                "sha256": record["sha256"],
            }
            for record in sorted(
                excluded_records,
                key=lambda item: (item["split"], item["class_name"], item["relative_path"]),
            )
        ],
        "label_conflict_groups": label_conflict_groups,
    }
    totals = {split: sum(split_counts.values()) for split, split_counts in counts.items()}
    audit = {
        "schema": "ua-sahi-mal-malevis-audit-v1",
        "dataset_root": str(root),
        "dataset_fingerprint_sha256": manifest.hexdigest(),
        "fingerprint_uses_content_hashes": hash_files,
        "class_names": class_names,
        "class_count": len(class_names),
        "split_counts": totals,
        "per_class_counts": counts,
        "dimensions": dict(sorted(dimensions.items())),
        "modes": dict(sorted(modes.items())),
        "invalid_image_count": len(invalid_images),
        "invalid_images": invalid_images[:100],
        "exact_duplicate_group_count": len(duplicate_groups),
        "cross_split_duplicate_group_count": len(cross_split_duplicates),
        "duplicate_examples": duplicate_examples,
        "cross_split_duplicate_examples": cross_split_examples,
        "deduplication_plan": exclusion_plan,
        "records_checked": len(records),
        "limitations": [
            "Exact hashes detect byte-identical files only; they do not rule out near-duplicate variants.",
            "MaleVis folders provide image-level classes and no object bounding boxes.",
            "The local class label 'Other' is treated as opaque; benign semantics are not inferred.",
        ],
    }
    if include_records:
        audit["file_records"] = records
    if invalid_images:
        raise MaleVisExperimentError(
            f"dataset contains {len(invalid_images)} invalid or unexpected images; "
            "inspect the audit details"
        )
    return audit


def build_paired_malevis_manifest(
    root_224: Path,
    root_300: Path,
) -> dict[str, Any]:
    """Create one leak-controlled logical split shared by both MaleVis resolutions."""

    audits = {
        224: audit_malevis_dataset(
            root_224,
            expected_image_size=224,
            hash_files=True,
            verify_images=True,
            include_records=True,
        ),
        300: audit_malevis_dataset(
            root_300,
            expected_image_size=300,
            hash_files=True,
            verify_images=True,
            include_records=True,
        ),
    }
    records_by_resolution: dict[int, dict[str, dict[str, Any]]] = {}
    for resolution, audit in audits.items():
        by_name: dict[str, dict[str, Any]] = {}
        for record in audit["file_records"]:
            sample_id = Path(record["relative_path"]).name
            if sample_id in by_name:
                raise MaleVisExperimentError(
                    f"resolution {resolution} contains a duplicate filename identity: {sample_id}"
                )
            by_name[sample_id] = record
        records_by_resolution[resolution] = by_name

    keys_224 = set(records_by_resolution[224])
    keys_300 = set(records_by_resolution[300])
    common_ids = sorted(keys_224 & keys_300)
    unmatched = {
        "only_224": sorted(keys_224 - keys_300),
        "only_300": sorted(keys_300 - keys_224),
    }
    label_mismatches = []
    split_mismatches = []
    for sample_id in common_ids:
        left = records_by_resolution[224][sample_id]
        right = records_by_resolution[300][sample_id]
        if left["class_name"] != right["class_name"]:
            label_mismatches.append(
                {
                    "sample_id": sample_id,
                    "class_224": left["class_name"],
                    "class_300": right["class_name"],
                }
            )
        if left["split"] != right["split"]:
            split_mismatches.append(
                {
                    "sample_id": sample_id,
                    "class_name": left["class_name"],
                    "split_224": left["split"],
                    "split_300": right["split"],
                }
            )

    parent = {sample_id: sample_id for sample_id in common_ids}

    def find(sample_id: str) -> str:
        while parent[sample_id] != sample_id:
            parent[sample_id] = parent[parent[sample_id]]
            sample_id = parent[sample_id]
        return sample_id

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[max(root_left, root_right)] = min(root_left, root_right)

    common_set = set(common_ids)
    for resolution in (224, 300):
        by_hash: dict[str, list[str]] = {}
        for sample_id, record in records_by_resolution[resolution].items():
            if sample_id in common_set:
                by_hash.setdefault(str(record["sha256"]), []).append(sample_id)
        for sample_ids in by_hash.values():
            for sample_id in sample_ids[1:]:
                union(sample_ids[0], sample_id)

    components: dict[str, list[str]] = {}
    for sample_id in common_ids:
        components.setdefault(find(sample_id), []).append(sample_id)
    duplicate_components = [sorted(component) for component in components.values() if len(component) > 1]
    excluded: dict[str, str] = {
        sample_id: "missing_from_300_resolution" for sample_id in unmatched["only_224"]
    }
    excluded.update(
        {sample_id: "missing_from_224_resolution" for sample_id in unmatched["only_300"]}
    )
    for mismatch in label_mismatches:
        excluded[mismatch["sample_id"]] = "cross_resolution_label_mismatch"
    retained_from_duplicate_components: list[str] = []
    conflicting_duplicate_components: list[dict[str, Any]] = []
    for component in duplicate_components:
        classes = sorted(
            {records_by_resolution[224][sample_id]["class_name"] for sample_id in component}
        )
        if len(classes) > 1:
            conflicting_duplicate_components.append(
                {"sample_ids": component, "class_names": classes}
            )
            for sample_id in component:
                excluded[sample_id] = "exact_duplicate_component_has_conflicting_labels"
            continue
        ordered = sorted(
            component,
            key=lambda sample_id: (
                0 if records_by_resolution[224][sample_id]["split"] == "val" else 1,
                sample_id,
            ),
        )
        retained_from_duplicate_components.append(ordered[0])
        for sample_id in ordered[1:]:
            excluded[sample_id] = "exact_duplicate_in_224_or_300_representation"

    samples = []
    for sample_id in common_ids:
        if sample_id in excluded:
            continue
        left = records_by_resolution[224][sample_id]
        right = records_by_resolution[300][sample_id]
        samples.append(
            {
                "sample_id": sample_id,
                "class_name": left["class_name"],
                "split": left["split"],
                "relative_paths": {
                    "224": left["relative_path"],
                    "300": right["relative_path"],
                },
                "sha256": {"224": left["sha256"], "300": right["sha256"]},
            }
        )
    split_counts = {
        split: sum(sample["split"] == split for sample in samples)
        for split in ("train", "val")
    }
    class_names = audits[224]["class_names"]
    per_class_counts = {
        split: {
            class_name: sum(
                sample["split"] == split and sample["class_name"] == class_name
                for sample in samples
            )
            for class_name in class_names
        }
        for split in ("train", "val")
    }
    excluded_records = [
        {"sample_id": sample_id, "reason": reason}
        for sample_id, reason in sorted(excluded.items())
    ]
    for audit in audits.values():
        audit.pop("file_records", None)
    return {
        "schema": "ua-sahi-mal-malevis-paired-split-v1",
        "canonical_split_resolution": 224,
        "dataset_roots": {
            "224": str(Path(root_224).resolve()),
            "300": str(Path(root_300).resolve()),
        },
        "dataset_fingerprints_sha256": {
            str(resolution): audit["dataset_fingerprint_sha256"]
            for resolution, audit in audits.items()
        },
        "raw_audits": {str(resolution): audit for resolution, audit in audits.items()},
        "class_names": class_names,
        "common_sample_id_count": len(common_ids),
        "unmatched_sample_ids": unmatched,
        "cross_resolution_label_mismatches": label_mismatches,
        "cross_resolution_split_mismatches": split_mismatches,
        "duplicate_component_count": len(duplicate_components),
        "conflicting_duplicate_components": conflicting_duplicate_components,
        "retained_duplicate_component_representatives": retained_from_duplicate_components,
        "excluded_sample_count": len(excluded_records),
        "excluded_samples": excluded_records,
        "eligible_sample_count": len(samples),
        "eligible_split_counts": split_counts,
        "eligible_per_class_counts": per_class_counts,
        "samples": samples,
        "policy": {
            "identity": "filename token shared across 224/300 trees",
            "split": "224 tree is canonical; 300 split swaps are remapped logically",
            "deduplication": (
                "union exact-hash duplicate graph from both resolutions; retain one canonical-val "
                "sample when present, otherwise one canonical-train sample"
            ),
            "filesystem_mutation": "none",
        },
        "limitations": [
            "Exact hashing does not detect perceptual or family-level near duplicates.",
            "One sample identity exists only in each resolution tree and is excluded from both.",
            "The 224 tree's provided split is treated as canonical; no provenance proves it is group-aware.",
        ],
    }


def stratified_holdout_indices(
    targets: Sequence[int],
    *,
    num_classes: int,
    holdout_per_class: int,
    seed: int,
    holdout_fraction: float | None = None,
) -> tuple[list[int], list[int]]:
    """Split a balanced training folder without touching the provided final test folder."""

    target_array = np.asarray(targets, dtype=np.int64)
    generator = np.random.default_rng(seed)
    train_indices: list[int] = []
    holdout_indices: list[int] = []
    for class_index in range(num_classes):
        indices = np.flatnonzero(target_array == class_index)
        class_holdout = holdout_per_class
        if holdout_fraction is not None:
            if not 0 < holdout_fraction < 1:
                raise MaleVisExperimentError("holdout_fraction must be in (0, 1)")
            class_holdout = min(
                holdout_per_class,
                max(1, int(round(len(indices) * holdout_fraction))),
            )
        if len(indices) <= class_holdout:
            raise MaleVisExperimentError(
                f"class {class_index} has {len(indices)} training images; "
                f"holdout={class_holdout} leaves no training data"
            )
        shuffled = generator.permutation(indices)
        holdout_indices.extend(int(value) for value in shuffled[:class_holdout])
        train_indices.extend(int(value) for value in shuffled[class_holdout:])
    return sorted(train_indices), sorted(holdout_indices)


def confusion_matrix(
    labels: Sequence[int] | np.ndarray,
    predictions: Sequence[int] | np.ndarray,
    num_classes: int,
) -> np.ndarray:
    matrix = np.zeros((num_classes, num_classes), dtype=np.int64)
    label_array = np.asarray(labels, dtype=np.int64)
    prediction_array = np.asarray(predictions, dtype=np.int64)
    if label_array.shape != prediction_array.shape:
        raise MaleVisExperimentError("labels and predictions must have the same shape")
    if label_array.ndim != 1:
        raise MaleVisExperimentError("labels and predictions must be one-dimensional")
    if len(label_array) and (
        label_array.min() < 0
        or prediction_array.min() < 0
        or label_array.max() >= num_classes
        or prediction_array.max() >= num_classes
    ):
        raise MaleVisExperimentError("labels or predictions fall outside the class range")
    np.add.at(matrix, (label_array, prediction_array), 1)
    return matrix


def _metrics_from_confusion(matrix: np.ndarray) -> dict[str, Any]:
    true_positive = np.diag(matrix).astype(np.float64)
    support = matrix.sum(axis=1).astype(np.float64)
    predicted = matrix.sum(axis=0).astype(np.float64)
    precision = np.divide(
        true_positive,
        predicted,
        out=np.zeros_like(true_positive),
        where=predicted > 0,
    )
    recall = np.divide(
        true_positive,
        support,
        out=np.zeros_like(true_positive),
        where=support > 0,
    )
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    total = float(matrix.sum())
    accuracy = float(true_positive.sum() / total) if total else 0.0
    weights = support / support.sum() if support.sum() else np.zeros_like(support)
    return {
        "accuracy": accuracy,
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1.mean()),
        "weighted_f1": float(np.sum(f1 * weights)),
        "per_class_precision": precision,
        "per_class_recall": recall,
        "per_class_f1": f1,
        "support": support.astype(np.int64),
    }


def classification_metrics(
    probabilities: np.ndarray,
    labels: Sequence[int] | np.ndarray,
    class_names: Sequence[str],
    *,
    ece_bins: int = 15,
) -> tuple[dict[str, Any], list[dict[str, Any]], np.ndarray]:
    """Compute imbalance-aware metrics without requiring scikit-learn."""

    probabilities = np.asarray(probabilities, dtype=np.float64)
    label_array = np.asarray(labels, dtype=np.int64)
    if probabilities.ndim != 2 or probabilities.shape[0] != len(label_array):
        raise MaleVisExperimentError("probabilities must be [samples, classes] and match labels")
    if probabilities.shape[1] != len(class_names):
        raise MaleVisExperimentError("probability class count does not match class_names")
    if len(label_array) == 0:
        raise MaleVisExperimentError("classification metrics require at least one sample")
    if not np.isfinite(probabilities).all() or np.any(probabilities < 0):
        raise MaleVisExperimentError("probabilities must be finite and non-negative")
    row_sums = probabilities.sum(axis=1)
    if not np.allclose(row_sums, 1.0, atol=1e-5):
        raise MaleVisExperimentError("each probability row must sum to one")
    predictions = probabilities.argmax(axis=1)
    matrix = confusion_matrix(label_array, predictions, len(class_names))
    base = _metrics_from_confusion(matrix)
    top_k = min(5, len(class_names))
    top_indices = np.argpartition(probabilities, -top_k, axis=1)[:, -top_k:]
    top5_accuracy = float(np.mean(np.any(top_indices == label_array[:, None], axis=1)))
    clipped = np.clip(probabilities, 1e-12, 1.0)
    nll = float(-np.log(clipped[np.arange(len(label_array)), label_array]).mean())
    one_hot = np.eye(len(class_names), dtype=np.float64)[label_array]
    brier = float(np.square(probabilities - one_hot).sum(axis=1).mean())
    confidence = probabilities.max(axis=1)
    correct = predictions == label_array
    bin_edges = np.linspace(0.0, 1.0, ece_bins + 1)
    ece = 0.0
    reliability: list[dict[str, Any]] = []
    for index in range(ece_bins):
        lower = bin_edges[index]
        upper = bin_edges[index + 1]
        lower_mask = (confidence > lower) if index else (confidence >= lower)
        mask = lower_mask & (confidence <= upper)
        count = int(mask.sum())
        bin_accuracy = float(correct[mask].mean()) if count else None
        bin_confidence = float(confidence[mask].mean()) if count else None
        if count:
            ece += (count / len(label_array)) * abs(float(bin_accuracy) - float(bin_confidence))
        reliability.append(
            {
                "lower": float(lower),
                "upper": float(upper),
                "count": count,
                "accuracy": bin_accuracy,
                "mean_confidence": bin_confidence,
            }
        )
    per_class_rows = []
    for index, class_name in enumerate(class_names):
        per_class_rows.append(
            {
                "class_index": index,
                "class_name": class_name,
                "support": int(base["support"][index]),
                "precision": float(base["per_class_precision"][index]),
                "recall": float(base["per_class_recall"][index]),
                "f1": float(base["per_class_f1"][index]),
            }
        )
    summary = {
        key: value
        for key, value in base.items()
        if not isinstance(value, np.ndarray)
    }
    summary.update(
        {
            "top5_accuracy": top5_accuracy,
            "negative_log_likelihood": nll,
            "multiclass_brier": brier,
            "expected_calibration_error": float(ece),
            "mean_confidence": float(confidence.mean()),
            "reliability_bins": reliability,
        }
    )
    return summary, per_class_rows, matrix


def stratified_bootstrap_intervals(
    labels: np.ndarray,
    predictions: np.ndarray,
    *,
    num_classes: int,
    replicates: int,
    seed: int,
) -> dict[str, dict[str, float]]:
    """Return percentile 95% intervals while preserving per-class support."""

    generator = np.random.default_rng(seed)
    by_class = [np.flatnonzero(labels == class_index) for class_index in range(num_classes)]
    if any(len(indices) == 0 for indices in by_class):
        raise MaleVisExperimentError("stratified bootstrap requires every class in the test set")
    values: dict[str, list[float]] = {"accuracy": [], "macro_f1": [], "macro_recall": []}
    for _ in range(replicates):
        sampled = np.concatenate(
            [generator.choice(indices, size=len(indices), replace=True) for indices in by_class]
        )
        metrics = _metrics_from_confusion(
            confusion_matrix(labels[sampled], predictions[sampled], num_classes)
        )
        for name in values:
            values[name].append(float(metrics[name]))
    return {
        name: {
            "lower_95": float(np.percentile(metric_values, 2.5)),
            "upper_95": float(np.percentile(metric_values, 97.5)),
            "replicates": replicates,
        }
        for name, metric_values in values.items()
    }


def _set_reproducible_seed(seed: int, torch: Any) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)


def _build_model(num_classes: int, embedding_dim: int, dropout: float, torch: Any):
    nn = torch.nn

    class DepthwiseSeparableBlock(nn.Module):
        def __init__(self, input_channels: int, output_channels: int, drop: float) -> None:
            super().__init__()
            self.layers = nn.Sequential(
                nn.Conv2d(
                    input_channels,
                    input_channels,
                    kernel_size=3,
                    stride=2,
                    padding=1,
                    groups=input_channels,
                    bias=False,
                ),
                nn.BatchNorm2d(input_channels),
                nn.ReLU(inplace=False),
                nn.Conv2d(input_channels, output_channels, kernel_size=1, bias=False),
                nn.BatchNorm2d(output_channels),
                nn.ReLU(inplace=False),
                nn.Dropout2d(p=drop),
            )

        def forward(self, inputs):
            return self.layers(inputs)

    class DecodeCompactDropoutCNN(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 24, kernel_size=5, stride=2, padding=2, bias=False),
                nn.BatchNorm2d(24),
                nn.ReLU(inplace=False),
                DepthwiseSeparableBlock(24, 48, dropout * 0.25),
                DepthwiseSeparableBlock(48, 96, dropout * 0.5),
                DepthwiseSeparableBlock(96, 160, dropout * 0.75),
                DepthwiseSeparableBlock(160, 256, dropout),
            )
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.embedding = nn.Sequential(
                nn.Flatten(),
                nn.Linear(256, embedding_dim),
                nn.ReLU(inplace=False),
                nn.Dropout(p=dropout),
            )
            self.classifier = nn.Linear(embedding_dim, num_classes)

        def forward(self, inputs):
            features = self.features(inputs)
            embedding = self.embedding(self.pool(features))
            return embedding, self.classifier(embedding)

    class CenterLoss(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.centers = nn.Parameter(torch.randn(num_classes, embedding_dim))

        def forward(self, embeddings, labels):
            selected = self.centers.index_select(0, labels)
            return torch.square(embeddings - selected).sum(dim=1).mean() / 2.0

    return DecodeCompactDropoutCNN(), CenterLoss()


def _enable_mc_dropout(model: Any, torch: Any) -> None:
    model.eval()
    for module in model.modules():
        if isinstance(module, (torch.nn.Dropout, torch.nn.Dropout2d, torch.nn.Dropout3d)):
            module.train()


def _collect_probabilities(
    model: Any,
    loader: Any,
    *,
    torch: Any,
    device: Any,
    mc_passes: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    if mc_passes > 1:
        _enable_mc_dropout(model, torch)
    else:
        model.eval()
    probability_batches: list[np.ndarray] = []
    label_batches: list[np.ndarray] = []
    predictive_entropy_batches: list[np.ndarray] = []
    mutual_information_batches: list[np.ndarray] = []
    with torch.inference_mode():
        for inputs, labels in loader:
            inputs = inputs.to(device)
            pass_probabilities = []
            for _ in range(mc_passes):
                _, logits = model(inputs)
                pass_probabilities.append(torch.softmax(logits, dim=1))
            stacked = torch.stack(pass_probabilities, dim=0)
            mean_probability = stacked.mean(dim=0)
            clipped_mean = mean_probability.clamp_min(1e-12)
            predictive_entropy = -(clipped_mean * clipped_mean.log()).sum(dim=1)
            pass_clipped = stacked.clamp_min(1e-12)
            expected_entropy = -(pass_clipped * pass_clipped.log()).sum(dim=2).mean(dim=0)
            probability_batches.append(mean_probability.cpu().numpy())
            label_batches.append(labels.numpy())
            predictive_entropy_batches.append(predictive_entropy.cpu().numpy())
            mutual_information_batches.append((predictive_entropy - expected_entropy).cpu().numpy())
    return (
        np.concatenate(probability_batches),
        np.concatenate(label_batches),
        {
            "predictive_entropy": np.concatenate(predictive_entropy_batches),
            "mutual_information": np.concatenate(mutual_information_batches),
        },
    )


def _benchmark_model(
    model: Any,
    loader: Any,
    *,
    torch: Any,
    device: Any,
    mc_passes: int,
    warmup_batches: int,
    repeats: int,
) -> dict[str, float | int | str]:
    if mc_passes > 1:
        _enable_mc_dropout(model, torch)
    else:
        model.eval()
    iterator = iter(loader)
    with torch.inference_mode():
        for _ in range(warmup_batches):
            try:
                inputs, _ = next(iterator)
            except StopIteration:
                iterator = iter(loader)
                inputs, _ = next(iterator)
            inputs = inputs.to(device)
            for _ in range(mc_passes):
                model(inputs)
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        per_image_ms: list[float] = []
        measured_images = 0
        total_start = time.perf_counter()
        for _ in range(repeats):
            for inputs, _ in loader:
                inputs = inputs.to(device)
                start = time.perf_counter()
                for _ in range(mc_passes):
                    model(inputs)
                if device.type == "cuda":
                    torch.cuda.synchronize(device)
                elapsed = time.perf_counter() - start
                batch_size = int(inputs.shape[0])
                per_image_ms.extend([elapsed * 1000.0 / batch_size] * batch_size)
                measured_images += batch_size
        total_elapsed = time.perf_counter() - total_start
    return {
        "mc_passes": mc_passes,
        "measured_images": measured_images,
        "batch_size": loader.batch_size,
        "latency_scope": "model_forward_after_batch_load",
        "throughput_scope": "dataloader_transfer_and_model_forward",
        "aggregation_note": (
            "Per-image latency divides each batch forward time by its batch size; "
            "it is not single-request end-to-end latency."
        ),
        "latency_mean_ms_per_image": float(statistics.fmean(per_image_ms)),
        "latency_p50_ms_per_image": float(np.percentile(per_image_ms, 50)),
        "latency_p95_ms_per_image": float(np.percentile(per_image_ms, 95)),
        "throughput_images_per_second": float(measured_images / total_elapsed),
        "wall_time_seconds": float(total_elapsed),
    }


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _plot_history(history: list[dict[str, Any]], output: Path) -> None:
    import matplotlib.pyplot as plt

    epochs = [row["epoch"] for row in history]
    figure, left = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    left.plot(epochs, [row["train_loss"] for row in history], label="train loss", color="#375A7F")
    left.set_xlabel("Epoch")
    left.set_ylabel("Training loss")
    right = left.twinx()
    right.plot(epochs, [row["validation_macro_f1"] for row in history], label="validation macro-F1", color="#C75B39")
    right.set_ylabel("Macro-F1")
    lines = left.lines + right.lines
    left.legend(lines, [line.get_label() for line in lines], loc="center right")
    left.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(output, bbox_inches="tight")
    plt.close(figure)


def _plot_confusion(matrix: np.ndarray, class_names: Sequence[str], output: Path) -> None:
    import matplotlib.pyplot as plt

    denominator = matrix.sum(axis=1, keepdims=True)
    normalized = np.divide(
        matrix,
        denominator,
        out=np.zeros_like(matrix, dtype=np.float64),
        where=denominator > 0,
    )
    figure, axis = plt.subplots(figsize=(9.0, 8.2), dpi=170)
    image = axis.imshow(normalized, cmap="Blues", vmin=0.0, vmax=1.0)
    axis.set_xticks(range(len(class_names)), class_names, rotation=90, fontsize=6)
    axis.set_yticks(range(len(class_names)), class_names, fontsize=6)
    axis.set_xlabel("Predicted class")
    axis.set_ylabel("True class")
    axis.set_title("Row-normalized MaleVis confusion matrix")
    figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Recall share")
    figure.tight_layout()
    figure.savefig(output, bbox_inches="tight")
    plt.close(figure)


def _json_dump(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _device_name(device: Any, torch: Any) -> str:
    if device.type == "cuda":
        return torch.cuda.get_device_name(device)
    return os.environ.get("PROCESSOR_IDENTIFIER", "CPU")


def run_malevis_experiment(
    *,
    dataset_root: Path,
    output_dir: Path,
    settings: MaleVisSettings,
    seed: int,
    paired_manifest: Path | None = None,
    benchmark_timing: bool = True,
    expected_train_images: int = 9100,
    expected_test_images: int = 5126,
) -> dict[str, Any]:
    """Train, evaluate, calibrate, benchmark, and persist one immutable run."""

    settings.validate()
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MaleVisExperimentError(f"refusing to overwrite non-empty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import torch
        import torchvision
        from torch.utils.data import DataLoader, Dataset, Subset
        from torchvision import datasets, transforms
    except ImportError as exc:
        raise MaleVisExperimentError(
            "PyTorch and torchvision are required; run the repository CPU/GPU setup first"
        ) from exc

    torch.set_num_threads(settings.torch_threads)
    try:
        torch.set_num_interop_threads(max(1, min(2, settings.torch_threads)))
    except RuntimeError:
        pass
    _set_reproducible_seed(seed, torch)
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    root = dataset_root.resolve()
    dataset_audit = audit_malevis_dataset(
        root,
        expected_image_size=settings.image_size,
        hash_files=True,
        verify_images=True,
    )
    if dataset_audit["split_counts"] != {
        "train": expected_train_images,
        "val": expected_test_images,
    }:
        raise MaleVisExperimentError(
            "unexpected dataset counts; expected "
            f"train={expected_train_images}, val={expected_test_images}, "
            f"found {dataset_audit['split_counts']}"
        )
    if dataset_audit["class_count"] != 26:
        raise MaleVisExperimentError(
            f"this frozen protocol expects 26 classes, found {dataset_audit['class_count']}"
        )

    transform = transforms.Compose(
        [
            transforms.Resize((settings.image_size, settings.image_size), antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225),
            ),
        ]
    )
    paired_document: dict[str, Any] | None = None

    class ManifestImageDataset(Dataset):
        def __init__(
            self,
            samples: list[tuple[str, int]],
            classes: list[str],
        ) -> None:
            self.samples = samples
            self.targets = [target for _, target in samples]
            self.classes = classes

        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, index: int):
            path, target = self.samples[index]
            with Image.open(path) as opened:
                image = opened.convert("RGB")
            return transform(image), target

    if paired_manifest is not None:
        paired_manifest = paired_manifest.resolve()
        if not paired_manifest.is_file():
            raise MaleVisExperimentError(f"paired manifest does not exist: {paired_manifest}")
        try:
            paired_document = json.loads(paired_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MaleVisExperimentError(f"cannot read paired manifest: {exc}") from exc
        if paired_document.get("schema") != "ua-sahi-mal-malevis-paired-split-v1":
            raise MaleVisExperimentError("paired manifest has an unexpected schema")
        resolution_key = str(settings.image_size)
        if resolution_key not in {"224", "300"}:
            raise MaleVisExperimentError("paired MaleVis protocol supports only 224 or 300")
        expected_root = Path(paired_document["dataset_roots"][resolution_key]).resolve()
        if expected_root != root:
            raise MaleVisExperimentError(
                f"dataset root differs from paired manifest: expected {expected_root}, got {root}"
            )
        expected_fingerprint = paired_document["dataset_fingerprints_sha256"][resolution_key]
        if dataset_audit["dataset_fingerprint_sha256"] != expected_fingerprint:
            raise MaleVisExperimentError("dataset content changed after the paired manifest was built")
        class_names = [str(value) for value in paired_document["class_names"]]
        if class_names != dataset_audit["class_names"]:
            raise MaleVisExperimentError("paired manifest class order differs from the dataset audit")
        class_to_index = {name: index for index, name in enumerate(class_names)}
        sample_rows: dict[str, list[tuple[str, int]]] = {"train": [], "val": []}
        for sample in paired_document["samples"]:
            split = sample["split"]
            if split not in sample_rows:
                raise MaleVisExperimentError(f"paired manifest contains invalid split: {split}")
            class_name = sample["class_name"]
            if class_name not in class_to_index:
                raise MaleVisExperimentError(
                    f"paired manifest references an unknown class: {class_name}"
                )
            path = root / sample["relative_paths"][resolution_key]
            if not path.is_file():
                raise MaleVisExperimentError(f"paired manifest image is missing: {path}")
            sample_rows[split].append((str(path), class_to_index[class_name]))
        complete_train = ManifestImageDataset(sample_rows["train"], class_names)
        complete_test = ManifestImageDataset(sample_rows["val"], class_names)
        eligible_train_indices = list(range(len(complete_train)))
        eligible_test_indices = list(range(len(complete_test)))
        split_policy = "paired_manifest_union_dedup_with_224_canonical_split"
    else:
        complete_train = datasets.ImageFolder(root / "train", transform=transform)
        complete_test = datasets.ImageFolder(root / "val", transform=transform)
        if complete_train.classes != complete_test.classes:
            raise MaleVisExperimentError("ImageFolder class ordering differs between train and val")
        excluded_paths = {
            record["relative_path"]
            for record in dataset_audit["deduplication_plan"]["excluded_records"]
        }
        eligible_train_indices = [
            index
            for index, (path, _) in enumerate(complete_train.samples)
            if Path(path).relative_to(root).as_posix() not in excluded_paths
        ]
        eligible_test_indices = [
            index
            for index, (path, _) in enumerate(complete_test.samples)
            if Path(path).relative_to(root).as_posix() not in excluded_paths
        ]
        split_policy = "single_resolution_exact_hash_dedup"
    eligible_train_targets = [complete_train.targets[index] for index in eligible_train_indices]
    train_positions, validation_positions = stratified_holdout_indices(
        eligible_train_targets,
        num_classes=len(complete_train.classes),
        holdout_per_class=settings.internal_validation_per_class,
        seed=seed,
        holdout_fraction=0.15,
    )
    train_indices = [eligible_train_indices[position] for position in train_positions]
    internal_validation_indices = [
        eligible_train_indices[position] for position in validation_positions
    ]
    train_set = Subset(complete_train, train_indices)
    validation_set = Subset(complete_train, internal_validation_indices)
    final_test = Subset(complete_test, eligible_test_indices)
    generator = torch.Generator().manual_seed(seed)
    loader_options = {
        "batch_size": settings.batch_size,
        "num_workers": settings.num_workers,
        "pin_memory": device.type == "cuda",
        "persistent_workers": settings.num_workers > 0,
    }
    train_loader = DataLoader(train_set, shuffle=True, generator=generator, **loader_options)
    validation_loader = DataLoader(validation_set, shuffle=False, **loader_options)
    test_loader = DataLoader(final_test, shuffle=False, **loader_options)

    model, center_loss = _build_model(
        len(complete_train.classes),
        settings.embedding_dim,
        settings.dropout,
        torch,
    )
    model = model.to(device)
    center_loss = center_loss.to(device)
    optimization_targets = np.asarray(
        [complete_train.targets[index] for index in train_indices],
        dtype=np.int64,
    )
    optimization_counts = np.bincount(
        optimization_targets,
        minlength=len(complete_train.classes),
    )
    if np.any(optimization_counts == 0):
        raise MaleVisExperimentError("deduplication/internal validation removed an entire class")
    class_weights = len(optimization_targets) / (
        len(complete_train.classes) * optimization_counts.astype(np.float64)
    )
    criterion = torch.nn.CrossEntropyLoss(
        weight=torch.as_tensor(class_weights, dtype=torch.float32, device=device),
        label_smoothing=settings.label_smoothing,
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=settings.learning_rate,
        weight_decay=settings.weight_decay,
    )
    center_optimizer = torch.optim.SGD(center_loss.parameters(), lr=0.05)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=settings.epochs)

    config_document = {
        "schema": SCHEMA,
        "experiment_id": settings.experiment_id,
        "seed": seed,
        "dataset_root": str(root),
        "paired_manifest": str(paired_manifest) if paired_manifest is not None else None,
        "settings": asdict(settings),
        "data_policy": {
            "provided_train": dataset_audit["split_counts"]["train"],
            "deduplicated_train_pool": len(eligible_train_indices),
            "optimization_train": len(train_set),
            "internal_validation": len(validation_set),
            "provided_val": dataset_audit["split_counts"]["val"],
            "deduplicated_val_used_once_as_final_test": len(final_test),
            "internal_validation_policy": (
                "15% per class, capped by internal_validation_per_class"
            ),
            "internal_validation_cap_per_class": settings.internal_validation_per_class,
            "optimization_class_counts": {
                complete_train.classes[index]: int(value)
                for index, value in enumerate(optimization_counts)
            },
            "cross_entropy_class_weights": {
                complete_train.classes[index]: float(value)
                for index, value in enumerate(class_weights)
            },
            "split_policy": split_policy,
            "augmentation": "none; byte-image spatial ordering is preserved",
            "normalization": "ImageNet channel mean/std for DECODE VGG-family comparability",
        },
    }
    _json_dump(output_dir / "config.resolved.json", config_document)
    _json_dump(output_dir / "dataset.full-audit.json", dataset_audit)
    if paired_document is not None:
        _json_dump(output_dir / "paired_manifest.snapshot.json", paired_document)

    history: list[dict[str, Any]] = []
    best_macro_f1 = -1.0
    best_epoch = 0
    best_state: dict[str, Any] | None = None
    epochs_without_improvement = 0
    train_start = time.perf_counter()
    for epoch in range(1, settings.epochs + 1):
        epoch_start = time.perf_counter()
        model.train()
        total_loss = 0.0
        total_correct = 0
        total_examples = 0
        for inputs, labels in train_loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            center_optimizer.zero_grad(set_to_none=True)
            embeddings, logits = model(inputs)
            softmax_loss = criterion(logits, labels)
            compactness_loss = center_loss(embeddings, labels)
            loss = softmax_loss + settings.center_loss_weight * compactness_loss
            loss.backward()
            if settings.center_loss_weight > 0:
                for parameter in center_loss.parameters():
                    if parameter.grad is not None:
                        parameter.grad.mul_(1.0 / settings.center_loss_weight)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            if settings.center_loss_weight > 0:
                center_optimizer.step()
            batch_examples = int(labels.shape[0])
            total_examples += batch_examples
            total_loss += float(loss.detach().cpu()) * batch_examples
            total_correct += int((logits.argmax(dim=1) == labels).sum().detach().cpu())
        validation_probabilities, validation_labels, _ = _collect_probabilities(
            model,
            validation_loader,
            torch=torch,
            device=device,
            mc_passes=1,
        )
        validation_metrics, _, _ = classification_metrics(
            validation_probabilities,
            validation_labels,
            complete_train.classes,
            ece_bins=settings.ece_bins,
        )
        history_row = {
            "epoch": epoch,
            "learning_rate": float(optimizer.param_groups[0]["lr"]),
            "train_loss": total_loss / total_examples,
            "train_accuracy": total_correct / total_examples,
            "validation_accuracy": validation_metrics["accuracy"],
            "validation_macro_f1": validation_metrics["macro_f1"],
            "validation_nll": validation_metrics["negative_log_likelihood"],
            "epoch_seconds": time.perf_counter() - epoch_start,
        }
        history.append(history_row)
        print(
            f"epoch={epoch:02d} loss={history_row['train_loss']:.4f} "
            f"train_acc={history_row['train_accuracy']:.4f} "
            f"val_acc={history_row['validation_accuracy']:.4f} "
            f"val_macro_f1={history_row['validation_macro_f1']:.4f} "
            f"seconds={history_row['epoch_seconds']:.1f}",
            flush=True,
        )
        if validation_metrics["macro_f1"] > best_macro_f1 + 1e-6:
            best_macro_f1 = float(validation_metrics["macro_f1"])
            best_epoch = epoch
            best_state = deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        scheduler.step()
        if epochs_without_improvement >= settings.patience:
            print(f"early_stopping epoch={epoch} best_epoch={best_epoch}", flush=True)
            break
    training_seconds = time.perf_counter() - train_start
    if best_state is None:
        raise MaleVisExperimentError("training completed without a valid checkpoint")
    model.load_state_dict(best_state)
    checkpoint_path = output_dir / "best_model.pt"
    torch.save(
        {
            "schema": SCHEMA,
            "architecture": "decode-compact-dropout-cnn-v1",
            "state_dict": best_state,
            "class_names": complete_train.classes,
            "seed": seed,
            "image_size": settings.image_size,
            "best_epoch": best_epoch,
            "settings": asdict(settings),
        },
        checkpoint_path,
    )

    evaluation_documents: dict[str, Any] = {}
    prediction_documents: dict[str, tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]] = {}
    modes = {"deterministic": 1, "mc_dropout": settings.mc_dropout_passes}
    for mode, passes in modes.items():
        probabilities, labels, uncertainty = _collect_probabilities(
            model,
            test_loader,
            torch=torch,
            device=device,
            mc_passes=passes,
        )
        metrics, per_class, matrix = classification_metrics(
            probabilities,
            labels,
            complete_train.classes,
            ece_bins=settings.ece_bins,
        )
        predictions = probabilities.argmax(axis=1)
        metrics["bootstrap_95"] = stratified_bootstrap_intervals(
            labels,
            predictions,
            num_classes=len(complete_train.classes),
            replicates=settings.bootstrap_replicates,
            seed=seed + (1301 if mode == "mc_dropout" else 1201),
        )
        if benchmark_timing:
            metrics["timing"] = {
                "status": "measured",
                **_benchmark_model(
                    model,
                    test_loader,
                    torch=torch,
                    device=device,
                    mc_passes=passes,
                    warmup_batches=settings.timing_warmup_batches,
                    repeats=settings.timing_repeats,
                ),
            }
        else:
            metrics["timing"] = {
                "status": "not_measured",
                "reason": "timing is measured on the designated representative seed only",
            }
        metrics["mc_passes"] = passes
        metrics["predictive_entropy_mean"] = float(uncertainty["predictive_entropy"].mean())
        metrics["mutual_information_mean"] = float(uncertainty["mutual_information"].mean())
        evaluation_documents[mode] = {
            "metrics": metrics,
            "per_class": per_class,
            "confusion_matrix": matrix.tolist(),
        }
        prediction_documents[mode] = (probabilities, labels, uncertainty)
        _write_csv(
            output_dir / f"per_class.{mode}.csv",
            per_class,
            ("class_index", "class_name", "support", "precision", "recall", "f1"),
        )
        matrix_rows = [
            {"true_class": complete_train.classes[row], **{
                complete_train.classes[column]: int(matrix[row, column])
                for column in range(len(complete_train.classes))
            }}
            for row in range(len(complete_train.classes))
        ]
        _write_csv(
            output_dir / f"confusion.{mode}.csv",
            matrix_rows,
            ("true_class", *complete_train.classes),
        )

    deterministic_probabilities, labels, deterministic_uncertainty = prediction_documents[
        "deterministic"
    ]
    mc_probabilities, _, mc_uncertainty = prediction_documents["mc_dropout"]
    prediction_rows = []
    test_samples = [complete_test.samples[index] for index in eligible_test_indices]
    for index, (path, target) in enumerate(test_samples):
        deterministic_prediction = int(deterministic_probabilities[index].argmax())
        mc_prediction = int(mc_probabilities[index].argmax())
        prediction_rows.append(
            {
                "relative_path": Path(path).relative_to(root).as_posix(),
                "true_class": complete_train.classes[target],
                "deterministic_prediction": complete_train.classes[deterministic_prediction],
                "deterministic_confidence": float(deterministic_probabilities[index].max()),
                "deterministic_entropy": float(
                    deterministic_uncertainty["predictive_entropy"][index]
                ),
                "mc_prediction": complete_train.classes[mc_prediction],
                "mc_confidence": float(mc_probabilities[index].max()),
                "mc_predictive_entropy": float(mc_uncertainty["predictive_entropy"][index]),
                "mc_mutual_information": float(mc_uncertainty["mutual_information"][index]),
            }
        )
    _write_csv(
        output_dir / "test_predictions.csv",
        prediction_rows,
        (
            "relative_path",
            "true_class",
            "deterministic_prediction",
            "deterministic_confidence",
            "deterministic_entropy",
            "mc_prediction",
            "mc_confidence",
            "mc_predictive_entropy",
            "mc_mutual_information",
        ),
    )
    _write_csv(
        output_dir / "training_history.csv",
        history,
        (
            "epoch",
            "learning_rate",
            "train_loss",
            "train_accuracy",
            "validation_accuracy",
            "validation_macro_f1",
            "validation_nll",
            "epoch_seconds",
        ),
    )
    _plot_history(history, output_dir / "training_history.png")
    _plot_confusion(
        np.asarray(evaluation_documents["mc_dropout"]["confusion_matrix"]),
        complete_train.classes,
        output_dir / "confusion.mc_dropout.png",
    )

    model_parameters = sum(parameter.numel() for parameter in model.parameters())
    checkpoint_sha256 = _sha256_file(checkpoint_path)
    summary = {
        "schema": SCHEMA,
        "experiment_id": settings.experiment_id,
        "seed": seed,
        "image_size": settings.image_size,
        "task": "closed-set 26-class image-level MaleVis classification",
        "baseline_scope": (
            "DECODE-inspired transfer of convolutional feature learning, dropout, center loss, "
            "and MC dropout; not a strict DECODE dynamic-behavior or object-detection reproduction"
        ),
        "dataset": {
            "root": str(root),
            "class_names": complete_train.classes,
            "provided_train_images": dataset_audit["split_counts"]["train"],
            "deduplicated_train_pool_images": len(eligible_train_indices),
            "optimization_train_images": len(train_set),
            "internal_validation_images": len(validation_set),
            "provided_val_images": dataset_audit["split_counts"]["val"],
            "deduplicated_val_as_final_test_images": len(final_test),
            "dataset_fingerprint_sha256": dataset_audit["dataset_fingerprint_sha256"],
            "fingerprint_uses_content_hashes": True,
            "split_policy": split_policy,
            "paired_manifest": str(paired_manifest) if paired_manifest is not None else None,
            "paired_manifest_sha256": (
                _sha256_file(paired_manifest) if paired_manifest is not None else None
            ),
            "deduplication_plan": {
                key: value
                for key, value in dataset_audit["deduplication_plan"].items()
                if key not in {"excluded_records", "label_conflict_groups"}
            },
        },
        "model": {
            "architecture": "decode-compact-dropout-cnn-v1",
            "parameters": model_parameters,
            "embedding_dim": settings.embedding_dim,
            "dropout": settings.dropout,
            "center_loss_weight": settings.center_loss_weight,
            "best_epoch": best_epoch,
            "best_internal_validation_macro_f1": best_macro_f1,
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": checkpoint_sha256,
        },
        "runtime": {
            "python": os.sys.version,
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "device": str(device),
            "device_name": _device_name(device, torch),
            "torch_threads": settings.torch_threads,
            "training_seconds": training_seconds,
            "benchmark_timing": benchmark_timing,
        },
        "evaluation": evaluation_documents,
        "localization_contract": {
            "status": "not_applicable",
            "reason": "MaleVis provides image-level classes but no independently verified object boxes",
            "not_reported": [
                "AP50",
                "mAP50:95",
                "AP_S",
                "Tile Recall",
                "Full SAHI comparison",
                "UA/JBU routing accuracy",
            ],
        },
        "evidence_limits": [
            "The provided val folder is used once as final test after model selection on an internal training holdout.",
            "Bootstrap intervals quantify test-sample uncertainty, not between-seed training variance.",
            (
                "Exact DECODE results and MaleVis results are not directly comparable because "
                "modalities and labels differ."
            ),
            "The local 'Other' label is not silently renamed or interpreted as benign.",
        ],
    }
    _json_dump(output_dir / "summary.json", summary)
    return summary


def aggregate_malevis_runs(run_dirs: Sequence[Path], output_dir: Path) -> dict[str, Any]:
    """Aggregate independent seeds/resolutions without fabricating missing comparisons."""

    if len(run_dirs) < 1:
        raise MaleVisExperimentError("at least one run directory is required")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MaleVisExperimentError(f"refusing to overwrite non-empty output: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for directory in run_dirs:
        path = directory.resolve() / "summary.json"
        if not path.is_file():
            raise MaleVisExperimentError(f"run summary is missing: {path}")
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema") != SCHEMA:
            raise MaleVisExperimentError(f"unexpected run schema in {path}")
        summaries.append(document)
    seen = set()
    for summary in summaries:
        key = (summary["image_size"], summary["seed"])
        if key in seen:
            raise MaleVisExperimentError(f"duplicate image_size/seed run: {key}")
        seen.add(key)

    metric_names = (
        "accuracy",
        "macro_precision",
        "macro_recall",
        "macro_f1",
        "weighted_f1",
        "top5_accuracy",
        "negative_log_likelihood",
        "multiclass_brier",
        "expected_calibration_error",
    )
    groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for summary in summaries:
        for mode in ("deterministic", "mc_dropout"):
            groups.setdefault((int(summary["image_size"]), mode), []).append(summary)
    aggregate_rows: list[dict[str, Any]] = []
    aggregate_groups: list[dict[str, Any]] = []
    t_critical_95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}
    for (image_size, mode), group in sorted(groups.items()):
        group_document: dict[str, Any] = {
            "image_size": image_size,
            "mode": mode,
            "seeds": [int(item["seed"]) for item in group],
            "n": len(group),
            "metrics": {},
        }
        for metric_name in metric_names:
            values = [float(item["evaluation"][mode]["metrics"][metric_name]) for item in group]
            mean = statistics.fmean(values)
            standard_deviation = statistics.stdev(values) if len(values) > 1 else None
            ci_lower = None
            ci_upper = None
            if standard_deviation is not None and len(values) in t_critical_95:
                margin = t_critical_95[len(values)] * standard_deviation / math.sqrt(len(values))
                ci_lower = mean - margin
                ci_upper = mean + margin
            group_document["metrics"][metric_name] = {
                "mean": mean,
                "standard_deviation": standard_deviation,
                "ci95_between_seed_lower": ci_lower,
                "ci95_between_seed_upper": ci_upper,
                "minimum": min(values),
                "maximum": max(values),
            }
            aggregate_rows.append(
                {
                    "image_size": image_size,
                    "mode": mode,
                    "n": len(values),
                    "metric": metric_name,
                    "mean": mean,
                    "standard_deviation": standard_deviation,
                    "ci95_between_seed_lower": ci_lower,
                    "ci95_between_seed_upper": ci_upper,
                    "minimum": min(values),
                    "maximum": max(values),
                }
            )
        timing_names = (
            "latency_mean_ms_per_image",
            "latency_p50_ms_per_image",
            "latency_p95_ms_per_image",
            "throughput_images_per_second",
        )
        group_document["timing"] = {}
        for timing_name in timing_names:
            values = [
                float(item["evaluation"][mode]["metrics"]["timing"][timing_name])
                for item in group
                if timing_name in item["evaluation"][mode]["metrics"]["timing"]
            ]
            if values:
                group_document["timing"][timing_name] = {
                    "status": "measured",
                    "n": len(values),
                    "mean": statistics.fmean(values),
                    "standard_deviation": statistics.stdev(values) if len(values) > 1 else None,
                    "minimum": min(values),
                    "maximum": max(values),
                }
            else:
                group_document["timing"][timing_name] = {"status": "not_measured", "n": 0}
        aggregate_groups.append(group_document)

    comparison_specs: list[dict[str, Any]] = []
    summaries_by_resolution_seed = {
        (int(summary["image_size"]), int(summary["seed"])): summary for summary in summaries
    }
    for image_size in sorted({int(summary["image_size"]) for summary in summaries}):
        resolution_summaries = sorted(
            (
                summary
                for summary in summaries
                if int(summary["image_size"]) == image_size
            ),
            key=lambda item: int(item["seed"]),
        )
        if len(resolution_summaries) >= 2:
            comparison_specs.append(
                {
                    "comparison": "mc_dropout_minus_deterministic",
                    "context": f"image_size={image_size}",
                    "left": "deterministic",
                    "right": "mc_dropout",
                    "pairs": [
                        (
                            int(summary["seed"]),
                            summary["evaluation"]["deterministic"]["metrics"],
                            summary["evaluation"]["mc_dropout"]["metrics"],
                        )
                        for summary in resolution_summaries
                    ],
                }
            )
    common_seeds = sorted(
        {
            int(summary["seed"])
            for summary in summaries
            if int(summary["image_size"]) == 224
        }
        & {
            int(summary["seed"])
            for summary in summaries
            if int(summary["image_size"]) == 300
        }
    )
    if len(common_seeds) >= 2:
        for mode in ("deterministic", "mc_dropout"):
            comparison_specs.append(
                {
                    "comparison": "300_minus_224",
                    "context": f"mode={mode}",
                    "left": "224",
                    "right": "300",
                    "pairs": [
                        (
                            seed,
                            summaries_by_resolution_seed[(224, seed)]["evaluation"][mode]["metrics"],
                            summaries_by_resolution_seed[(300, seed)]["evaluation"][mode]["metrics"],
                        )
                        for seed in common_seeds
                    ],
                }
            )

    paired_comparisons: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    for specification in comparison_specs:
        pairs = specification.pop("pairs")
        document: dict[str, Any] = {
            **specification,
            "difference_definition": "right_minus_left",
            "seeds": [seed for seed, _, _ in pairs],
            "n": len(pairs),
            "metrics": {},
        }
        for metric_name in metric_names:
            differences = [
                float(right_metrics[metric_name]) - float(left_metrics[metric_name])
                for _, left_metrics, right_metrics in pairs
            ]
            mean_difference = statistics.fmean(differences)
            standard_deviation = statistics.stdev(differences) if len(differences) > 1 else None
            ci_lower = None
            ci_upper = None
            if standard_deviation is not None and len(differences) in t_critical_95:
                margin = t_critical_95[len(differences)] * standard_deviation / math.sqrt(
                    len(differences)
                )
                ci_lower = mean_difference - margin
                ci_upper = mean_difference + margin
            document["metrics"][metric_name] = {
                "mean_difference": mean_difference,
                "standard_deviation_of_differences": standard_deviation,
                "ci95_lower": ci_lower,
                "ci95_upper": ci_upper,
                "individual_differences": differences,
            }
            comparison_rows.append(
                {
                    "comparison": specification["comparison"],
                    "context": specification["context"],
                    "left": specification["left"],
                    "right": specification["right"],
                    "difference_definition": "right_minus_left",
                    "n": len(differences),
                    "seeds": ";".join(str(seed) for seed, _, _ in pairs),
                    "metric": metric_name,
                    "mean_difference": mean_difference,
                    "standard_deviation_of_differences": standard_deviation,
                    "ci95_lower": ci_lower,
                    "ci95_upper": ci_upper,
                }
            )
        paired_comparisons.append(document)

    result = {
        "schema": "ua-sahi-mal-malevis-aggregate-v1",
        "source_runs": [str(path.resolve()) for path in run_dirs],
        "run_count": len(summaries),
        "groups": aggregate_groups,
        "paired_comparisons": paired_comparisons,
        "interpretation": {
            "between_seed_ci": (
                "Student-t 95% intervals are emitted only for 2-5 independent seeds; "
                "sample bootstrap intervals remain in each run summary"
            ),
            "paired_comparisons": (
                "MC-vs-deterministic and 300-vs-224 contrasts pair matching seeds; "
                "with three seeds their Student-t intervals are descriptive and low-power"
            ),
            "cross_resolution": (
                "224 and 300 are separate resized renderings of the same MaleVis source set, "
                "not independent datasets"
            ),
            "timing": (
                "Timing is measured on the designated representative seed only. Per-image "
                "p50/p95 divides batch model-forward time after loading by batch size; throughput "
                "covers data loading, host-to-device transfer, and model forward. Neither value is "
                "single-request end-to-end latency."
            ),
        },
    }
    _json_dump(output_dir / "aggregate.json", result)
    _write_csv(
        output_dir / "aggregate.csv",
        aggregate_rows,
        (
            "image_size",
            "mode",
            "n",
            "metric",
            "mean",
            "standard_deviation",
            "ci95_between_seed_lower",
            "ci95_between_seed_upper",
            "minimum",
            "maximum",
        ),
    )
    _write_csv(
        output_dir / "paired_comparisons.csv",
        comparison_rows,
        (
            "comparison",
            "context",
            "left",
            "right",
            "difference_definition",
            "n",
            "seeds",
            "metric",
            "mean_difference",
            "standard_deviation_of_differences",
            "ci95_lower",
            "ci95_upper",
        ),
    )
    return result
