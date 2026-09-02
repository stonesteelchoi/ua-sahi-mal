"""Restricted Ultralytics checkpoint inspection and class-contract validation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml

from ua_sahi_mal.encoding import sha256_file

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
COCO80 = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)
_COCO_SENTINELS = frozenset({"person", "car", "airplane", "truck"})


class CheckpointValidationError(ValueError):
    """Raised when a checkpoint violates the detector experiment contract."""


@dataclass(frozen=True)
class CheckpointMetadata:
    path: str
    sha256: str
    size_bytes: int
    class_names: tuple[str, ...]
    class_count: int
    model_type: str
    task: str | None
    parameter_count: int | None
    training_data: str | None
    dataset_revision: str | None
    safe_load: bool = True


def _ordered_names(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        try:
            keys = sorted(value, key=lambda item: int(item))
        except (TypeError, ValueError) as exc:
            raise CheckpointValidationError("checkpoint class-name keys must be integer-like") from exc
        if [int(key) for key in keys] != list(range(len(keys))):
            raise CheckpointValidationError("checkpoint class names must be contiguous from zero")
        names = tuple(value[key] for key in keys)
    elif isinstance(value, (list, tuple)):
        names = tuple(value)
    else:
        raise CheckpointValidationError("checkpoint does not expose class names")
    if not names or any(not isinstance(name, str) or not name.strip() for name in names):
        raise CheckpointValidationError("checkpoint class names must be non-empty strings")
    normalized = tuple(name.strip() for name in names)
    if len({name.casefold() for name in normalized}) != len(normalized):
        raise CheckpointValidationError("checkpoint class names are not unique")
    return normalized


def dataset_classes(dataset_yaml: Path) -> tuple[str, ...]:
    if not dataset_yaml.is_file():
        raise CheckpointValidationError(f"dataset YAML does not exist: {dataset_yaml}")
    try:
        document = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CheckpointValidationError(f"cannot read dataset YAML: {exc}") from exc
    if not isinstance(document, dict) or "names" not in document:
        raise CheckpointValidationError("dataset YAML must define names")
    return _ordered_names(document["names"])


def _default_loader(path: Path) -> tuple[dict[str, Any], str]:
    from ua_sahi_mal.offline import enforce_offline_network

    enforce_offline_network()
    from ultralytics.nn.tasks import torch_safe_load

    return torch_safe_load(str(path), safe_only=True)


def _parameter_count(model: Any) -> int | None:
    parameters = getattr(model, "parameters", None)
    if not callable(parameters):
        return None
    try:
        return sum(int(parameter.numel()) for parameter in parameters())
    except (TypeError, RuntimeError):
        return None


def inspect_checkpoint(
    path: Path,
    *,
    expected_classes: Sequence[str] | None = None,
    expected_sha256: str | None = None,
    dataset_revision: str | None = None,
    loader: Callable[[Path], Any] | None = None,
) -> CheckpointMetadata:
    """Restricted-load a local checkpoint and enforce its class contract."""

    path = path.resolve()
    if not path.is_file():
        raise CheckpointValidationError(f"checkpoint does not exist locally: {path}")
    if path.suffix.lower() != ".pt":
        raise CheckpointValidationError("Ultralytics checkpoint must have a .pt suffix")
    digest = sha256_file(path)
    if expected_sha256 is not None:
        expected_sha256 = expected_sha256.lower()
        if _SHA256.fullmatch(expected_sha256) is None:
            raise CheckpointValidationError("expected SHA-256 must be 64 hexadecimal characters")
        if digest != expected_sha256:
            raise CheckpointValidationError(
                f"checkpoint SHA-256 mismatch: expected {expected_sha256}, got {digest}"
            )

    loaded = (loader or _default_loader)(path)
    checkpoint = loaded[0] if isinstance(loaded, tuple) else loaded
    if not isinstance(checkpoint, dict):
        raise CheckpointValidationError("checkpoint loader did not return an Ultralytics mapping")
    model = checkpoint.get("ema")
    if model is None:
        model = checkpoint.get("model")
    if model is None:
        raise CheckpointValidationError("checkpoint contains neither ema nor model weights")
    names = _ordered_names(getattr(model, "names", checkpoint.get("names")))
    folded = {name.casefold() for name in names}
    if folded == {name.casefold() for name in COCO80} or _COCO_SENTINELS.issubset(folded):
        raise CheckpointValidationError(
            "checkpoint exposes COCO object classes (person/car/airplane/truck); "
            "it is not a malware-specific detector"
        )
    if expected_classes is not None:
        expected = tuple(str(name).strip() for name in expected_classes)
        if names != expected:
            raise CheckpointValidationError(
                f"checkpoint classes {list(names)!r} do not match dataset classes {list(expected)!r}"
            )

    train_args = checkpoint.get("train_args")
    training_data = None
    task = getattr(model, "task", None)
    if isinstance(train_args, dict):
        if train_args.get("data") is not None:
            training_data = str(train_args["data"])
        if task is None and train_args.get("task") is not None:
            task = str(train_args["task"])
    if task is not None:
        task = str(task)
        if task != "detect":
            raise CheckpointValidationError(f"checkpoint task must be detect, got {task!r}")
    return CheckpointMetadata(
        path=str(path),
        sha256=digest,
        size_bytes=path.stat().st_size,
        class_names=names,
        class_count=len(names),
        model_type=type(model).__name__,
        task=task,
        parameter_count=_parameter_count(model),
        training_data=training_data,
        dataset_revision=dataset_revision,
    )


def write_checkpoint_metadata(metadata: CheckpointMetadata, output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise CheckpointValidationError(f"refusing to overwrite metadata output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(metadata), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
