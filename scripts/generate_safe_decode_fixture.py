"""Generate inert DECODE-like images and both adapter and YOLO fixtures.

All image content comes from printable ASCII API names and ``SYNTH_*`` markers.
The script never downloads, opens, parses, or executes a malware artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image

LOW_SIZE = 128
QUAD_SIZE = 256
FINAL_SIZE = 512
MAX_PIXELS = LOW_SIZE * LOW_SIZE

CLASSES = [
    "process_injection_like_evidence",
    "registry_persistence_like_evidence",
    "network_c2_like_evidence",
    "file_encryption_like_evidence",
]

# DECODE composite order: process | registry / network | filesystem.
QUADRANTS = {
    0: (0, 0, "process"),
    1: (256, 0, "registry"),
    2: (0, 256, "network"),
    3: (256, 256, "filesystem"),
}

SAFE_APIS = {
    "process": [
        "GetCurrentProcessId",
        "CreateToolhelp32Snapshot",
        "Process32FirstW",
        "Process32NextW",
        "OpenProcess",
        "GetProcessTimes",
        "CloseHandle",
    ],
    "registry": [
        "RegOpenKeyExW",
        "RegQueryValueExW",
        "RegEnumValueW",
        "RegCloseKey",
        "RegGetValueW",
        "RegQueryInfoKeyW",
    ],
    "network": [
        "InternetOpenW",
        "InternetConnectW",
        "HttpOpenRequestW",
        "HttpQueryInfoW",
        "InternetReadFile",
        "InternetCloseHandle",
    ],
    "filesystem": [
        "CreateFileW",
        "ReadFile",
        "GetFileSizeEx",
        "SetFilePointerEx",
        "CloseHandle",
        "GetFileAttributesW",
        "FindFirstFileW",
        "FindNextFileW",
    ],
}

MARKERS = {
    0: "SYNTH_PROC_INJECT_EVIDENCE_",
    1: "SYNTH_REG_PERSIST_EVIDENCE_",
    2: "SYNTH_NET_C2_EVIDENCE_",
    3: "SYNTH_FILE_ENCRYPT_EVIDENCE_",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def ascii_to_gray(text: str) -> list[tuple[int, int, int]]:
    """Mirror DECODE's ``int(256 * ord(character) / 128)`` ASCII mapping."""

    values: list[tuple[int, int, int]] = []
    for character in text:
        code = ord(character)
        if code > 127:
            raise ValueError("fixture must remain ASCII-only")
        value = max(0, min(255, int(256 * code / 128)))
        values.append((value, value, value))
    return values


def make_background_text(category: str, rng: random.Random) -> str:
    pieces: list[str] = []
    counter = 0
    current_length = 0
    while current_length < MAX_PIXELS:
        piece = f"{rng.choice(SAFE_APIS[category])}_{counter:05d}"
        pieces.append(piece)
        current_length += len(piece)
        counter += 1
    return "".join(pieces)[:MAX_PIXELS]


def insert_marker_as_rect(
    base_text: str,
    marker: str,
    rng: random.Random,
    *,
    width: int = 24,
    height: int = 8,
) -> tuple[str, tuple[int, int, int, int]]:
    if len(base_text) != MAX_PIXELS:
        raise ValueError("base text length mismatch")
    x = rng.randint(8, LOW_SIZE - width - 8)
    y = rng.randint(8, LOW_SIZE - height - 8)
    characters = list(base_text)
    marker_stream = (marker * math.ceil((width * height) / len(marker)))[: width * height]
    cursor = 0
    for row in range(height):
        start = (y + row) * LOW_SIZE + x
        characters[start : start + width] = marker_stream[cursor : cursor + width]
        cursor += width
    return "".join(characters), (x, y, width, height)


def quadrant_image(text: str) -> Image.Image:
    image = Image.new("RGB", (LOW_SIZE, LOW_SIZE))
    image.putdata(ascii_to_gray(text))
    return image.resize((QUAD_SIZE, QUAD_SIZE), Image.Resampling.NEAREST)


def make_sample(
    rng: random.Random,
    evidence_classes: list[int],
) -> tuple[Image.Image, list[dict[str, object]]]:
    combined = Image.new("RGB", (FINAL_SIZE, FINAL_SIZE))
    annotations: list[dict[str, object]] = []
    evidence_set = set(evidence_classes)
    for class_id, (offset_x, offset_y, category) in QUADRANTS.items():
        text = make_background_text(category, rng)
        if class_id in evidence_set:
            text, (x, y, width, height) = insert_marker_as_rect(
                text,
                MARKERS[class_id],
                rng,
            )
            annotations.append(
                {
                    "class_id": class_id,
                    "class_name": CLASSES[class_id],
                    "bbox_xywh": [
                        offset_x + x * 2,
                        offset_y + y * 2,
                        width * 2,
                        height * 2,
                    ],
                    "annotation_source": "synthetic",
                    "verified": True,
                }
            )
        combined.paste(quadrant_image(text), (offset_x, offset_y))
    return combined, annotations


def yolo_line(annotation: dict[str, object]) -> str:
    x, y, width, height = annotation["bbox_xywh"]  # type: ignore[misc]
    center_x = (x + width / 2) / FINAL_SIZE
    center_y = (y + height / 2) / FINAL_SIZE
    return (
        f"{annotation['class_id']} {center_x:.8f} {center_y:.8f} "
        f"{width / FINAL_SIZE:.8f} {height / FINAL_SIZE:.8f}"
    )


