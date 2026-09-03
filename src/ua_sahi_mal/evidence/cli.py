"""Command line for the v2 evidence protocol.

    python -m ua_sahi_mal.evidence prepare  --archive ... --labels ... --out ...
    python -m ua_sahi_mal.evidence synth    --manifest ... --rasters ... --out ...
    python -m ua_sahi_mal.evidence train    --manifest ... --rasters ... --out ...
    python -m ua_sahi_mal.evidence run      --manifest ... --rasters ... --models ... --out ...
    python -m ua_sahi_mal.evidence smoke    --out ...

``smoke`` needs no dataset, no checkpoint, and no GPU: it builds a planted
sample, runs the whole protocol against a stub classifier with a known decision
rule, and checks the decision table comes out of it.  That is what the container
runs to prove the environment works.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ua_sahi_mal.evidence import (
    classifiers,
    corpus,
    criteria,
    metrics,
    occlusion,
    protocol,
    raster,
    routing,
    search,
    synthetic,
    training,
)

# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def _iter_selected_dumps(directory: Path, selection: dict[str, int]) -> list[Path]:
    paths = []
    for identifier in sorted(selection):
        candidate = directory / f"{identifier}.bytes"
        if candidate.exists():
            paths.append(candidate)
    return paths


def command_prepare(args: argparse.Namespace) -> int:
    """Select a stratified subset, convert its dumps to rasters, write a manifest."""
    labels = corpus.read_labels(args.labels)
    selection = corpus.stratified_selection(labels, per_family=args.per_family, seed=args.seed)
    print(f"selected {len(selection)} samples ({args.per_family} per family cap)", flush=True)

    dumps = _iter_selected_dumps(Path(args.dumps), selection)
    missing = len(selection) - len(dumps)
    if missing:
        print(f"  {missing} selected samples are not present in {args.dumps}", flush=True)
    if not dumps:
        print("no .bytes files found -- extract the archive first", file=sys.stderr)
        return 2

    started = time.time()
    report = corpus.convert_dumps(
        dumps,
        selection,
        args.out,
        width=args.width,
        min_bytes=args.min_bytes,
    )
    manifest = corpus.write_manifest(
        report,
        Path(args.out).parent / "manifest.json",
        width=args.width,
        per_family=args.per_family,
        seed=args.seed,
        extra={"source_directory": str(args.dumps), "seconds": round(time.time() - started, 1)},
    )
    print(
        f"converted {len(report.converted)}  duplicates {len(report.duplicates)}  "
        f"failures {len(report.failures)}  -> {manifest}",
        flush=True,
    )
    print(json.dumps(corpus.family_counts(report.converted), indent=2))
    return 0


# ---------------------------------------------------------------------------
# synthetic control set
# ---------------------------------------------------------------------------


def command_synth(args: argparse.Namespace) -> int:
    entries, _ = corpus.read_manifest(args.manifest)
    pool_entries = corpus.split_entries(entries, corpus.SPLIT_TRAIN)
    host_entries = corpus.stratified_subset(
        corpus.split_entries(entries, corpus.SPLIT_TEST), per_family=args.per_family, seed=args.seed
    )
    if not host_entries or not pool_entries:
        print("need both a train split (donors) and a test split (hosts)", file=sys.stderr)
        return 2

    store = training.SampleStore(args.rasters)
    pool = synthetic.DonorPool.from_items(
        (entry.sample_id, entry.label, store.get(entry)) for entry in pool_entries
    )
    hosts = [(entry.sample_id, entry.label, store.get(entry)) for entry in host_entries]

    samples, rejections = synthetic.build_control_set(
        hosts,
        pool,
        seed=args.seed,
        block_bytes=args.block_bytes,
        blocks=args.blocks,
        max_pairs=args.pairs,
    )
    path = synthetic.save_control_set(samples, rejections, args.out, save_rasters=args.save_rasters)
    print(f"built {len(samples)} samples ({len(samples) // 2} matched pairs), "
          f"{len(rejections)} hosts rejected -> {path}")
    return 0


# ---------------------------------------------------------------------------
# train
# ---------------------------------------------------------------------------


def command_train(args: argparse.Namespace) -> int:
    config = training.TrainingConfig(epochs=args.epochs, seed=args.seed, batch_size=args.batch_size)
    summary = training.train_all(
        args.manifest,
        args.rasters,
        args.out,
        class_count=args.classes,
        config=config,
        skip_torch=args.skip_torch,
    )
    for name, report in summary["models"].items():
        validation = report.get("validation") if isinstance(report, dict) else None
        if validation:
            print(
                f"{name:10s} accuracy {validation['accuracy']:.3f}  macro-F1 {validation['macro_f1']:.3f}  "
                f"NLL {validation['mean_nll']:.3f}  ({report['seconds']:.0f}s)"
            )
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _load_models(directory: Path) -> dict[str, Any]:
    models: dict[str, Any] = {}
    text_path = directory / "classifier_text.npz"
    if text_path.exists():
        models[classifiers.MODEL_TEXT] = classifiers.TextClassifier.load(text_path)
    for name, filename, loader in (
        (classifiers.MODEL_TILED, "classifier_tiled.pt", classifiers.TiledClassifier.load),
        (classifiers.MODEL_THUMBNAIL, "classifier_thumbnail.pt", classifiers.ThumbnailClassifier.load),
    ):
        path = directory / filename
        if path.exists():
            try:
                models[name] = loader(path)
            except classifiers.TorchUnavailable as exc:
                print(f"  {name}: {exc}", file=sys.stderr)
    return models


def command_run(args: argparse.Namespace) -> int:
    config = protocol.ProtocolConfig(
        block_bytes=args.block_bytes,
        budget=args.budget,
        subset_per_family=args.per_family,
        seed=args.seed,
    )
    entries, _ = corpus.read_manifest(args.manifest)
    test = corpus.split_entries(entries, corpus.SPLIT_TEST)
    subset = corpus.stratified_subset(test, per_family=config.subset_per_family, seed=config.seed)
    store = training.SampleStore(args.rasters)

    models = _load_models(Path(args.models))
    searcher = models.get(classifiers.MODEL_TILED)
    if searcher is None:
        print("classifier A (tiled) is required for the search", file=sys.stderr)
        return 2
    verifiers = {
        name: model
        for name, model in models.items()
        if name in (classifiers.MODEL_THUMBNAIL, classifiers.MODEL_TEXT)
    }

    document: dict[str, Any] = {
        "format": protocol.RESULT_FORMAT,
        "config": config.to_dict(),
        "environment": protocol.environment_record(),
        "subset": [entry.sample_id for entry in subset],
        "stages": {},
    }

    calibration = None
    if args.synthetic:
        control, _ = synthetic.load_control_set(args.synthetic)
        calibration = protocol.calibrate_on_synthetic(searcher, control, config=config)
        document["stages"]["calibration"] = calibration.to_dict()
        print(f"D1 calibration: {calibration.summary}", flush=True)

    sweeps: dict[str, dict[str, search.SearchResult]] = {}
    sweep_stage, primary = protocol.exhaustive_sweep(
        searcher, subset, store, config=config, fill_name=occlusion.PRIMARY_FILL
    )
    sweeps[occlusion.PRIMARY_FILL] = primary
    document["stages"]["exhaustive"] = sweep_stage.to_dict()
    print(f"sweep: {sweep_stage.summary}", flush=True)

    if args.fill_robustness:
        for name in config.fills:
            if name == occlusion.PRIMARY_FILL:
                continue
            stage, results = protocol.exhaustive_sweep(
                searcher, subset, store, config=config, fill_name=name
            )
            sweeps[name] = results
            document["stages"][f"exhaustive_{name}"] = stage.to_dict()

    ablation = protocol.budget_ablation(searcher, subset, store, primary, config=config)
    document["stages"]["ablation"] = ablation.to_dict()
    print(f"routing arms: {json.dumps(ablation.summary.get('arms', []), indent=2)}", flush=True)

    cross = protocol.cross_checks(subset, store, primary, verifiers=verifiers, config=config)
    document["stages"]["cross_checks"] = cross.to_dict()

    agreement = protocol.fill_agreement(sweeps, config=config) if len(sweeps) > 1 else None
    if agreement is not None:
        document["stages"]["fill_agreement"] = agreement.to_dict()

    document["decision"] = protocol.build_decision_table(
        calibration=calibration,
        ablation=ablation,
        cross=cross,
        agreement=agreement,
        ua_measured=routing.UPSAMPLE_UA in config.upsamplers,
    )
    path = protocol.write_results(document, Path(args.out) / "evidence_results.json")
    print(json.dumps(document["decision"]["criteria"], indent=2, ensure_ascii=False))
    print(f"paper standing: {document['decision']['paper_standing']}  -> {path}")
    return 0


# ---------------------------------------------------------------------------
# smoke
# ---------------------------------------------------------------------------


class _StubClassifier:
    """Two classes, decided by the density of one marker byte.

    Stands in for a trained network so the pipeline can be exercised with no
    dataset and no checkpoint.  Because its decision rule is known, the smoke
    test can assert that the search finds the planted range rather than merely
    that it ran.
    """

    name = "stub"
    class_count = 2

    def __init__(self, marker: int = 0xE7) -> None:
        self.marker = marker

    def log_probabilities(self, data: np.ndarray, valid=None) -> np.ndarray:
        density = float((data == self.marker).mean())
        probability = 0.02 + 0.96 * min(density / 0.15, 1.0)
        return np.log(np.array([1.0 - probability, probability]))

    def negative_log_likelihood(self, data: np.ndarray, label: int, valid=None) -> float:
        return float(-self.log_probabilities(data)[label])


def command_smoke(args: argparse.Namespace) -> int:
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    model = _StubClassifier()
    config = protocol.ProtocolConfig(seed=0, bootstrap_iterations=200)

    rows = []
    recalls = []
    for index in range(args.samples):
        size = 300_000
        data = rng.integers(0, 224, size=size, dtype=np.uint8)
        start = int(rng.integers(0, (size - 20_000) // 4096)) * 4096
        end = start + 3 * 4096
        data[start:end] = model.marker
        truth = [(start, end)]

        full = search.exhaustive_search(
            model, data, 1, sample_id=f"smoke{index}", block_bytes=config.block_bytes
        )
        found = search.evidence_ranges(full, budget=3 / full.block_count)
        iou = metrics.byte_iou(found, truth, size)

        budgeted = search.budgeted_search(
            model,
            data,
            1,
            sample_id=f"smoke{index}",
            block_bytes=config.block_bytes,
            budget=config.budget,
            router=routing.ROUTE_ENTROPY,
        )
        recall = metrics.evidence_recall_at_budget(
            full.probed_deltas(), np.flatnonzero(budgeted.probed)
        )
        necessity = search.verify_necessity(
            model, data, 1, np.asarray(truth), sample_id=f"smoke{index}", model_name="stub"
        )
        rows.append(
            {
                "sample": f"smoke{index}",
                "byte_iou": iou,
                "evidence_recall_entropy_router": recall,
                "delta_evidence": necessity.delta_evidence,
                "delta_control": necessity.delta_control,
                "exhaustive_forward_passes": full.forward_passes,
                "budgeted_forward_passes": budgeted.forward_passes,
            }
        )
        recalls.append(recall)

    ious = [row["byte_iou"] for row in rows]
    summary = {
        "format": "evidence-smoke-1",
        "samples": len(rows),
        "mean_byte_iou": float(np.mean(ious)),
        "min_byte_iou": float(np.min(ious)),
        "mean_delta_evidence": float(np.mean([row["delta_evidence"] for row in rows])),
        "mean_delta_control": float(np.mean([row["delta_control"] for row in rows])),
        "mean_forward_pass_saving": float(
            1.0
            - np.mean([row["budgeted_forward_passes"] for row in rows])
            / np.mean([row["exhaustive_forward_passes"] for row in rows])
        ),
        "environment": protocol.environment_record(),
        "rows": rows,
    }
    finite = [value for value in recalls if np.isfinite(value)]
    summary["mean_evidence_recall_entropy_router"] = float(np.mean(finite)) if finite else None

    checks = {
        "search_recovers_planted_range": bool(np.min(ious) >= criteria.BYTE_IOU_FLOOR),
        "evidence_beats_random_control": bool(
            summary["mean_delta_evidence"] > summary["mean_delta_control"]
        ),
        "budget_reduces_forward_passes": bool(summary["mean_forward_pass_saving"] > 0.5),
    }
    summary["checks"] = checks
    summary["passed"] = all(checks.values())

    protocol.write_results(summary, output / "evidence_smoke.json")
    print(json.dumps({**checks, "mean_byte_iou": summary["mean_byte_iou"]}, indent=2))
    return 0 if summary["passed"] else 1


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ua_sahi_mal.evidence", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="stratify, rasterize, and write a manifest")
    prepare.add_argument("--dumps", required=True, help="directory of extracted .bytes files")
    prepare.add_argument("--labels", required=True, help="trainLabels.csv")
    prepare.add_argument("--out", required=True, help="raster output directory")
    prepare.add_argument("--per-family", type=int, default=200)
    prepare.add_argument("--width", type=int, default=raster.DEFAULT_WIDTH)
    prepare.add_argument("--min-bytes", type=int, default=64 * 1024)
    prepare.add_argument("--seed", type=int, default=0)
    prepare.set_defaults(handler=command_prepare)

    synth = subparsers.add_parser("synth", help="build the synthetic control set")
    synth.add_argument("--manifest", required=True)
    synth.add_argument("--rasters", required=True)
    synth.add_argument("--out", required=True)
    synth.add_argument("--pairs", type=int, default=24)
    synth.add_argument("--per-family", type=int, default=4)
    synth.add_argument("--blocks", type=int, default=4)
    synth.add_argument("--block-bytes", type=int, default=criteria.PRIMARY_BLOCK_BYTES)
    synth.add_argument("--save-rasters", action="store_true")
    synth.add_argument("--seed", type=int, default=0)
    synth.set_defaults(handler=command_synth)

    train = subparsers.add_parser("train", help="train classifiers A, B and C_text")
    train.add_argument("--manifest", required=True)
    train.add_argument("--rasters", required=True)
    train.add_argument("--out", required=True)
    train.add_argument("--classes", type=int, default=9)
    train.add_argument("--epochs", type=int, default=training.DEFAULT_EPOCHS)
    train.add_argument("--batch-size", type=int, default=training.DEFAULT_BATCH)
    train.add_argument("--skip-torch", action="store_true")
    train.add_argument("--seed", type=int, default=0)
    train.set_defaults(handler=command_train)

    run = subparsers.add_parser("run", help="run the protocol and emit the decision table")
    run.add_argument("--manifest", required=True)
    run.add_argument("--rasters", required=True)
    run.add_argument("--models", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--synthetic", help="synthetic control set directory (enables D1)")
    run.add_argument("--per-family", type=int, default=5)
    run.add_argument("--budget", type=float, default=criteria.PRIMARY_BUDGET)
    run.add_argument("--block-bytes", type=int, default=criteria.PRIMARY_BLOCK_BYTES)
    run.add_argument("--fill-robustness", action="store_true", help="repeat the sweep per fill (D4)")
    run.add_argument("--seed", type=int, default=0)
    run.set_defaults(handler=command_run)

    smoke = subparsers.add_parser("smoke", help="end-to-end check with no dataset and no checkpoint")
    smoke.add_argument("--out", required=True)
    smoke.add_argument("--samples", type=int, default=4)
    smoke.set_defaults(handler=command_smoke)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
