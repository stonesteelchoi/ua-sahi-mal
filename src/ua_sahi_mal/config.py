from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PredictConfig:
    source: Path
    model: str = "yolo11n.pt"
    output_dir: Path = Path("runs/ua_sahi_mal")
    device: str = "auto"
    upsampler: str = "auto"
    coarse_mode: str = "dense"
    route_scale: int = 16
    slice_height: int = 400
    slice_width: int = 400
    overlap: float = 0.2
    budget: float = 0.5
    confidence: float = 0.25
    route_confidence: float = 0.05
    guard_threshold: float = 0.15
    coverage_ratio: float = 0.2
    top_fraction: float = 0.1
    probability_weight: float = 0.8
    entropy_weight: float = 0.2
    box_weight: float = 0.85
    texture_weight: float = 0.15
    batch_size: int = 1
    include_standard_prediction: bool = True
    postprocess_match_threshold: float = 0.5
    image_size: int = 640

    def validate(self) -> None:
        if not self.source.is_file():
            raise ValueError(f"source image does not exist: {self.source}")
        if self.upsampler not in {"auto", "upa", "jbu", "bilinear"}:
            raise ValueError("upsampler must be auto, upa, jbu, or bilinear")
        if self.coarse_mode not in {"dense", "boxes"}:
            raise ValueError("coarse_mode must be dense or boxes")
        if self.route_scale < 2:
            raise ValueError("route_scale must be at least 2")
        if self.slice_height <= 0 or self.slice_width <= 0:
            raise ValueError("slice dimensions must be positive")
        if not 0 <= self.overlap < 1:
            raise ValueError("overlap must be in [0, 1)")
        if not 0 < self.budget <= 1:
            raise ValueError("budget must be in (0, 1]")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if not 0 <= self.route_confidence <= 1:
            raise ValueError("route_confidence must be in [0, 1]")
        if self.route_confidence > self.confidence:
            raise ValueError("route_confidence must not exceed confidence")
        if not 0 <= self.guard_threshold <= 1:
            raise ValueError("guard_threshold must be in [0, 1]")
        if not 0 <= self.coverage_ratio <= 1:
            raise ValueError("coverage_ratio must be in [0, 1]")
        if not 0 < self.top_fraction <= 1:
            raise ValueError("top_fraction must be in (0, 1]")
        if self.probability_weight < 0 or self.entropy_weight < 0:
            raise ValueError("probability and entropy weights must be non-negative")
        if self.probability_weight == 0 and self.entropy_weight == 0:
            raise ValueError("at least one dense routing weight must be positive")
        if self.box_weight < 0 or self.texture_weight < 0:
            raise ValueError("routing weights must be non-negative")
        if self.box_weight == 0 and self.texture_weight == 0:
            raise ValueError("at least one routing weight must be positive")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.image_size <= 0:
            raise ValueError("image_size must be positive")


def resolve_device(requested: str) -> str:
    if requested != "auto":
        return requested

    try:
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
