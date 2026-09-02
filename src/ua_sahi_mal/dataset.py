"""Manifest validation and COCO/YOLO dataset preparation.

The data contract keeps executable samples outside Git. A manifest points to
local inputs, records their SHA-256 hashes and split groups, and exports only
non-executing PNG visualizations plus detector annotations.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from ua_sahi_mal.encoding import (
    SUPPORTED_ENCODINGS,
    EncodedImage,
    EncodingMetadata,
    encode_path,
    save_encoded_png,
    sha256_file,
    source_range_to_boxes,
)

MANIFEST_VERSION = 1
ALLOWED_SPLITS = frozenset({"train", "val", "test"})
ALLOWED_ANNOTATION_SOURCES = frozenset(
    {"bayesian_gradcam", "human_verified", "source_range", "synthetic"}
)
_SAMPLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

_ROOT_KEYS = frozenset({"version", "name", "categories", "samples"})
_CATEGORY_KEYS = frozenset({"id", "name"})
_SAMPLE_KEYS = frozenset(
    {"sample_id", "source", "split", "encoding", "width", "annotations", "sha256", "family_id"}
)
_ANNOTATION_KEYS = frozenset(
    {
        "category_id",
        "annotation_source",
        "verified",
        "start",
        "end",
        "bbox_xywh",
        "annotation_version",
        "teacher_model",
        "source_score",
    }
)


class ManifestError(ValueError):
    """Raised when a dataset contract is unsafe, incomplete, or inconsistent."""


@dataclass(frozen=True)
class Category:
    id: int
    name: str


@dataclass(frozen=True)
class SourceAnnotation:
    category_id: int
    annotation_source: str
    verified: bool
    start: int | None = None
    end: int | None = None
    bbox_xywh: tuple[float, float, float, float] | None = None
    annotation_version: str | None = None
    teacher_model: str | None = None
    source_score: float | None = None


@dataclass(frozen=True)
class SampleSpec:
    sample_id: str
    source: Path
    split: str
    encoding: str
    width: int
    annotations: tuple[SourceAnnotation, ...]
    expected_sha256: str | None = None
    family_id: str | None = None


@dataclass(frozen=True)
class DatasetManifest:
    path: Path
    name: str
    categories: tuple[Category, ...]
    samples: tuple[SampleSpec, ...]


@dataclass(frozen=True)
class ValidatedSample:
    spec: SampleSpec
    sha256: str
    metadata: EncodingMetadata


@dataclass(frozen=True)
class ValidatedManifest:
    manifest: DatasetManifest
    samples: tuple[ValidatedSample, ...]


@dataclass(frozen=True)
class PreparedDatasetSummary:
    output_dir: Path
    sample_count: int
    annotation_count: int
    split_counts: dict[str, int]
    category_count: int


def _as_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{context} must be a JSON object")
    return value


def _reject_unknown_keys(item: dict[str, Any], allowed: frozenset[str], context: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ManifestError(f"{context} contains unknown keys: {', '.join(unknown)}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"manifest contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _as_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{context} must be a JSON array")
    return value


def _as_nonempty_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context} must be a non-empty string")
    return value.strip()


def _as_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{context} must be an integer")
    return value


def _parse_category(raw: Any, index: int) -> Category:
    item = _as_mapping(raw, f"categories[{index}]")
    _reject_unknown_keys(item, _CATEGORY_KEYS, f"categories[{index}]")
    category_id = _as_int(item.get("id"), f"categories[{index}].id")
    name = _as_nonempty_string(item.get("name"), f"categories[{index}].name")
    if any(character in name for character in "\r\n"):
        raise ManifestError(f"categories[{index}].name must be one line")
    return Category(id=category_id, name=name)


def _parse_bbox(value: Any, context: str) -> tuple[float, float, float, float]:
    values = _as_list(value, context)
    if len(values) != 4:
        raise ManifestError(f"{context} must contain [x, y, width, height]")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise ManifestError(f"{context} values must be numbers")
    if any(not math.isfinite(float(item)) for item in values):
        raise ManifestError(f"{context} values must be finite")
    return tuple(float(item) for item in values)  # type: ignore[return-value]


def _parse_annotation(raw: Any, sample_index: int, annotation_index: int) -> SourceAnnotation:
    context = f"samples[{sample_index}].annotations[{annotation_index}]"
    item = _as_mapping(raw, context)
    _reject_unknown_keys(item, _ANNOTATION_KEYS, context)
    category_id = _as_int(item.get("category_id"), f"{context}.category_id")
    annotation_source = _as_nonempty_string(
        item.get("annotation_source"), f"{context}.annotation_source"
    )
    if annotation_source not in ALLOWED_ANNOTATION_SOURCES:
        allowed = ", ".join(sorted(ALLOWED_ANNOTATION_SOURCES))
        raise ManifestError(f"{context}.annotation_source must be one of: {allowed}")
    verified = item.get("verified", annotation_source == "human_verified")
    if not isinstance(verified, bool):
        raise ManifestError(f"{context}.verified must be true or false")
    if annotation_source == "human_verified" and not verified:
        raise ManifestError(f"{context}: human_verified annotations must set verified=true")

    has_range = "start" in item or "end" in item
    has_bbox = "bbox_xywh" in item
    if has_range == has_bbox:
        raise ManifestError(
            f"{context} must define exactly one of start/end source offsets or bbox_xywh"
        )

    start: int | None = None
    end: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    if has_range:
        start = _as_int(item.get("start"), f"{context}.start")
        end = _as_int(item.get("end"), f"{context}.end")
    else:
        bbox = _parse_bbox(item.get("bbox_xywh"), f"{context}.bbox_xywh")

    score = item.get("source_score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ManifestError(f"{context}.source_score must be a number in [0, 1]")
        score = float(score)

    annotation_version = item.get("annotation_version")
    if annotation_version is not None:
        annotation_version = _as_nonempty_string(
            annotation_version, f"{context}.annotation_version"
        )
    teacher_model = item.get("teacher_model")
    if teacher_model is not None:
        teacher_model = _as_nonempty_string(teacher_model, f"{context}.teacher_model")
    if annotation_source == "bayesian_gradcam" and not annotation_version:
        raise ManifestError(f"{context}: Bayesian Grad-CAM labels require annotation_version")

    return SourceAnnotation(
        category_id=category_id,
        annotation_source=annotation_source,
        verified=verified,
        start=start,
        end=end,
        bbox_xywh=bbox,
        annotation_version=annotation_version,
        teacher_model=teacher_model,
        source_score=score,
    )


def _parse_sample(raw: Any, index: int, manifest_path: Path) -> SampleSpec:
    context = f"samples[{index}]"
    item = _as_mapping(raw, context)
    _reject_unknown_keys(item, _SAMPLE_KEYS, context)
    sample_id = _as_nonempty_string(item.get("sample_id"), f"{context}.sample_id")
    if _SAMPLE_ID.fullmatch(sample_id) is None:
        raise ManifestError(
            f"{context}.sample_id must use only letters, digits, dot, underscore, and hyphen"
        )
    windows_stem = sample_id.split(".", 1)[0].upper()
    if sample_id.endswith(".") or windows_stem in _WINDOWS_RESERVED_NAMES:
        raise ManifestError(f"{context}.sample_id is not a portable file name")

    source_text = _as_nonempty_string(item.get("source"), f"{context}.source")
    source = Path(source_text)
    if not source.is_absolute():
        source = manifest_path.parent / source
    source = source.resolve()

    split = _as_nonempty_string(item.get("split"), f"{context}.split")
    if split not in ALLOWED_SPLITS:
        raise ManifestError(f"{context}.split must be train, val, or test")
    encoding = _as_nonempty_string(item.get("encoding"), f"{context}.encoding")
    if encoding not in SUPPORTED_ENCODINGS:
        supported = ", ".join(sorted(SUPPORTED_ENCODINGS))
        raise ManifestError(f"{context}.encoding must be one of: {supported}")

    width = item.get("width", 256)
    width = _as_int(width, f"{context}.width")
    if not 1 <= width <= 8192:
        raise ManifestError(f"{context}.width must be in [1, 8192]")

    annotations = tuple(
        _parse_annotation(annotation, index, annotation_index)
        for annotation_index, annotation in enumerate(
            _as_list(item.get("annotations", []), f"{context}.annotations")
        )
    )

    expected_hash = item.get("sha256")
    if expected_hash is not None:
        expected_hash = _as_nonempty_string(expected_hash, f"{context}.sha256").lower()
        if _SHA256.fullmatch(expected_hash) is None:
            raise ManifestError(f"{context}.sha256 must be 64 lowercase hexadecimal characters")

    family_id = item.get("family_id")
    if family_id is not None:
        family_id = _as_nonempty_string(family_id, f"{context}.family_id")

    return SampleSpec(
        sample_id=sample_id,
        source=source,
        split=split,
        encoding=encoding,
        width=width,
        annotations=annotations,
        expected_sha256=expected_hash,
        family_id=family_id,
    )


def load_manifest(path: Path) -> DatasetManifest:
    """Parse the versioned JSON manifest without reading any sample payload."""

    path = path.resolve()
    if not path.is_file():
        raise ManifestError(f"manifest does not exist: {path}")
    try:
        root = _as_mapping(
            json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object),
            "manifest",
        )
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON manifest: {exc}") from exc

    _reject_unknown_keys(root, _ROOT_KEYS, "manifest")
    version = _as_int(root.get("version"), "version")
    if version != MANIFEST_VERSION:
        raise ManifestError(f"unsupported manifest version {version}; expected {MANIFEST_VERSION}")
    name = _as_nonempty_string(root.get("name"), "name")
    categories = tuple(
        _parse_category(item, index)
        for index, item in enumerate(_as_list(root.get("categories"), "categories"))
    )
    if not categories:
        raise ManifestError("categories must not be empty")
    expected_ids = list(range(1, len(categories) + 1))
    actual_ids = [category.id for category in categories]
    if actual_ids != expected_ids:
        raise ManifestError(f"category ids must be contiguous and ordered from 1: {expected_ids}")
    names = [category.name for category in categories]
    if len({name.casefold() for name in names}) != len(names):
        raise ManifestError("category names must be unique")

    samples = tuple(
        _parse_sample(item, index, path)
        for index, item in enumerate(_as_list(root.get("samples"), "samples"))
    )
    if not samples:
        raise ManifestError("samples must not be empty")
    sample_ids = [sample.sample_id for sample in samples]
    if len({sample_id.casefold() for sample_id in sample_ids}) != len(sample_ids):
        raise ManifestError("sample_id values must be unique under case-insensitive file systems")

    valid_category_ids = set(actual_ids)
    for sample in samples:
        for annotation in sample.annotations:
            if annotation.category_id not in valid_category_ids:
                raise ManifestError(
                    f"sample {sample.sample_id!r} references unknown category {annotation.category_id}"
                )
    return DatasetManifest(path=path, name=name, categories=categories, samples=samples)


def _validate_annotation_geometry(
    sample: SampleSpec,
    annotation: SourceAnnotation,
    encoded: EncodedImage,
) -> None:
    if annotation.bbox_xywh is not None:
        x, y, width, height = annotation.bbox_xywh
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ManifestError(f"sample {sample.sample_id!r} contains a non-positive bbox")
        if x + width > encoded.image.width or y + height > encoded.image.height:
            raise ManifestError(
                f"sample {sample.sample_id!r} bbox {annotation.bbox_xywh} exceeds "
                f"image size {encoded.image.size}"
            )
        return

    if annotation.start is None or annotation.end is None:
        raise ManifestError(f"sample {sample.sample_id!r} annotation has no location")
    try:
        source_range_to_boxes(annotation.start, annotation.end, encoded.metadata)
    except ValueError as exc:
        raise ManifestError(f"sample {sample.sample_id!r}: {exc}") from exc


def validate_manifest(
    path: Path,
    *,
    max_input_bytes: int = 64 * 1024 * 1024,
) -> ValidatedManifest:
    """Validate hashes, geometry, and family/source leakage across splits."""

    manifest = load_manifest(path)
    validated: list[ValidatedSample] = []
    seen_hashes: dict[str, tuple[str, str]] = {}
    family_splits: dict[str, str] = {}

    for sample in manifest.samples:
        if not sample.source.is_file():
            raise ManifestError(f"sample {sample.sample_id!r} source does not exist: {sample.source}")
        size = sample.source.stat().st_size
        if size > max_input_bytes:
            raise ManifestError(
                f"sample {sample.sample_id!r} exceeds max_input_bytes ({size} > {max_input_bytes})"
            )

        fingerprint = sha256_file(sample.source)
        if sample.expected_sha256 and sample.expected_sha256 != fingerprint:
            raise ManifestError(
                f"sample {sample.sample_id!r} SHA-256 mismatch: "
                f"expected {sample.expected_sha256}, got {fingerprint}"
            )
        if fingerprint in seen_hashes:
            previous_id, previous_split = seen_hashes[fingerprint]
            raise ManifestError(
                f"duplicate source SHA-256 for {previous_id!r} ({previous_split}) and "
                f"{sample.sample_id!r} ({sample.split})"
            )
        seen_hashes[fingerprint] = (sample.sample_id, sample.split)

        if sample.family_id:
            previous_split = family_splits.setdefault(sample.family_id, sample.split)
            if previous_split != sample.split:
                raise ManifestError(
                    f"family_id {sample.family_id!r} crosses {previous_split!r} and {sample.split!r}"
                )

        try:
            encoded = encode_path(
                sample.source,
                mode=sample.encoding,
                width=sample.width,
                max_input_bytes=max_input_bytes,
            )
        except (OSError, ValueError) as exc:
            raise ManifestError(f"sample {sample.sample_id!r} cannot be encoded: {exc}") from exc
        for annotation in sample.annotations:
            _validate_annotation_geometry(sample, annotation, encoded)
        validated.append(
            ValidatedSample(spec=sample, sha256=fingerprint, metadata=encoded.metadata)
        )

    return ValidatedManifest(manifest=manifest, samples=tuple(validated))


def _annotation_boxes(
    annotation: SourceAnnotation,
    metadata: EncodingMetadata,
) -> tuple[tuple[float, float, float, float], ...]:
    if annotation.bbox_xywh is not None:
        return (annotation.bbox_xywh,)
    if annotation.start is None or annotation.end is None:
        raise ManifestError("annotation has no source range or bbox")
    return tuple(
        tuple(float(value) for value in box)
        for box in source_range_to_boxes(annotation.start, annotation.end, metadata)
    )


def _write_dataset_yaml(output_dir: Path, categories: Iterable[Category], splits: set[str]) -> None:
    lines: list[str] = []
    for split in ("train", "val", "test"):
        if split in splits:
            lines.append(f"{split}: images/{split}")
    lines.append("names:")
    for category in categories:
        lines.append(f"  {category.id - 1}: {json.dumps(category.name, ensure_ascii=False)}")
    (output_dir / "dataset.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_coco_document(document: dict[str, Any]) -> None:
    """Validate the strict COCO subset emitted by this project."""

    images = _as_list(document.get("images"), "COCO images")
    annotations = _as_list(document.get("annotations"), "COCO annotations")
    categories = _as_list(document.get("categories"), "COCO categories")
    image_sizes: dict[int, tuple[int, int]] = {}
    for index, raw_image in enumerate(images):
        image = _as_mapping(raw_image, f"COCO images[{index}]")
        image_id = _as_int(image.get("id"), f"COCO images[{index}].id")
        width = _as_int(image.get("width"), f"COCO images[{index}].width")
        height = _as_int(image.get("height"), f"COCO images[{index}].height")
        if image_id in image_sizes or width < 1 or height < 1:
            raise ManifestError("COCO images must have unique ids and positive dimensions")
        image_sizes[image_id] = (width, height)

    category_ids = {
        _as_int(_as_mapping(item, "COCO category").get("id"), "COCO category id")
        for item in categories
    }
    annotation_ids: set[int] = set()
    for index, raw_annotation in enumerate(annotations):
        annotation = _as_mapping(raw_annotation, f"COCO annotations[{index}]")
        annotation_id = _as_int(annotation.get("id"), f"COCO annotations[{index}].id")
        image_id = _as_int(annotation.get("image_id"), f"COCO annotations[{index}].image_id")
        category_id = _as_int(
            annotation.get("category_id"), f"COCO annotations[{index}].category_id"
        )
        if annotation_id in annotation_ids:
            raise ManifestError("COCO annotation ids must be unique")
        annotation_ids.add(annotation_id)
        if image_id not in image_sizes or category_id not in category_ids:
            raise ManifestError("COCO annotation references an unknown image or category")
        x, y, width, height = _parse_bbox(
            annotation.get("bbox"), f"COCO annotations[{index}].bbox"
        )
        image_width, image_height = image_sizes[image_id]
        if x < 0 or y < 0 or width <= 0 or height <= 0:
            raise ManifestError("COCO bbox must be positive and inside the image")
        if x + width > image_width or y + height > image_height:
            raise ManifestError("COCO bbox extends outside its image")


def prepare_dataset(
    manifest_path: Path,
    output_dir: Path,
    *,
    max_input_bytes: int = 64 * 1024 * 1024,
    allow_sensitive_output: bool = False,
) -> PreparedDatasetSummary:
    """Export validated PNGs, YOLO labels, COCO JSON, and provenance."""

    if not allow_sensitive_output:
        raise ManifestError(
            "prepared RGB images can preserve source bytes/opcodes; "
            "set allow_sensitive_output=True only for an approved non-Git output location"
        )
    validated = validate_manifest(manifest_path, max_input_bytes=max_input_bytes)
    available_splits = {sample.spec.split for sample in validated.samples}
    missing_training_splits = {"train", "val"} - available_splits
    if missing_training_splits:
        missing = ", ".join(sorted(missing_training_splits))
        raise ManifestError(f"prepared YOLO datasets require train and val splits; missing: {missing}")
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ManifestError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    categories = validated.manifest.categories
    category_documents = [
        {"id": category.id, "name": category.name, "supercategory": "malware_evidence"}
        for category in categories
    ]
    split_documents: dict[str, dict[str, Any]] = {}
    split_image_ids: dict[str, int] = {}
    split_annotation_ids: dict[str, int] = {}
    provenance_records: list[dict[str, Any]] = []
    prepared_records: list[dict[str, Any]] = []
    annotation_count = 0

    for validated_sample in validated.samples:
        sample = validated_sample.spec
        split = sample.split
        document = split_documents.setdefault(
            split,
            {
                "info": {
                    "description": f"{validated.manifest.name} ({split})",
                    "manifest_version": MANIFEST_VERSION,
                },
                "images": [],
                "annotations": [],
                "categories": category_documents,
            },
        )
        image_id = split_image_ids.get(split, 0) + 1
        split_image_ids[split] = image_id
        split_annotation_ids.setdefault(split, 0)

        before_encode_hash = sha256_file(sample.source)
        if before_encode_hash != validated_sample.sha256:
            raise ManifestError(f"sample {sample.sample_id!r} changed after manifest validation")
        encoded = encode_path(
            sample.source,
            mode=sample.encoding,
            width=sample.width,
            max_input_bytes=max_input_bytes,
        )
        after_encode_hash = sha256_file(sample.source)
        if after_encode_hash != before_encode_hash:
            raise ManifestError(f"sample {sample.sample_id!r} changed while it was being encoded")
        image_relative = Path("images") / split / f"{sample.sample_id}.png"
        label_relative = Path("labels") / split / f"{sample.sample_id}.txt"
        image_path = output_dir / image_relative
        label_path = output_dir / label_relative
        image_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        save_encoded_png(encoded, image_path)

        document["images"].append(
            {
                "id": image_id,
                "file_name": image_relative.as_posix(),
                "width": encoded.image.width,
                "height": encoded.image.height,
            }
        )
        yolo_lines: list[str] = []
        for source_annotation_index, source_annotation in enumerate(sample.annotations):
            for component_index, (x, y, width, height) in enumerate(
                _annotation_boxes(source_annotation, encoded.metadata)
            ):
                annotation_id = split_annotation_ids[split] + 1
                split_annotation_ids[split] = annotation_id
                annotation_count += 1
                document["annotations"].append(
                    {
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": source_annotation.category_id,
                        "bbox": [x, y, width, height],
                        "area": width * height,
                        "iscrowd": 0,
                    }
                )
                center_x = (x + width / 2) / encoded.image.width
                center_y = (y + height / 2) / encoded.image.height
                normalized_width = width / encoded.image.width
                normalized_height = height / encoded.image.height
                yolo_lines.append(
                    f"{source_annotation.category_id - 1} {center_x:.8f} {center_y:.8f} "
                    f"{normalized_width:.8f} {normalized_height:.8f}"
                )
                provenance_records.append(
                    {
                        "split": split,
                        "sample_id": sample.sample_id,
                        "image_id": image_id,
                        "annotation_id": annotation_id,
                        "source_annotation_index": source_annotation_index,
                        "component_index": component_index,
                        "category_id": source_annotation.category_id,
                        "annotation_source": source_annotation.annotation_source,
                        "annotation_version": source_annotation.annotation_version,
                        "teacher_model": source_annotation.teacher_model,
                        "source_score": source_annotation.source_score,
                        "verified": source_annotation.verified,
                        "source_range": (
                            [source_annotation.start, source_annotation.end]
                            if source_annotation.start is not None
                            else None
                        ),
                        "bbox_xywh": [x, y, width, height],
                        "source_sha256": validated_sample.sha256,
                        "encoding_version": encoded.metadata.version,
                    }
                )
        label_path.write_text("\n".join(yolo_lines) + ("\n" if yolo_lines else ""), encoding="utf-8")
        prepared_records.append(
            {
                "sample_id": sample.sample_id,
                "split": split,
                "family_id": sample.family_id,
                "source_name": sample.source.name,
                "source_sha256": validated_sample.sha256,
                "image": image_relative.as_posix(),
                "label": label_relative.as_posix(),
                "encoding": encoded.metadata.to_dict(),
            }
        )

    annotation_dir = output_dir / "annotations"
    annotation_dir.mkdir(parents=True, exist_ok=True)
    for split, document in split_documents.items():
        validate_coco_document(document)
        (annotation_dir / f"{split}.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    (output_dir / "annotation_provenance.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in provenance_records),
        encoding="utf-8",
    )
    prepared_manifest = {
        "version": MANIFEST_VERSION,
        "name": validated.manifest.name,
        "source_manifest_sha256": sha256_file(validated.manifest.path),
        "categories": [asdict(category) for category in categories],
        "samples": prepared_records,
    }
    (output_dir / "prepared_manifest.json").write_text(
        json.dumps(prepared_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    splits = set(split_documents)
    _write_dataset_yaml(output_dir, categories, splits)

    return PreparedDatasetSummary(
        output_dir=output_dir,
        sample_count=len(validated.samples),
        annotation_count=annotation_count,
        split_counts={split: len(document["images"]) for split, document in split_documents.items()},
        category_count=len(categories),
    )


def summary_to_json(summary: PreparedDatasetSummary) -> str:
    return json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str)


def manifest_template() -> dict[str, Any]:
    """Return a small schema example for CLI help and documentation tests."""

    return {
        "version": MANIFEST_VERSION,
        "name": "ua-sahi-mal-example",
        "categories": [{"id": 1, "name": "malicious_evidence"}],
        "samples": [
            {
                "sample_id": "synthetic-001",
                "source": "inputs/synthetic.hex",
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "width": 16,
                "family_id": "synthetic-family-a",
                "annotations": [
                    {
                        "category_id": 1,
                        "start": 2,
                        "end": 8,
                        "annotation_source": "synthetic",
                        "verified": True,
                    }
                ],
            }
        ],
    }
