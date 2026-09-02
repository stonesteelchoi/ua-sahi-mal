import json
from pathlib import Path

import pytest
from PIL import Image

from ua_sahi_mal.dataset import load_manifest
from ua_sahi_mal.decode_adapter import DecodeImportError, annotation_hashes, import_decode_roi
from ua_sahi_mal.encoding import sha256_file


def _write_json(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _write_image(root: Path, name: str, *, color: int = 32) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 24), color=(color, color, color)).save(path)
    return path


def _run_import(
    tmp_path: Path,
    records: list[dict[str, object]],
    split_map: dict[str, dict[str, str]],
    *,
    class_policy: str = "class-agnostic",
):
    images = tmp_path / "images"
    for index, name in enumerate(split_map):
        _write_image(images, name, color=32 + index)
    annotation = _write_json(tmp_path / "roi.json", records)
    split_path = _write_json(tmp_path / "splits.json", split_map)
    output = tmp_path / "manifest.json"
    summary = import_decode_roi(
        [annotation],
        images_root=images,
        split_map_path=split_path,
        output_path=output,
        dataset_name="decode-static",
        annotation_version="gradcam-v1",
        teacher_model="teacher-sha256:abc",
        class_policy=class_policy,
    )
    return summary, output, annotation, images


def test_import_decode_roi_builds_valid_class_agnostic_manifest(tmp_path: Path) -> None:
    records = [
        {
            "image_name": r"C:\untrusted-export\alpha.png",
            "category_name": "dropper",
            "bbox": [2, 3, 8, 7],
            "score": 0.75,
        },
        {
            "image_name": "alpha.png",
            "category_name": "dropper",
            "bbox": [2, 3, 8, 7],
            "score": 0.75,
        },
    ]
    split_map = {"alpha.png": {"split": "train", "family_id": "source-alpha"}}

    summary, output, annotation, images = _run_import(tmp_path, records, split_map)
    document = json.loads(output.read_text(encoding="utf-8"))
    manifest = load_manifest(output)

    assert summary.samples == 1
    assert summary.annotations == 1
    assert summary.duplicates_removed == 1
    assert summary.categories == ("malicious_evidence",)
    assert manifest.categories[0].name == "malicious_evidence"
    assert document["samples"][0]["source"] == str((images / "alpha.png").resolve())
    assert document["samples"][0]["sha256"] == sha256_file(images / "alpha.png")
    assert document["samples"][0]["annotations"][0] == {
        "category_id": 1,
        "bbox_xywh": [2.0, 3.0, 8.0, 7.0],
        "annotation_source": "bayesian_gradcam",
        "annotation_version": "gradcam-v1",
        "teacher_model": "teacher-sha256:abc",
        "verified": False,
        "source_score": 0.75,
    }
    assert annotation_hashes([annotation]) == (
        {"name": "roi.json", "sha256": sha256_file(annotation)},
    )


def test_import_decode_roi_family_policy_preserves_sorted_family_classes(tmp_path: Path) -> None:
    records = [
        {"image_name": "alpha.png", "category_name": "worm", "bbox": [1, 1, 4, 4]},
        {"image_name": "alpha.png", "category_name": "dropper", "bbox": [8, 2, 5, 5]},
    ]
    split_map = {"alpha.png": {"split": "val", "source_group": "source-alpha"}}

    summary, output, _, _ = _run_import(
        tmp_path,
        records,
        split_map,
        class_policy="roi-family",
    )
    document = json.loads(output.read_text(encoding="utf-8"))

    assert summary.categories == ("dropper", "worm")
    assert document["categories"] == [
        {"id": 1, "name": "dropper"},
        {"id": 2, "name": "worm"},
    ]
    assert [item["category_id"] for item in document["samples"][0]["annotations"]] == [2, 1]


