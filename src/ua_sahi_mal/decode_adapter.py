"""Import static DECODE ROI JSON into the UA-SAHI-MAL manifest contract.

The adapter intentionally accepts only already-generated images and ROI JSON.
It never downloads, executes, imports, or disassembles a malware sample.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Sequence

from PIL import Image

from ua_sahi_mal.encoding import sha256_file

ALLOWED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})
CLASS_POLICIES = frozenset({"class-agnostic", "roi-family"})
_SAMPLE_ID_CHARACTER = re.compile(r"[^A-Za-z0-9_.-]+")


class DecodeImportError(ValueError):
    """Raised when DECODE-derived static inputs are unsafe or inconsistent."""


@dataclass(frozen=True)
class DecodeImportSummary:
    output: Path
    dataset_name: str
    class_policy: str
    annotation_files: int
    samples: int
    annotations: int
    duplicates_removed: int
    categories: tuple[str, ...]


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DecodeImportError(f"JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise DecodeImportError(f"JSON file does not exist: {path}")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecodeImportError(f"cannot read JSON {path}: {exc}") from exc


def _annotation_records(document: Any, path: Path) -> list[dict[str, Any]]:
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict) and isinstance(document.get("annotations"), list):
        records = document["annotations"]
    else:
        raise DecodeImportError(
            f"{path} must contain a JSON array or an object with an annotations array"
        )
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise DecodeImportError(f"{path}: annotations[{index}] must be an object")
    return records


def _portable_basename(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DecodeImportError("DECODE image_name must be a non-empty string")
    value = value.strip()
    windows_name = PureWindowsPath(value).name
    posix_name = PurePosixPath(value).name
    name = windows_name if len(windows_name) <= len(posix_name) else posix_name
    if not name or name in {".", ".."}:
        raise DecodeImportError(f"invalid DECODE image_name: {value!r}")
    return name


def _image_index(images_root: Path) -> dict[str, Path]:
    images_root = images_root.resolve()
    if not images_root.is_dir():
        raise DecodeImportError(f"images root does not exist: {images_root}")
    matches: dict[str, list[Path]] = defaultdict(list)
    for path in images_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES:
            resolved = path.resolve()
            try:
                resolved.relative_to(images_root)
            except ValueError as exc:
                raise DecodeImportError(f"image escapes approved root: {path}") from exc
            matches[path.name.casefold()].append(resolved)
    ambiguous = {name: paths for name, paths in matches.items() if len(paths) > 1}
    if ambiguous:
        name, paths = sorted(ambiguous.items())[0]
        joined = ", ".join(str(path) for path in sorted(paths))
        raise DecodeImportError(f"ambiguous image basename {name!r}: {joined}")
    return {name: paths[0] for name, paths in matches.items()}


def _parse_split_map(path: Path) -> dict[str, tuple[str, str]]:
    document = _load_json(path)
    if not isinstance(document, dict) or not document:
        raise DecodeImportError("split map must be a non-empty object keyed by image basename")
    parsed: dict[str, tuple[str, str]] = {}
    family_splits: dict[str, str] = {}
    for raw_name, raw_entry in document.items():
        name = _portable_basename(raw_name).casefold()
        if name in parsed:
            raise DecodeImportError(f"split map contains duplicate basename: {raw_name}")
        if not isinstance(raw_entry, dict):
            raise DecodeImportError(f"split entry for {raw_name!r} must be an object")
        unknown = sorted(set(raw_entry) - {"split", "family_id", "source_group"})
        if unknown:
            raise DecodeImportError(
                f"split entry for {raw_name!r} contains unknown keys: {', '.join(unknown)}"
            )
        split = raw_entry.get("split")
        if split not in {"train", "val", "test"}:
            raise DecodeImportError(f"split for {raw_name!r} must be train, val, or test")
        family_id = raw_entry.get("family_id", raw_entry.get("source_group"))
        if not isinstance(family_id, str) or not family_id.strip():
            raise DecodeImportError(
                f"split entry for {raw_name!r} requires family_id (or source_group)"
            )
        family_id = family_id.strip()
        previous = family_splits.setdefault(family_id.casefold(), split)
        if previous != split:
            raise DecodeImportError(
                f"family/source group {family_id!r} crosses {previous!r} and {split!r}"
            )
        parsed[name] = (split, family_id)
    return parsed


def _bbox(record: dict[str, Any], context: str) -> tuple[float, float, float, float]:
    raw = record.get("bbox")
    if not isinstance(raw, list) or len(raw) != 4:
        raise DecodeImportError(f"{context}.bbox must contain [x, y, width, height]")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw):
        raise DecodeImportError(f"{context}.bbox values must be numbers")
    values = tuple(float(value) for value in raw)
    if any(not math.isfinite(value) for value in values):
        raise DecodeImportError(f"{context}.bbox values must be finite")
    x, y, width, height = values
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise DecodeImportError(f"{context}.bbox must be positive and non-negative at its origin")
    return values


def _source_score(record: dict[str, Any], context: str) -> float | None:
    value = record.get("source_score", record.get("score"))
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecodeImportError(f"{context}.source_score must be a number in [0, 1]")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise DecodeImportError(f"{context}.source_score must be a number in [0, 1]")
    return value


def _sample_id(image_path: Path, digest: str) -> str:
    stem = _SAMPLE_ID_CHARACTER.sub("-", image_path.stem).strip(".-_") or "image"
    stem = stem[:96]
    return f"decode-{stem}-{digest[:12]}"


def _image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise DecodeImportError(f"unsupported decoded image format for {path}: {image.format}")
            width, height = image.size
            image.verify()
    except DecodeImportError:
        raise
    except (OSError, ValueError) as exc:
        raise DecodeImportError(f"cannot decode approved image {path}: {exc}") from exc
    if width < 1 or height < 1:
        raise DecodeImportError(f"image has invalid dimensions: {path}")
    return width, height


def import_decode_roi(
    annotation_paths: Sequence[Path],
    *,
    images_root: Path,
    split_map_path: Path,
    output_path: Path,
    dataset_name: str,
    annotation_version: str,
    teacher_model: str,
    class_policy: str = "class-agnostic",
) -> DecodeImportSummary:
    """Convert DECODE ROI JSON files to a validated manifest-shaped document.

    ``roi-family`` preserves the initial Grad-CAM family label. It does not claim
    to reproduce DECODE's later within-family visual feature clustering.
    """

    if not annotation_paths:
        raise DecodeImportError("at least one DECODE annotation JSON is required")
    if class_policy not in CLASS_POLICIES:
        raise DecodeImportError(
            f"class_policy must be one of: {', '.join(sorted(CLASS_POLICIES))}"
        )
    for field_name, value in (
        ("dataset_name", dataset_name),
        ("annotation_version", annotation_version),
        ("teacher_model", teacher_model),
    ):
        if not isinstance(value, str) or not value.strip():
            raise DecodeImportError(f"{field_name} must be a non-empty string")
    output_path = output_path.resolve()
    if output_path.exists():
        raise DecodeImportError(f"refusing to overwrite existing output: {output_path}")

    image_by_name = _image_index(images_root)
    split_map = _parse_split_map(split_map_path)
    grouped: dict[str, list[tuple[str, tuple[float, float, float, float], float | None]]] = (
        defaultdict(list)
    )
    for annotation_path in annotation_paths:
        document = _load_json(annotation_path.resolve())
        for index, record in enumerate(_annotation_records(document, annotation_path)):
            context = f"{annotation_path.name}:annotations[{index}]"
            image_name = _portable_basename(record.get("image_name"))
            key = image_name.casefold()
            if Path(image_name).suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
                raise DecodeImportError(f"{context}: image_name must reference PNG or JPEG")
            if key not in image_by_name:
                raise DecodeImportError(
                    f"{context}: {image_name!r} was not found under the approved images root"
                )
            category_name = record.get("category_name")
            if not isinstance(category_name, str) or not category_name.strip():
                raise DecodeImportError(f"{context}.category_name must be a non-empty string")
            grouped[key].append(
                (category_name.strip(), _bbox(record, context), _source_score(record, context))
            )

    if not grouped:
        raise DecodeImportError("DECODE annotation files contain no ROI records")
    missing_splits = sorted(image_by_name[key].name for key in grouped if key not in split_map)
    if missing_splits:
        raise DecodeImportError(
            "split map is missing annotated images: " + ", ".join(missing_splits[:10])
        )

    if class_policy == "class-agnostic":
        category_names = ("malicious_evidence",)
    else:
        spelling_by_folded: dict[str, str] = {}
        for records in grouped.values():
            for category, _, _ in records:
                folded = category.casefold()
                previous = spelling_by_folded.setdefault(folded, category)
                if previous != category:
                    raise DecodeImportError(
                        "ROI family labels collide case-insensitively: "
                        f"{previous!r} and {category!r}"
                    )
        category_names = tuple(
            sorted({category for records in grouped.values() for category, _, _ in records}, key=str.casefold)
        )
    category_ids = {name.casefold(): index + 1 for index, name in enumerate(category_names)}

    samples: list[dict[str, Any]] = []
    duplicate_count = 0
    annotation_count = 0
    seen_sample_ids: set[str] = set()
    for key in sorted(grouped):
        image_path = image_by_name[key]
        width, height = _image_size(image_path)
        digest = sha256_file(image_path)
        sample_id = _sample_id(image_path, digest)
        if sample_id.casefold() in seen_sample_ids:
            raise DecodeImportError(f"sample id collision for image: {image_path}")
        seen_sample_ids.add(sample_id.casefold())
        split, family_id = split_map[key]
        annotations: list[dict[str, Any]] = []
        seen_annotations: set[tuple[Any, ...]] = set()
        for roi_family, bbox, score in grouped[key]:
            x, y, box_width, box_height = bbox
            if x + box_width > width or y + box_height > height:
                raise DecodeImportError(
                    f"bbox {bbox} exceeds image size {(width, height)} for {image_path.name}"
                )
            output_category = "malicious_evidence" if class_policy == "class-agnostic" else roi_family
            dedupe_key = (output_category.casefold(), *bbox)
            if dedupe_key in seen_annotations:
                duplicate_count += 1
                continue
            seen_annotations.add(dedupe_key)
            annotation: dict[str, Any] = {
                "category_id": category_ids[output_category.casefold()],
                "bbox_xywh": list(bbox),
                "annotation_source": "bayesian_gradcam",
                "annotation_version": annotation_version.strip(),
                "teacher_model": teacher_model.strip(),
                "verified": False,
            }
            if score is not None:
                annotation["source_score"] = score
            annotations.append(annotation)
            annotation_count += 1
        samples.append(
            {
                "sample_id": sample_id,
                "source": str(image_path),
                "sha256": digest,
                "split": split,
                "family_id": family_id,
                "encoding": "existing-image",
                "annotations": annotations,
            }
        )

    manifest = {
        "version": 1,
        "name": dataset_name.strip(),
        "categories": [
            {"id": index + 1, "name": name} for index, name in enumerate(category_names)
        ],
        "samples": samples,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return DecodeImportSummary(
        output=output_path,
        dataset_name=dataset_name.strip(),
        class_policy=class_policy,
        annotation_files=len(annotation_paths),
        samples=len(samples),
        annotations=annotation_count,
        duplicates_removed=duplicate_count,
        categories=category_names,
    )


def annotation_hashes(paths: Iterable[Path]) -> tuple[dict[str, str], ...]:
    """Return stable name/hash records for provenance files."""

    return tuple(
        {"name": path.name, "sha256": sha256_file(path.resolve())}
        for path in sorted((item.resolve() for item in paths), key=lambda item: str(item).casefold())
    )