def write_dataset_yaml(root: Path) -> None:
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASSES))
    document = (
        "# Safe synthetic DECODE-like fixture. Not a real-malware benchmark.\n"
        f"path: {root.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        f"{names}\n"
    )
    (root / "dataset.yaml").write_text(document, encoding="utf-8")


def generate_split(
    root: Path,
    split: str,
    count: int,
    seed: int,
) -> list[dict[str, object]]:
    image_dir = root / "images" / split
    label_dir = root / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for index in range(count):
        rng = random.Random(seed + index * 104729)
        evidence = [] if index % 7 == 0 else rng.sample(range(len(CLASSES)), k=1 + index % 4)
        image, annotations = make_sample(rng, evidence)
        stem = f"{split}_{index:04d}"
        image_path = image_dir / f"{stem}.png"
        label_path = label_dir / f"{stem}.txt"
        image.save(image_path, format="PNG", optimize=True)
        lines = "\n".join(yolo_line(annotation) for annotation in annotations)
        label_path.write_text(lines + ("\n" if lines else ""), encoding="utf-8")
        records.append(
            {
                "sample_id": stem,
                "split": split,
                "image": image_path.relative_to(root).as_posix(),
                "sha256": sha256_file(image_path),
                "annotations": annotations,
            }
        )
    return records


def write_adapter_fixture(root: Path, records: list[dict[str, object]]) -> tuple[Path, Path]:
    """Write DECODE-shaped ROI JSON and an explicit, leakage-safe split map."""

    roi_records: list[dict[str, object]] = []
    split_map: dict[str, dict[str, str]] = {}
    for record in records:
        image_name = Path(str(record["image"])).name
        split = str(record["split"])
        split_map[image_name] = {
            "split": split,
            # Every inert source is independent; no group crosses a split.
            "source_group": f"synthetic-source-{record['sample_id']}",
        }
        for annotation in record["annotations"]:  # type: ignore[union-attr]
            roi_records.append(
                {
                    "image_name": image_name,
                    "category_name": annotation["class_name"],
                    "bbox": annotation["bbox_xywh"],
                }
            )
    adapter_dir = root / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    roi_path = adapter_dir / "decode_roi.synthetic.json"
    split_path = adapter_dir / "splits.synthetic.json"
    roi_path.write_text(json.dumps(roi_records, indent=2) + "\n", encoding="utf-8")
    split_path.write_text(json.dumps(split_map, indent=2) + "\n", encoding="utf-8")
    return roi_path, split_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an inert DECODE-like synthetic YOLO and adapter fixture"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train", type=int, default=80)
    parser.add_argument("--val", type=int, default=20)
    parser.add_argument("--test", type=int, default=20)
    parser.add_argument("--seed", type=int, default=260826)
    arguments = parser.parse_args()
    if arguments.train < 1 or arguments.val < 1 or arguments.test < 1:
        raise SystemExit("train, val, and test counts must all be positive")

    root = arguments.output.resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"refusing to overwrite non-empty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    records.extend(generate_split(root, "train", arguments.train, arguments.seed + 1000))
    records.extend(generate_split(root, "val", arguments.val, arguments.seed + 2000))
    records.extend(generate_split(root, "test", arguments.test, arguments.seed + 3000))
    write_dataset_yaml(root)
    roi_path, split_path = write_adapter_fixture(root, records)

    fixture_dir = root / "fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    sample, annotations = make_sample(random.Random(arguments.seed), [0, 1, 2, 3])
    sample_path = fixture_dir / "sample.png"
    sample.save(sample_path, format="PNG", optimize=True)
    clean, clean_annotations = make_sample(random.Random(arguments.seed + 1), [])
    clean_path = fixture_dir / "sample_clean.png"
    clean.save(clean_path, format="PNG", optimize=True)
    expected_path = fixture_dir / "expected.json"
    expected_path.write_text(
        json.dumps(
            {
                "schema": "ua-sahi-mal-safe-fixture-v1",
                "purpose": "pipeline-validation-only",
                "warning": (
                    "Synthetic DECODE-like evidence. This is not evidence of real "
                    "malware-detection performance."
                ),
                "image": "sample.png",
                "image_sha256": sha256_file(sample_path),
                "size": [FINAL_SIZE, FINAL_SIZE],
                "classes": CLASSES,
                "annotations": annotations,
                "clean_image": "sample_clean.png",
                "clean_image_sha256": sha256_file(clean_path),
                "clean_annotations": clean_annotations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (root / "fixture_manifest.json").write_text(
        json.dumps(
            {
                "schema": "ua-sahi-mal-safe-training-fixture-v1",
                "safe": True,
                "contains_executable_malware": False,
                "encoding": (
                    "DECODE-like ASCII-to-grayscale; four 256x256 behavior quadrants "
                    "in a 512x512 image"
                ),
                "classes": CLASSES,
                "counts": {
                    "train": arguments.train,
                    "val": arguments.val,
                    "test": arguments.test,
                },
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    checksum_lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name != "SHA256SUMS.txt":
            checksum_lines.append(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(root),
                "dataset_yaml": str(root / "dataset.yaml"),
                "adapter_images_root": str(root / "images"),
                "adapter_roi": str(roi_path),
                "adapter_split_map": str(split_path),
                "sample": str(sample_path),
                "expected": str(expected_path),
                "classes": CLASSES,
                "counts": {
                    "train": arguments.train,
                    "val": arguments.val,
                    "test": arguments.test,
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
