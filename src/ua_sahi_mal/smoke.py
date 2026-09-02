"""CPU-only synthetic end-to-end smoke workflow."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from ua_sahi_mal.dataset import prepare_dataset
from ua_sahi_mal.evaluation import detector_call_reduction, tile_recall
from ua_sahi_mal.strategies import (
    BudgetedSahiStrategy,
    FullImageStrategy,
    FullSahiStrategy,
    RedBlobFakeDetector,
    generate_tile_grid,
)


@dataclass(frozen=True)
class SmokeSummary:
    output_dir: Path
    prepared_samples: int
    prepared_annotations: int
    full_image_detections: int
    full_sahi_detections: int
    budgeted_detections: int
    full_sahi_detector_images: int
    budgeted_detector_images: int
    detector_call_reduction: float
    tile_recall: float


def _write_synthetic_manifest(root: Path) -> Path:
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "train.hex").write_text(
        "10 20 30 40 50 60 70 80 90 A0 B0 C0 D0 E0 F0 01\n",
        encoding="utf-8",
    )
    (inputs / "val.hex").write_text(
        "01 03 05 07 09 0B 0D 0F 11 13 15 17 19 1B 1D 1F\n",
        encoding="utf-8",
    )
    document = {
        "version": 1,
        "name": "synthetic-malware-localization-smoke",
        "categories": [{"id": 1, "name": "synthetic_malicious_evidence"}],
        "samples": [
            {
                "sample_id": "synthetic-train-001",
                "source": "inputs/train.hex",
                "split": "train",
                "encoding": "opcode-3gram-rgb",
                "width": 4,
                "family_id": "synthetic-family-train",
                "annotations": [
                    {
                        "category_id": 1,
                        "start": 4,
                        "end": 9,
                        "annotation_source": "synthetic",
                        "verified": True,
                    }
                ],
            },
            {
                "sample_id": "synthetic-val-001",
                "source": "inputs/val.hex",
                "split": "val",
                "encoding": "opcode-3gram-rgb",
                "width": 4,
                "family_id": "synthetic-family-val",
                "annotations": [
                    {
                        "category_id": 1,
                        "start": 7,
                        "end": 12,
                        "annotation_source": "synthetic",
                        "verified": True,
                    }
                ],
            },
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def run_smoke(output_dir: Path) -> SmokeSummary:
    """Run safe data preparation and three detector-neutral baselines."""

    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"smoke output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = _write_synthetic_manifest(output_dir)
    prepared = prepare_dataset(
        manifest_path,
        output_dir / "dataset",
        allow_sensitive_output=True,
    )

    image = Image.new("RGB", (64, 64), color=(8, 8, 8))
    draw = ImageDraw.Draw(image)
    ground_truth = (40.0, 40.0, 52.0, 52.0)
    draw.rectangle(ground_truth, fill=(255, 0, 0))
    image.save(output_dir / "synthetic_detection.png")

    detector = RedBlobFakeDetector()
    full_image = FullImageStrategy().run(image, detector)
    full_sahi_strategy = FullSahiStrategy(
        tile_width=32,
        tile_height=32,
        overlap=0.0,
        batch_size=2,
    )
    full_sahi = full_sahi_strategy.run(image, detector)
    budgeted_strategy = BudgetedSahiStrategy(
        tile_width=32,
        tile_height=32,
        overlap=0.0,
        budget=0.5,
        coverage_ratio=0.0,
        batch_size=2,
    )
    budgeted = budgeted_strategy.run(
        image,
        detector,
        risk_scores=(0.1, 0.2, 0.3, 1.0),
    )
    tiles = generate_tile_grid(64, 64, tile_width=32, tile_height=32, overlap=0.0)
    selected_tiles = [tiles[index] for index in budgeted.selected_indices]

    summary = SmokeSummary(
        output_dir=output_dir,
        prepared_samples=prepared.sample_count,
        prepared_annotations=prepared.annotation_count,
        full_image_detections=len(full_image.detections),
        full_sahi_detections=len(full_sahi.detections),
        budgeted_detections=len(budgeted.detections),
        full_sahi_detector_images=full_sahi.detector_images,
        budgeted_detector_images=budgeted.detector_images,
        detector_call_reduction=detector_call_reduction(
            full_sahi.detector_images,
            budgeted.detector_images,
        ),
        tile_recall=tile_recall(selected_tiles, [ground_truth]),
    )
    (output_dir / "smoke_summary.json").write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return summary
