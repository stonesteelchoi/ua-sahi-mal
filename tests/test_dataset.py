import json
from pathlib import Path

import pytest
from PIL import Image

import ua_sahi_mal.dataset as dataset_module
from ua_sahi_mal.dataset import ManifestError, prepare_dataset, validate_manifest


def _write_manifest(tmp_path: Path, samples: list[dict], categories: list[dict] | None = None) -> Path:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "test-dataset",
                "categories": categories or [{"id": 1, "name": "evidence"}],
                "samples": samples,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _range_annotation(start: int = 1, end: int = 5) -> dict:
    return {
        "category_id": 1,
        "start": start,
        "end": end,
        "annotation_source": "source_range",
        "verified": False,
    }


def test_prepare_dataset_writes_coco_yolo_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    val_source = tmp_path / "val.txt"
    source.write_text("10 20 30 40 50 60 70 80", encoding="utf-8")
    val_source.write_text("11 21 31 41 51 61 71 81", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "sample-001",
                "source": source.name,
                "split": "train",
                "family_id": "family-a",
                "encoding": "opcode-3gram-rgb",
                "width": 4,
                "annotations": [_range_annotation()],
            },
            {
                "sample_id": "sample-val-001",
                "source": val_source.name,
                "split": "val",
                "family_id": "family-b",
                "encoding": "opcode-3gram-rgb",
                "width": 4,
                "annotations": [],
            },
        ],
    )

    summary = prepare_dataset(
        manifest,
        tmp_path / "prepared",
        allow_sensitive_output=True,
    )

    assert summary.sample_count == 2
    assert summary.annotation_count >= 1
    assert (tmp_path / "prepared/images/train/sample-001.png").is_file()
    yolo_text = (tmp_path / "prepared/labels/train/sample-001.txt").read_text(encoding="utf-8")
    assert yolo_text.startswith("0 ")
    coco = json.loads((tmp_path / "prepared/annotations/train.json").read_text(encoding="utf-8"))
    assert coco["images"][0]["width"] == 4
    assert coco["annotations"][0]["category_id"] == 1
    provenance = (tmp_path / "prepared/annotation_provenance.jsonl").read_text(encoding="utf-8")
    assert '"annotation_source": "source_range"' in provenance
    prepared = (tmp_path / "prepared/prepared_manifest.json").read_text(encoding="utf-8")
    assert str(tmp_path.resolve()) not in prepared
    dataset_yaml = (tmp_path / "prepared/dataset.yaml").read_text(encoding="utf-8")
    assert "path:" not in dataset_yaml
    assert "train: images/train" in dataset_yaml
    assert "val: images/val" in dataset_yaml
    assert b"ua_sahi_mal_sensitive" in (tmp_path / "prepared/images/train/sample-001.png").read_bytes()


def test_existing_image_accepts_direct_pseudo_bbox(tmp_path: Path) -> None:
    source = tmp_path / "decode.png"
    Image.new("RGB", (16, 12)).save(source)
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "decode-001",
                "source": source.name,
                "split": "val",
                "encoding": "existing-image",
                "annotations": [
                    {
                        "category_id": 1,
                        "bbox_xywh": [2, 3, 4, 5],
                        "annotation_source": "bayesian_gradcam",
                        "annotation_version": "bgcam-v1",
                        "teacher_model": "teacher-sha256",
                        "source_score": 0.8,
                        "verified": False,
                    }
                ],
            }
        ],
    )

    validated = validate_manifest(manifest)

    assert validated.samples[0].metadata.width == 16


def test_bayesian_gradcam_requires_version(tmp_path: Path) -> None:
    source = tmp_path / "decode.png"
    Image.new("RGB", (8, 8)).save(source)
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "decode-001",
                "source": source.name,
                "split": "train",
                "encoding": "existing-image",
                "annotations": [
                    {
                        "category_id": 1,
                        "bbox_xywh": [1, 1, 2, 2],
                        "annotation_source": "bayesian_gradcam",
                        "verified": False,
                    }
                ],
            }
        ],
    )

    with pytest.raises(ManifestError, match="annotation_version"):
        validate_manifest(manifest)


def test_duplicate_source_hash_is_rejected_across_splits(tmp_path: Path) -> None:
    source = tmp_path / "same.txt"
    source.write_text("10 20 30 40", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "a",
                "source": source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
            {
                "sample_id": "b",
                "source": source.name,
                "split": "test",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
        ],
    )

    with pytest.raises(ManifestError, match="duplicate source SHA-256"):
        validate_manifest(manifest)


