"""Thin, lazy Ultralytics adapters for reproducible train/validation commands."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class YoloTrainConfig:
    data: Path
    model: str = "yolo11n.pt"
    epochs: int = 100
    image_size: int = 640
    batch_size: int = 16
    device: str = "auto"
    seed: int = 42
    project: Path = Path("runs/train")
    name: str = "ua-sahi-mal-yolo11"

    def validate(self) -> None:
        if not self.data.is_file():
            raise ValueError(f"dataset YAML does not exist: {self.data}")
        if self.epochs < 1 or self.image_size < 1 or self.batch_size < 1:
            raise ValueError("epochs, image_size, and batch_size must be positive")
        if not self.name.strip():
            raise ValueError("run name must not be empty")


@dataclass(frozen=True)
class YoloEvaluateConfig:
    data: Path
    model: str
    split: str = "test"
    image_size: int = 640
    batch_size: int = 16
    device: str = "auto"
    project: Path = Path("runs/val")
    name: str = "ua-sahi-mal-evaluation"
    metrics_json: Path | None = None
    metrics_csv: Path | None = None
    dataset_revision: str | None = None

    def validate(self) -> None:
        if not self.data.is_file():
            raise ValueError(f"dataset YAML does not exist: {self.data}")
        if self.split not in {"val", "test"}:
            raise ValueError("split must be val or test")
        if self.image_size < 1 or self.batch_size < 1:
            raise ValueError("image_size and batch_size must be positive")
        if (
            self.metrics_json is not None
            and self.metrics_csv is not None
            and self.metrics_json.resolve() == self.metrics_csv.resolve()
        ):
            raise ValueError("metrics_json and metrics_csv must be different files")
        for output in (self.metrics_json, self.metrics_csv):
            if output is not None and output.exists():
                raise ValueError(f"refusing to overwrite metrics output: {output}")


def _ultralytics_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("Ultralytics is required; install the project dependencies first") from exc
    return YOLO


def _device_value(device: str) -> str | int:
    if device == "auto":
        return ""
    if device.startswith("cuda:"):
        return int(device.split(":", 1)[1])
    return device


def train_yolo(config: YoloTrainConfig) -> Any:
    """Train YOLO11 using a prepared dataset YAML; returns Ultralytics results."""

    from ua_sahi_mal.offline import enforce_offline_network

    config.validate()
    enforce_offline_network()
    model = _ultralytics_yolo()(config.model)
    return model.train(
        data=str(config.data),
        epochs=config.epochs,
        imgsz=config.image_size,
        batch=config.batch_size,
        device=_device_value(config.device),
        seed=config.seed,
        deterministic=True,
        project=str(config.project),
        name=config.name,
        # Ultralytics plotting may fetch a font even when YOLO_OFFLINE=true.
        # Disable it so the training path stays within the static/offline contract.
        plots=False,
    )


def evaluate_yolo(config: YoloEvaluateConfig) -> Any:
    """Run a fixed validation/test split without changing detector weights."""

    from ua_sahi_mal.offline import enforce_offline_network

    config.validate()
    enforce_offline_network()
    model = _ultralytics_yolo()(config.model)
    result = model.val(
        data=str(config.data),
        split=config.split,
        imgsz=config.image_size,
        batch=config.batch_size,
        device=_device_value(config.device),
        project=str(config.project),
        name=config.name,
        plots=False,
    )
    if config.metrics_json is not None or config.metrics_csv is not None:
        write_evaluation_metrics(
            evaluation_metrics_document(result, config),
            json_path=config.metrics_json,
            csv_path=config.metrics_csv,
        )
    return result


def _finite_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def evaluation_metrics_document(result: Any, config: YoloEvaluateConfig) -> dict[str, Any]:
    """Convert Ultralytics metrics into stable, paper-table-friendly JSON."""

    metrics: dict[str, float] = {}
    results_dict = getattr(result, "results_dict", None)
    if isinstance(results_dict, Mapping):
        for key, value in results_dict.items():
            number = _finite_number(value)
            if number is not None:
                metrics[str(key)] = number
    box = getattr(result, "box", None)
    if box is not None:
        for key, attribute in (
            ("box_map50_95", "map"),
            ("box_map50", "map50"),
            ("box_map75", "map75"),
        ):
            number = _finite_number(getattr(box, attribute, None))
            if number is not None:
                metrics[key] = number
    speed: dict[str, float] = {}
    raw_speed = getattr(result, "speed", None)
    if isinstance(raw_speed, Mapping):
        for key, value in raw_speed.items():
            number = _finite_number(value)
            if number is not None:
                speed[str(key)] = number
    return {
        "schema": "ua-sahi-mal-yolo-evaluation-v1",
        "measured": True,
        "dataset": str(config.data),
        "dataset_revision": config.dataset_revision,
        "model": config.model,
        "split": config.split,
        "image_size": config.image_size,
        "batch_size": config.batch_size,
        "device": config.device,
        "metrics": dict(sorted(metrics.items())),
        "speed_ms_per_image": dict(sorted(speed.items())),
        "notes": {
            "ap_s": "not available from the default Ultralytics summary; use COCO size-stratified evaluation",
            "tile_recall": "not measured by this detector-only command",
            "detector_calls": "not measured by this detector-only command",
            "vram": "not measured by this detector-only command",
        },
    }


def write_evaluation_metrics(
    document: dict[str, Any],
    *,
    json_path: Path | None,
    csv_path: Path | None,
) -> None:
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("section", "metric", "value"))
            writer.writeheader()
            for section in ("metrics", "speed_ms_per_image"):
                for metric, value in document.get(section, {}).items():
                    writer.writerow({"section": section, "metric": metric, "value": value})
