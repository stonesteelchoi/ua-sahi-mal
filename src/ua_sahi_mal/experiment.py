"""Versioned experiment protocol loader used to freeze primary comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "dataset",
        "detector",
        "slicing",
        "routing",
        "merge",
        "success",
        "runtime",
    }
)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True)
class DatasetProtocol:
    name: str
    modality: str
    manifest: str
    annotation_policy: str


@dataclass(frozen=True)
class DetectorProtocol:
    name: str
    checkpoint: str
    input_size: int


@dataclass(frozen=True)
class SlicingProtocol:
    tile_height: int
    tile_width: int
    overlap_ratio: float
    budget_fraction: float


@dataclass(frozen=True)
class RoutingProtocol:
    probability_weight: float
    entropy_weight: float
    guard_threshold: float
    coverage_fraction: float


@dataclass(frozen=True)
class MergeProtocol:
    method: str
    match_metric: str
    threshold: float
    class_aware: bool


@dataclass(frozen=True)
class SuccessProtocol:
    primary_metric: str
    maximum_loss_points: float
    minimum_detector_call_reduction: float
    minimum_latency_reduction: float


@dataclass(frozen=True)
class RuntimeProtocol:
    seed: int
    device: str
    warmup_runs: int
    measured_runs: int
    latency_statistic: str


@dataclass(frozen=True)
class ExperimentProtocol:
    schema_version: int
    experiment_id: str
    dataset: DatasetProtocol
    detector: DetectorProtocol
    slicing: SlicingProtocol
    routing: RoutingProtocol
    merge: MergeProtocol
    success: SuccessProtocol
    runtime: RuntimeProtocol

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError("experiment schema_version must be 1")
        if not self.experiment_id.strip():
            raise ValueError("experiment_id must not be empty")
        if not all(
            value.strip()
            for value in (
                self.dataset.name,
                self.dataset.modality,
                self.dataset.manifest,
                self.dataset.annotation_policy,
            )
        ):
            raise ValueError("dataset protocol values must not be empty")
        if self.detector.name not in {"yolo11", "efficientdet"}:
            raise ValueError("detector.name must be yolo11 or efficientdet")
        if not self.detector.checkpoint.strip() or self.detector.input_size < 1:
            raise ValueError("detector checkpoint and positive input_size are required")
        if self.slicing.tile_height < 1 or self.slicing.tile_width < 1:
            raise ValueError("slice dimensions must be positive")
        if not 0 <= self.slicing.overlap_ratio < 1:
            raise ValueError("overlap_ratio must be in [0, 1)")
        if not 0 < self.slicing.budget_fraction <= 1:
            raise ValueError("budget_fraction must be in (0, 1]")
        if self.routing.probability_weight < 0 or self.routing.entropy_weight < 0:
            raise ValueError("routing weights must be non-negative")
        if self.routing.probability_weight + self.routing.entropy_weight <= 0:
            raise ValueError("at least one routing weight must be positive")
        if not 0 <= self.routing.guard_threshold <= 1:
            raise ValueError("guard_threshold must be in [0, 1]")
        if not 0 <= self.routing.coverage_fraction <= 1:
            raise ValueError("coverage_fraction must be in [0, 1]")
        if self.merge.method != "greedy_nmm":
            raise ValueError("merge.method must be greedy_nmm")
        if self.merge.match_metric not in {"iou", "ios"}:
            raise ValueError("merge.match_metric must be iou or ios")
        if not 0 <= self.merge.threshold <= 1:
            raise ValueError("merge.threshold must be in [0, 1]")
        if self.success.primary_metric != "AP_S":
            raise ValueError("the pre-registered primary metric must remain AP_S")
        if self.success.maximum_loss_points < 0:
            raise ValueError("maximum_loss_points must be non-negative")
        for name, value in (
            ("minimum_detector_call_reduction", self.success.minimum_detector_call_reduction),
            ("minimum_latency_reduction", self.success.minimum_latency_reduction),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.runtime.warmup_runs < 0 or self.runtime.measured_runs < 1:
            raise ValueError("runtime requires non-negative warmup and positive measured runs")
        if self.runtime.latency_statistic != "p95_end_to_end_ms":
            raise ValueError("latency_statistic must be p95_end_to_end_ms")


def _mapping(value: Any, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def _construct(cls: type, values: dict[str, Any], key: str):
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValueError(f"invalid {key} fields: {exc}") from exc


def load_experiment_protocol(path: Path) -> ExperimentProtocol:
    if not path.is_file():
        raise ValueError(f"experiment config does not exist: {path}")
    try:
        root = _mapping(
            yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader),
            "config",
        )
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid experiment YAML: {exc}") from exc
    unknown = sorted(str(key) for key in set(root) - _ROOT_KEYS)
    if unknown:
        raise ValueError(f"unknown experiment config fields: {', '.join(unknown)}")
    try:
        protocol = ExperimentProtocol(
            schema_version=root["schema_version"],
            experiment_id=root["experiment_id"],
            dataset=_construct(DatasetProtocol, _mapping(root["dataset"], "dataset"), "dataset"),
            detector=_construct(
                DetectorProtocol, _mapping(root["detector"], "detector"), "detector"
            ),
            slicing=_construct(SlicingProtocol, _mapping(root["slicing"], "slicing"), "slicing"),
            routing=_construct(RoutingProtocol, _mapping(root["routing"], "routing"), "routing"),
            merge=_construct(MergeProtocol, _mapping(root["merge"], "merge"), "merge"),
            success=_construct(SuccessProtocol, _mapping(root["success"], "success"), "success"),
            runtime=_construct(RuntimeProtocol, _mapping(root["runtime"], "runtime"), "runtime"),
        )
    except KeyError as exc:
        raise ValueError(f"missing experiment config section: {exc.args[0]}") from exc
    protocol.validate()
    return protocol
