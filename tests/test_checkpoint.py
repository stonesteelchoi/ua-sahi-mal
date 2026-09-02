import json
from pathlib import Path

import pytest

from ua_sahi_mal.checkpoint import (
    COCO80,
    CheckpointValidationError,
    dataset_classes,
    inspect_checkpoint,
    write_checkpoint_metadata,
)
from ua_sahi_mal.encoding import sha256_file


class _Parameter:
    def __init__(self, size: int) -> None:
        self.size = size

    def numel(self) -> int:
        return self.size


class _Model:
    def __init__(self, names, *, task: str | None = "detect") -> None:
        self.names = names
        self.task = task

    def parameters(self):
        return [_Parameter(7), _Parameter(11)]


def _checkpoint_file(tmp_path: Path) -> Path:
    path = tmp_path / "best.pt"
    path.write_bytes(b"inert-test-checkpoint")
    return path


def test_inspect_checkpoint_enforces_class_contract_and_writes_metadata(tmp_path: Path) -> None:
    checkpoint = _checkpoint_file(tmp_path)
    model = _Model({0: "malicious_evidence"})

    metadata = inspect_checkpoint(
        checkpoint,
        expected_classes=["malicious_evidence"],
        expected_sha256=sha256_file(checkpoint),
        dataset_revision="decode-r1",
        loader=lambda _path: ({"ema": model, "train_args": {"data": "dataset.yaml"}}, "best.pt"),
    )
    output = tmp_path / "metadata.json"
    write_checkpoint_metadata(metadata, output)
    document = json.loads(output.read_text(encoding="utf-8"))

    assert metadata.class_names == ("malicious_evidence",)
    assert metadata.parameter_count == 18
    assert metadata.task == "detect"
    assert metadata.training_data == "dataset.yaml"
    assert metadata.safe_load
    assert document["sha256"] == sha256_file(checkpoint)
    assert document["dataset_revision"] == "decode-r1"

    with pytest.raises(CheckpointValidationError, match="refusing to overwrite"):
        write_checkpoint_metadata(metadata, output)


def test_inspect_checkpoint_rejects_coco_or_wrong_malware_classes(tmp_path: Path) -> None:
    checkpoint = _checkpoint_file(tmp_path)

    with pytest.raises(CheckpointValidationError, match="COCO object classes"):
        inspect_checkpoint(
            checkpoint,
            loader=lambda _path: {"model": _Model(list(COCO80))},
        )

    with pytest.raises(CheckpointValidationError, match="do not match dataset"):
        inspect_checkpoint(
            checkpoint,
            expected_classes=["malicious_evidence"],
            loader=lambda _path: {"model": _Model(["dropper"])},
        )


def test_inspect_checkpoint_validates_hash_before_loading(tmp_path: Path) -> None:
    checkpoint = _checkpoint_file(tmp_path)
    called = False

    def loader(_path: Path):
        nonlocal called
        called = True
        return {"model": _Model(["malicious_evidence"])}

    with pytest.raises(CheckpointValidationError, match="SHA-256 mismatch"):
        inspect_checkpoint(checkpoint, expected_sha256="0" * 64, loader=loader)

    assert not called


@pytest.mark.parametrize("task", ["classify", "segment"])
def test_inspect_checkpoint_requires_detection_task(tmp_path: Path, task: str) -> None:
    checkpoint = _checkpoint_file(tmp_path)

    with pytest.raises(CheckpointValidationError, match="task must be detect"):
        inspect_checkpoint(
            checkpoint,
            loader=lambda _path: {"model": _Model(["malicious_evidence"], task=task)},
        )


def test_dataset_classes_accepts_list_or_contiguous_mapping(tmp_path: Path) -> None:
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("names: [dropper, worm]\n", encoding="utf-8")
    mapping_yaml = tmp_path / "mapping.yaml"
    mapping_yaml.write_text("names:\n  0: dropper\n  1: worm\n", encoding="utf-8")

    assert dataset_classes(list_yaml) == ("dropper", "worm")
    assert dataset_classes(mapping_yaml) == ("dropper", "worm")

    invalid_yaml = tmp_path / "invalid.yaml"
    invalid_yaml.write_text("names:\n  1: worm\n", encoding="utf-8")
    with pytest.raises(CheckpointValidationError, match="contiguous"):
        dataset_classes(invalid_yaml)