def test_import_decode_roi_rejects_family_group_crossing_splits(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _write_image(images, "train.png")
    _write_image(images, "test.png")
    annotation = _write_json(
        tmp_path / "roi.json",
        [
            {"image_name": "train.png", "category_name": "dropper", "bbox": [1, 1, 4, 4]},
            {"image_name": "test.png", "category_name": "dropper", "bbox": [1, 1, 4, 4]},
        ],
    )
    split_path = _write_json(
        tmp_path / "splits.json",
        {
            "train.png": {"split": "train", "family_id": "Same-Source"},
            "test.png": {"split": "test", "family_id": "same-source"},
        },
    )

    with pytest.raises(DecodeImportError, match="crosses"):
        import_decode_roi(
            [annotation],
            images_root=images,
            split_map_path=split_path,
            output_path=tmp_path / "manifest.json",
            dataset_name="decode-static",
            annotation_version="v1",
            teacher_model="teacher",
        )


@pytest.mark.parametrize(
    ("records", "split_map", "message"),
    [
        (
            [{"image_name": "alpha.png", "category_name": "dropper", "bbox": [30, 20, 3, 5]}],
            {"alpha.png": {"split": "train", "family_id": "a"}},
            "exceeds image size",
        ),
        (
            [{"image_name": "alpha.png", "category_name": "dropper", "bbox": [1, 2, 3, 4]}],
            {"other.png": {"split": "train", "family_id": "a"}},
            "missing annotated images",
        ),
    ],
)
def test_import_decode_roi_rejects_invalid_bbox_or_missing_split(
    tmp_path: Path,
    records: list[dict[str, object]],
    split_map: dict[str, dict[str, str]],
    message: str,
) -> None:
    images = tmp_path / "images"
    _write_image(images, "alpha.png")
    if "other.png" in split_map:
        _write_image(images, "other.png")
    annotation = _write_json(tmp_path / "roi.json", records)
    split_path = _write_json(tmp_path / "splits.json", split_map)

    with pytest.raises(DecodeImportError, match=message):
        import_decode_roi(
            [annotation],
            images_root=images,
            split_map_path=split_path,
            output_path=tmp_path / "manifest.json",
            dataset_name="decode-static",
            annotation_version="v1",
            teacher_model="teacher",
        )


def test_import_decode_roi_rejects_ambiguous_basename(tmp_path: Path) -> None:
    images = tmp_path / "images"
    _write_image(images, "a/alpha.png")
    _write_image(images, "b/alpha.png")
    annotation = _write_json(
        tmp_path / "roi.json",
        [{"image_name": "alpha.png", "category_name": "dropper", "bbox": [1, 1, 4, 4]}],
    )
    split_path = _write_json(
        tmp_path / "splits.json",
        {"alpha.png": {"split": "train", "family_id": "a"}},
    )

    with pytest.raises(DecodeImportError, match="ambiguous image basename"):
        import_decode_roi(
            [annotation],
            images_root=images,
            split_map_path=split_path,
            output_path=tmp_path / "manifest.json",
            dataset_name="decode-static",
            annotation_version="v1",
            teacher_model="teacher",
        )


def test_import_decode_roi_rejects_case_colliding_family_labels(tmp_path: Path) -> None:
    records = [
        {"image_name": "alpha.png", "category_name": "Dropper", "bbox": [1, 1, 4, 4]},
        {"image_name": "alpha.png", "category_name": "dropper", "bbox": [8, 1, 4, 4]},
    ]
    split_map = {"alpha.png": {"split": "train", "family_id": "a"}}

    with pytest.raises(DecodeImportError, match="case-insensitive"):
        _run_import(tmp_path, records, split_map, class_policy="roi-family")


def test_import_decode_roi_refuses_to_overwrite_output(tmp_path: Path) -> None:
    output = tmp_path / "manifest.json"
    output.write_text("keep", encoding="utf-8")
    images = tmp_path / "images"
    _write_image(images, "alpha.png")
    annotation = _write_json(
        tmp_path / "roi.json",
        [{"image_name": "alpha.png", "category_name": "dropper", "bbox": [1, 1, 4, 4]}],
    )
    split_path = _write_json(
        tmp_path / "splits.json",
        {"alpha.png": {"split": "train", "family_id": "a"}},
    )

    with pytest.raises(DecodeImportError, match="refusing to overwrite"):
        import_decode_roi(
            [annotation],
            images_root=images,
            split_map_path=split_path,
            output_path=output,
            dataset_name="decode-static",
            annotation_version="v1",
            teacher_model="teacher",
        )
    assert output.read_text(encoding="utf-8") == "keep"