def test_family_id_cannot_cross_splits(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("10 20 30 40", encoding="utf-8")
    second.write_text("50 60 70 80", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "a",
                "source": first.name,
                "split": "train",
                "family_id": "same-family",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
            {
                "sample_id": "b",
                "source": second.name,
                "split": "test",
                "family_id": "same-family",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
        ],
    )

    with pytest.raises(ManifestError, match="family_id"):
        validate_manifest(manifest)


def test_bbox_outside_image_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "decode.png"
    Image.new("RGB", (8, 8)).save(source)
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "decode-001",
                "source": source.name,
                "split": "train",
                "encoding": "existing-image",
                "annotations": [
                    {
                        "category_id": 1,
                        "bbox_xywh": [7, 7, 2, 2],
                        "annotation_source": "human_verified",
                        "verified": True,
                    }
                ],
            }
        ],
    )

    with pytest.raises(ManifestError, match="exceeds image size"):
        validate_manifest(manifest)


def test_category_ids_must_be_contiguous_from_one(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("10 20 30", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "a",
                "source": source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            }
        ],
        categories=[{"id": 2, "name": "bad"}],
    )

    with pytest.raises(ManifestError, match="contiguous"):
        validate_manifest(manifest)


@pytest.mark.parametrize("sample_id", ["CON", "lpt1", "portable."])
def test_sample_id_must_be_portable_on_windows(tmp_path: Path, sample_id: str) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("10 20 30", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": sample_id,
                "source": source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            }
        ],
    )

    with pytest.raises(ManifestError, match="portable"):
        validate_manifest(manifest)


def test_non_finite_bbox_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "decode.png"
    Image.new("RGB", (8, 8)).save(source)
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "decode-001",
                "source": source.name,
                "split": "train",
                "encoding": "existing-image",
                "annotations": [
                    {
                        "category_id": 1,
                        "bbox_xywh": [1, 1, float("nan"), 2],
                        "annotation_source": "human_verified",
                        "verified": True,
                    }
                ],
            }
        ],
    )

    with pytest.raises(ManifestError, match="finite"):
        validate_manifest(manifest)


def test_unknown_manifest_key_is_rejected_instead_of_ignored(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("10 20 30", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "a",
                "source": source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annnotations": [],
                "annotations": [],
            }
        ],
    )

    with pytest.raises(ManifestError, match="unknown keys: annnotations"):
        validate_manifest(manifest)


def test_sample_ids_are_unique_on_case_insensitive_filesystems(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("10 20 30", encoding="utf-8")
    second.write_text("40 50 60", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "sample-a",
                "source": first.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
            {
                "sample_id": "SAMPLE-A",
                "source": second.name,
                "split": "val",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
        ],
    )

    with pytest.raises(ManifestError, match="case-insensitive"):
        validate_manifest(manifest)


def test_prepare_requires_explicit_sensitive_output_acknowledgement(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="allow_sensitive_output"):
        prepare_dataset(tmp_path / "not-read.json", tmp_path / "prepared")


def test_prepare_requires_train_and_val_splits(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("10 20 30", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "a",
                "source": source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            }
        ],
    )

    with pytest.raises(ManifestError, match="missing: val"):
        prepare_dataset(manifest, tmp_path / "prepared", allow_sensitive_output=True)


def test_prepare_detects_source_change_during_second_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_source = tmp_path / "train.txt"
    val_source = tmp_path / "val.txt"
    train_source.write_text("10 20 30 40", encoding="utf-8")
    val_source.write_text("50 60 70 80", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "sample_id": "train-a",
                "source": train_source.name,
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
            {
                "sample_id": "val-a",
                "source": val_source.name,
                "split": "val",
                "encoding": "opcode-3gram-rgb",
                "annotations": [],
            },
        ],
    )
    original_encode = dataset_module.encode_path
    call_count = 0

    def mutate_on_prepare(path: Path, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            path.write_text("11 21 31 41", encoding="utf-8")
        return original_encode(path, **kwargs)

    monkeypatch.setattr(dataset_module, "encode_path", mutate_on_prepare)

    with pytest.raises(ManifestError, match="changed while it was being encoded"):
        prepare_dataset(manifest, tmp_path / "prepared", allow_sensitive_output=True)
