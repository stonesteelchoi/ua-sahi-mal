from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import click

from ua_sahi_mal.dataset import (
    ManifestError,
    manifest_template,
    prepare_dataset,
    summary_to_json,
    validate_manifest,
)
from ua_sahi_mal.encoding import SUPPORTED_ENCODINGS, encode_path, save_encoded_png, sha256_file


@click.group()
def main() -> None:
    """Prepare, validate, train, and evaluate UA-SAHI-MAL experiments."""


@main.command("doctor")
@click.option("--skip-upsample-smoke", is_flag=True, help="Skip the bilinear shape smoke test.")
@click.option("--strict", is_flag=True, help="Exit non-zero when dependencies or submodules are missing.")
def doctor_command(skip_upsample_smoke: bool, strict: bool) -> None:
    """Print environment, CUDA, package, and submodule diagnostics."""

    from ua_sahi_mal.doctor import print_doctor

    issues = print_doctor(skip_upsample_smoke)
    if strict and issues:
        raise click.ClickException("; ".join(issues))


@main.command("manifest-template")
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="New JSON file to create.",
)
def manifest_template_command(output: Path) -> None:
    """Write a safe version-1 dataset manifest example."""

    if output.exists():
        raise click.ClickException(f"refusing to overwrite existing file: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest_template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(f"Manifest template: {output.resolve()}")


@main.command("encode")
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--mode", type=click.Choice(sorted(SUPPORTED_ENCODINGS)), required=True)
@click.option("--width", type=click.IntRange(1, 8192), default=256, show_default=True)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="New PNG path; an adjacent metadata JSON file is also written.",
)
@click.option("--max-input-mib", type=click.IntRange(1, 4096), default=64, show_default=True)
@click.option(
    "--allow-sensitive-output",
    is_flag=True,
    help="Acknowledge that encoded pixels can reveal the original source stream.",
)
def encode_command(
    source: Path,
    mode: str,
    width: int,
    output: Path,
    max_input_mib: int,
    allow_sensitive_output: bool,
) -> None:
    """Convert one local artifact to a non-executing RGB visualization."""

    metadata_path = output.with_suffix(output.suffix + ".json")
    if output.suffix.lower() != ".png":
        raise click.ClickException("--output must use a .png extension")
    if not allow_sensitive_output:
        raise click.ClickException(
            "encoded RGB can preserve source bytes/opcodes; choose an approved non-Git "
            "output location and pass --allow-sensitive-output"
        )
    if output.exists() or metadata_path.exists():
        raise click.ClickException("refusing to overwrite an existing image or metadata file")
    try:
        encoded = encode_path(
            source.resolve(),
            mode=mode,
            width=width,
            max_input_bytes=max_input_mib * 1024 * 1024,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    save_encoded_png(encoded, output)
    metadata = {
        "source_name": source.name,
        "source_sha256": sha256_file(source),
        "encoding": encoded.metadata.to_dict(),
        "image": str(output.resolve()),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(f"Encoded image: {output.resolve()}")
    click.echo(f"Coordinate metadata: {metadata_path.resolve()}")


@main.command("encode-behavior-report")
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Already-produced static CAPE-shaped JSON report.",
)
@click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--metadata-output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--max-input-mib", type=click.IntRange(1, 4096), default=64, show_default=True)
@click.option(
    "--allow-sensitive-output",
    is_flag=True,
    help="Acknowledge that API-sequence images are sensitive derived artifacts.",
)
def encode_behavior_report_command(
    source: Path,
    output: Path,
    metadata_output: Path | None,
    max_input_mib: int,
    allow_sensitive_output: bool,
) -> None:
    """Render four API categories from static JSON; never run or control a sandbox."""

    from ua_sahi_mal.behavior_encoding import (
        BehaviorEncodingError,
        encode_behavior_report,
        save_behavior_visualization,
    )

    if output.suffix.lower() != ".png":
        raise click.ClickException("--output must use a .png extension")
    if not allow_sensitive_output:
        raise click.ClickException(
            "behavior images preserve API ordering; pass --allow-sensitive-output after "
            "choosing an approved non-Git output location"
        )
    if metadata_output is None:
        metadata_output = output.with_suffix(output.suffix + ".json")
    try:
        image, metadata = encode_behavior_report(
            source,
            max_input_bytes=max_input_mib * 1024 * 1024,
        )
        save_behavior_visualization(
            image,
            metadata,
            output=output,
            metadata_output=metadata_output,
        )
    except (BehaviorEncodingError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Behavior image: {output.resolve()}")
    click.echo(f"Behavior metadata: {metadata_output.resolve()}")


@main.command("validate-data")
@click.option(
    "--manifest",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--max-input-mib", type=click.IntRange(1, 4096), default=64, show_default=True)
def validate_data_command(manifest: Path, max_input_mib: int) -> None:
    """Validate source hashes, boxes, categories, and split leakage."""

    try:
        validated = validate_manifest(
            manifest,
            max_input_bytes=max_input_mib * 1024 * 1024,
        )
    except ManifestError as exc:
        raise click.ClickException(str(exc)) from exc
    split_counts: dict[str, int] = {}
    for sample in validated.samples:
        split_counts[sample.spec.split] = split_counts.get(sample.spec.split, 0) + 1
    click.echo(
        json.dumps(
            {
                "valid": True,
                "name": validated.manifest.name,
                "samples": len(validated.samples),
                "categories": len(validated.manifest.categories),
                "split_counts": split_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("validate-config")
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def validate_config_command(config: Path) -> None:
    """Validate the frozen primary metric, budget, routing, merge, and timing contract."""

    from ua_sahi_mal.experiment import load_experiment_protocol

    try:
        protocol = load_experiment_protocol(config)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "valid": True,
                "experiment_id": protocol.experiment_id,
                "dataset": protocol.dataset.name,
                "detector": protocol.detector.name,
                "primary_metric": protocol.success.primary_metric,
                "budget_fraction": protocol.slicing.budget_fraction,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("paper-table-template")
@click.option("--experiment-id", required=True)
@click.option("--dataset-revision", required=True)
@click.option("--checkpoint-sha256")
@click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
def paper_table_template_command(
    experiment_id: str,
    dataset_revision: str,
    checkpoint_sha256: str | None,
    output: Path,
) -> None:
    """Create a frozen strategy/metric table with explicit unmeasured cells."""

    from ua_sahi_mal.paper_results import (
        PaperResultError,
        paper_table_template,
        validate_paper_table,
    )

    if output.exists():
        raise click.ClickException(f"refusing to overwrite paper table template: {output}")
    try:
        document = validate_paper_table(
            paper_table_template(
                experiment_id=experiment_id,
                dataset_revision=dataset_revision,
                checkpoint_sha256=checkpoint_sha256,
            )
        )
    except PaperResultError as exc:
        raise click.ClickException(str(exc)) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(f"Paper table template: {output.resolve()}")


@main.command("compile-paper-table")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--output-json", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--output-csv", required=True, type=click.Path(dir_okay=False, path_type=Path))
def compile_paper_table_command(
    input_path: Path,
    output_json: Path,
    output_csv: Path,
) -> None:
    """Validate measured cells, calculate eligible gates, and export JSON/CSV."""

    from ua_sahi_mal.paper_results import PaperResultError, load_paper_table, write_paper_table

    try:
        document = load_paper_table(input_path)
        write_paper_table(document, json_path=output_json, csv_path=output_csv)
    except (OSError, PaperResultError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "json": str(output_json.resolve()),
                "csv": str(output_csv.resolve()),
                "primary_assessments": document["primary_assessments"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@main.command("import-decode")
@click.option(
    "--annotation",
    "annotations",
    multiple=True,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="DECODE ROI JSON. Repeat for multiple category files.",
)
@click.option(
    "--images-root",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--split-map",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--dataset-name", required=True)
@click.option("--annotation-version", required=True)
@click.option("--teacher-model", required=True)
@click.option(
    "--class-policy",
    type=click.Choice(["class-agnostic", "roi-family"]),
    default="class-agnostic",
    show_default=True,
)
def import_decode_command(
    annotations: tuple[Path, ...],
    images_root: Path,
    split_map: Path,
    output: Path,
    dataset_name: str,
    annotation_version: str,
    teacher_model: str,
    class_policy: str,
) -> None:
    """Import already-generated DECODE PNG/JPEG and ROI JSON; never execute samples."""

    from ua_sahi_mal.decode_adapter import DecodeImportError, import_decode_roi

    try:
        summary = import_decode_roi(
            annotations,
            images_root=images_root,
            split_map_path=split_map,
            output_path=output,
            dataset_name=dataset_name,
            annotation_version=annotation_version,
            teacher_model=teacher_model,
            class_policy=class_policy,
        )
    except (DecodeImportError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))


@main.command("validate-checkpoint")
@click.option(
    "--model",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Local Ultralytics .pt checkpoint; network model identifiers are not accepted.",
)
@click.option(
    "--data",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Prepared dataset YAML whose ordered class names must match the checkpoint.",
)
@click.option("--dataset-revision")
@click.option("--expected-sha256")
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="New JSON metadata file to create.",
)
def validate_checkpoint_command(
    model: Path,
    data: Path,
    dataset_revision: str | None,
    expected_sha256: str | None,
    output: Path,
) -> None:
    """Restricted-load a checkpoint and enforce the malware class contract."""

    from ua_sahi_mal.checkpoint import (
        CheckpointValidationError,
        dataset_classes,
        inspect_checkpoint,
        write_checkpoint_metadata,
    )

    try:
        metadata = inspect_checkpoint(
            model,
            expected_classes=dataset_classes(data),
            expected_sha256=expected_sha256,
            dataset_revision=dataset_revision,
        )
        write_checkpoint_metadata(metadata, output)
    except (CheckpointValidationError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(metadata), ensure_ascii=False, indent=2))


@main.command("evaluate-predictions")
@click.option(
    "--predictions",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--ground-truth",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--image-name")
@click.option("--iou-threshold", type=float, default=0.5, show_default=True)
@click.option("--output-json", required=True, type=click.Path(dir_okay=False, path_type=Path))
@click.option("--output-csv", type=click.Path(dir_okay=False, path_type=Path))
def evaluate_predictions_command(
    predictions: Path,
    ground_truth: Path,
    image_name: str | None,
    iou_threshold: float,
    output_json: Path,
    output_csv: Path | None,
) -> None:
    """Match saved prediction boxes against fixture or COCO ground truth."""

    from ua_sahi_mal.evaluation import (
        evaluate_localization,
        load_ground_truth_boxes,
        load_prediction_boxes,
        write_localization_evaluation,
    )

    for output in (output_json, output_csv):
        if output is not None and output.exists():
            raise click.ClickException(f"refusing to overwrite evaluation output: {output}")
    try:
        evaluation = evaluate_localization(
            load_prediction_boxes(predictions),
            load_ground_truth_boxes(ground_truth, image_name=image_name),
            iou_threshold=iou_threshold,
        )
        write_localization_evaluation(
            evaluation,
            json_path=output_json,
            csv_path=output_csv,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(evaluation), ensure_ascii=False, indent=2))


@main.command("record-run")
@click.option(
    "--repo-root",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--base-model",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--annotation",
    "annotations",
    multiple=True,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--split-map",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--manifest",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--data",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--dataset-revision", required=True)
@click.option("--teacher-model", required=True)
@click.option("--annotation-version", required=True)
@click.option(
    "--class-policy",
    type=click.Choice(["class-agnostic", "roi-family"]),
    default="class-agnostic",
    show_default=True,
)
@click.option("--epochs", type=click.IntRange(min=1), required=True)
@click.option("--batch-size", type=click.IntRange(min=1), required=True)
@click.option("--image-size", type=click.IntRange(min=1), required=True)
@click.option("--device", required=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option(
    "--best-checkpoint",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--output", required=True, type=click.Path(dir_okay=False, path_type=Path))
def record_run_command(
    repo_root: Path,
    base_model: Path,
    annotations: tuple[Path, ...],
    split_map: Path,
    manifest: Path,
    data: Path,
    dataset_revision: str,
    teacher_model: str,
    annotation_version: str,
    class_policy: str,
    epochs: int,
    batch_size: int,
    image_size: int,
    device: str,
    seed: int,
    best_checkpoint: Path | None,
    output: Path,
) -> None:
    """Write immutable hashes, runtime versions, split, and training inputs."""

    from ua_sahi_mal.checkpoint import CheckpointValidationError, dataset_classes
    from ua_sahi_mal.provenance import create_pipeline_record, write_pipeline_record

    try:
        record = create_pipeline_record(
            repo_root=repo_root,
            base_model=base_model,
            annotation_paths=annotations,
            split_map=split_map,
            manifest=manifest,
            dataset_revision=dataset_revision,
            teacher_model=teacher_model,
            annotation_version=annotation_version,
            class_policy=class_policy,
            epochs=epochs,
            batch_size=batch_size,
            image_size=image_size,
            device=device,
            seed=seed,
            best_checkpoint=best_checkpoint,
            expected_classes=dataset_classes(data),
        )
        write_pipeline_record(record, output)
    except (CheckpointValidationError, OSError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(record, ensure_ascii=False, indent=2, default=str))


@main.command("prepare-data")
@click.option(
    "--manifest",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--output-dir", required=True, type=click.Path(path_type=Path))
@click.option("--max-input-mib", type=click.IntRange(1, 4096), default=64, show_default=True)
@click.option(
    "--allow-sensitive-output",
    is_flag=True,
    help="Acknowledge that prepared images may be reversible and must stay outside Git.",
)
def prepare_data_command(
    manifest: Path,
    output_dir: Path,
    max_input_mib: int,
    allow_sensitive_output: bool,
) -> None:
    """Create PNG, YOLO, COCO, checksum, and provenance artifacts."""

    try:
        summary = prepare_dataset(
            manifest,
            output_dir,
            max_input_bytes=max_input_mib * 1024 * 1024,
            allow_sensitive_output=allow_sensitive_output,
        )
    except (ManifestError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(summary_to_json(summary))


@main.command("smoke")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="New output directory. Defaults to a timestamped path under runs/smoke.",
)
def smoke_command(output_dir: Path | None) -> None:
    """Run a CPU-only synthetic data and baseline workflow."""

    from ua_sahi_mal.smoke import run_smoke

    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("runs/smoke") / stamp
    try:
        summary = run_smoke(output_dir)
    except (ManifestError, OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))


@main.command("train")
@click.option(
    "--data",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--model",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Existing local base checkpoint/model definition; remote identifiers are not accepted.",
)
@click.option("--epochs", type=click.IntRange(min=1), default=100, show_default=True)
@click.option("--image-size", type=click.IntRange(min=1), default=640, show_default=True)
@click.option("--batch-size", type=click.IntRange(min=1), default=16, show_default=True)
@click.option("--device", default="auto", show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--project", type=click.Path(path_type=Path), default=Path("runs/train"), show_default=True)
@click.option("--name", default="ua-sahi-mal-yolo11", show_default=True)
def train_command(
    data: Path,
    model: Path,
    epochs: int,
    image_size: int,
    batch_size: int,
    device: str,
    seed: int,
    project: Path,
    name: str,
) -> None:
    """Train the primary YOLO11 baseline on a prepared dataset."""

    from ua_sahi_mal.training import YoloTrainConfig, train_yolo

    config = YoloTrainConfig(
        data=data.resolve(),
        model=str(model.resolve()),
        epochs=epochs,
        image_size=image_size,
        batch_size=batch_size,
        device=device,
        seed=seed,
        project=project.resolve(),
        name=name,
    )
    try:
        train_yolo(config)
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("evaluate")
@click.option(
    "--data",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--model",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option("--split", type=click.Choice(["val", "test"]), default="test", show_default=True)
@click.option("--image-size", type=click.IntRange(min=1), default=640, show_default=True)
@click.option("--batch-size", type=click.IntRange(min=1), default=16, show_default=True)
@click.option("--device", default="auto", show_default=True)
@click.option("--project", type=click.Path(path_type=Path), default=Path("runs/val"), show_default=True)
@click.option("--name", default="ua-sahi-mal-evaluation", show_default=True)
@click.option("--metrics-json", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--metrics-csv", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--dataset-revision")
def evaluate_command(
    data: Path,
    model: Path,
    split: str,
    image_size: int,
    batch_size: int,
    device: str,
    project: Path,
    name: str,
    metrics_json: Path | None,
    metrics_csv: Path | None,
    dataset_revision: str | None,
) -> None:
    """Evaluate a fixed YOLO11 checkpoint on val or test."""

    from ua_sahi_mal.checkpoint import (
        CheckpointValidationError,
        dataset_classes,
        inspect_checkpoint,
    )
    from ua_sahi_mal.training import YoloEvaluateConfig, evaluate_yolo

    config = YoloEvaluateConfig(
        data=data.resolve(),
        model=str(model.resolve()),
        split=split,
        image_size=image_size,
        batch_size=batch_size,
        device=device,
        project=project.resolve(),
        name=name,
        metrics_json=metrics_json.resolve() if metrics_json is not None else None,
        metrics_csv=metrics_csv.resolve() if metrics_csv is not None else None,
        dataset_revision=dataset_revision,
    )
    try:
        inspect_checkpoint(
            model,
            expected_classes=dataset_classes(data),
            dataset_revision=dataset_revision,
        )
        evaluate_yolo(config)
    except (CheckpointValidationError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("predict")
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--model",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Local malware-specific .pt checkpoint. COCO checkpoints are rejected.",
)
@click.option(
    "--data",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional dataset YAML for exact checkpoint class-order validation.",
)
@click.option("--dataset-revision", help="Dataset revision recorded with checkpoint metadata.")
@click.option(
    "--output-dir",
    default=Path("runs/ua_sahi_mal"),
    type=click.Path(path_type=Path),
    show_default=True,
)
@click.option("--device", default="auto", show_default=True)
@click.option(
    "--upsampler",
    type=click.Choice(["auto", "upa", "jbu", "bilinear"]),
    default="auto",
    show_default=True,
)
@click.option(
    "--coarse-mode",
    type=click.Choice(["dense", "boxes"]),
    default="dense",
    show_default=True,
    help="dense uses pre-NMS P3/P4/P5 logits; boxes is the legacy fallback.",
)
@click.option("--route-scale", type=int, default=16, show_default=True)
@click.option("--slice-height", type=int, default=400, show_default=True)
@click.option("--slice-width", type=int, default=400, show_default=True)
@click.option("--overlap", type=float, default=0.2, show_default=True)
@click.option("--budget", type=float, default=0.5, show_default=True)
@click.option("--confidence", type=float, default=0.25, show_default=True)
@click.option("--route-confidence", type=float, default=0.05, show_default=True)
@click.option("--guard-threshold", type=float, default=0.15, show_default=True)
@click.option("--coverage-ratio", type=float, default=0.2, show_default=True)
@click.option("--top-fraction", type=float, default=0.1, show_default=True)
@click.option("--probability-weight", type=float, default=0.8, show_default=True)
@click.option("--entropy-weight", type=float, default=0.2, show_default=True)
@click.option("--box-weight", type=float, default=0.85, show_default=True)
@click.option("--texture-weight", type=float, default=0.15, show_default=True)
@click.option("--batch-size", type=int, default=1, show_default=True)
@click.option("--image-size", type=int, default=640, show_default=True)
@click.option("--no-standard-pred", is_flag=True)
@click.option(
    "--ground-truth",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional expected.json or COCO JSON for this image.",
)
@click.option("--iou-threshold", type=float, default=0.5, show_default=True)
@click.option(
    "--tile-recall-coverage",
    type=click.FloatRange(min=0.0, max=1.0, min_open=True),
    default=0.5,
    show_default=True,
    help="Minimum fraction of one GT box that a selected tile must cover.",
)
def predict_command(
    source: Path,
    model: Path,
    data: Path | None,
    dataset_revision: str | None,
    output_dir: Path,
    device: str,
    upsampler: str,
    coarse_mode: str,
    route_scale: int,
    slice_height: int,
    slice_width: int,
    overlap: float,
    budget: float,
    confidence: float,
    route_confidence: float,
    guard_threshold: float,
    coverage_ratio: float,
    top_fraction: float,
    probability_weight: float,
    entropy_weight: float,
    box_weight: float,
    texture_weight: float,
    batch_size: int,
    image_size: int,
    no_standard_pred: bool,
    ground_truth: Path | None,
    iou_threshold: float,
    tile_recall_coverage: float,
) -> None:
    """Run UA/JBU-guided selective SAHI on one approved, prepared image."""

    from PIL import Image

    from ua_sahi_mal.artifacts import save_artifacts
    from ua_sahi_mal.checkpoint import (
        CheckpointValidationError,
        dataset_classes,
        inspect_checkpoint,
    )
    from ua_sahi_mal.config import PredictConfig, resolve_device
    from ua_sahi_mal.doctor import collect_versions
    from ua_sahi_mal.inference import load_detection_model, run_selective_sahi
    from ua_sahi_mal.upsampling import build_upsampler

    resolved_device = resolve_device(device)
    config = PredictConfig(
        source=source.resolve(),
        model=str(model.resolve()),
        output_dir=output_dir.resolve(),
        device=resolved_device,
        upsampler=upsampler,
        coarse_mode=coarse_mode,
        route_scale=route_scale,
        slice_height=slice_height,
        slice_width=slice_width,
        overlap=overlap,
        budget=budget,
        confidence=confidence,
        route_confidence=route_confidence,
        guard_threshold=guard_threshold,
        coverage_ratio=coverage_ratio,
        top_fraction=top_fraction,
        probability_weight=probability_weight,
        entropy_weight=entropy_weight,
        box_weight=box_weight,
        texture_weight=texture_weight,
        batch_size=batch_size,
        image_size=image_size,
        include_standard_prediction=not no_standard_pred,
    )
    try:
        config.validate()
        checkpoint_metadata = inspect_checkpoint(
            model,
            expected_classes=dataset_classes(data) if data is not None else None,
            dataset_revision=dataset_revision,
        )
        routing_upsampler = build_upsampler(upsampler, resolved_device)
    except (CheckpointValidationError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        click.echo(f"Loading {model} on {resolved_device}...")
        detection_model = load_detection_model(config, resolved_device)
        with Image.open(config.source) as opened:
            image = opened.convert("RGB")
        click.echo(f"Running {routing_upsampler.name}-guided selective SAHI...")
        result = run_selective_sahi(image, detection_model, routing_upsampler, config)
        paths = save_artifacts(
            image=image,
            result=result,
            config=config,
            device=resolved_device,
            versions=collect_versions(),
        )
        summary = json.loads(paths.summary.read_text(encoding="utf-8"))
        summary["checkpoint"] = asdict(checkpoint_metadata)
        paths.summary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if ground_truth is not None:
        from ua_sahi_mal.evaluation import (
            evaluate_localization,
            load_ground_truth_boxes,
            load_prediction_boxes,
            tile_recall,
            write_localization_evaluation,
        )
        from ua_sahi_mal.strategies import Tile

        try:
            ground_truth_boxes = load_ground_truth_boxes(ground_truth, image_name=source.name)
            evaluation = evaluate_localization(
                load_prediction_boxes(paths.predictions),
                ground_truth_boxes,
                iou_threshold=iou_threshold,
            )
            routing_tile_recall = tile_recall(
                [
                    Tile(candidate.index, candidate.bbox)
                    for candidate in result.selection.selected
                ],
                [
                    (
                        record.bbox_xywh[0],
                        record.bbox_xywh[1],
                        record.bbox_xywh[0] + record.bbox_xywh[2],
                        record.bbox_xywh[1] + record.bbox_xywh[3],
                    )
                    for record in ground_truth_boxes
                ],
                minimum_object_coverage=tile_recall_coverage,
            )
            evaluation_json = paths.run_dir / "localization_evaluation.json"
            evaluation_csv = paths.run_dir / "localization_evaluation.csv"
            write_localization_evaluation(
                evaluation,
                json_path=evaluation_json,
                csv_path=evaluation_csv,
            )
            summary = json.loads(paths.summary.read_text(encoding="utf-8"))
            summary["ground_truth_evaluation"] = asdict(evaluation)
            summary["routing_ground_truth_evaluation"] = {
                "tile_recall": routing_tile_recall,
                "minimum_object_coverage": tile_recall_coverage,
                "ground_truth_objects": len(ground_truth_boxes),
                "candidate_tiles": len(result.selection.candidates),
                "selected_tiles": len(result.selection.selected_indices),
                "detector_images": len(result.selection.selected_indices) + 1,
                "detector_invocations": (
                    (len(result.selection.selected_indices) + config.batch_size - 1)
                    // config.batch_size
                    + 1
                ),
                "counting_note": "includes the one full-image coarse detector pass",
            }
            paths.summary.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            click.echo(
                "Ground truth: "
                f"precision={evaluation.precision:.4f}, recall={evaluation.recall:.4f}, "
                f"F1={evaluation.f1:.4f}, tile_recall={routing_tile_recall:.4f}"
            )
        except (OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Done: {len(result.selection.selected_indices)}/{len(result.selection.candidates)} tiles, "
        f"{len(result.prediction_result.object_prediction_list)} predictions"
    )
    click.echo(f"Artifacts: {paths.run_dir}")
