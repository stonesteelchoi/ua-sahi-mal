from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from ua_sahi_mal.malevis_experiment import (
    MaleVisExperimentError,
    load_malevis_settings,
    run_malevis_experiment,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one immutable DECODE-inspired MaleVis classification experiment."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--paired-manifest",
        type=Path,
        help="Recommended shared 224/300 split manifest from build_malevis_paired_manifest.py.",
    )
    parser.add_argument(
        "--image-size",
        type=int,
        help="Override only the image_size token for the matching 224/300 dataset tree.",
    )
    parser.add_argument("--epochs", type=int, help="Optional resource-bounded pilot override.")
    parser.add_argument("--batch-size", type=int, help="Optional hardware-memory override.")
    parser.add_argument("--torch-threads", type=int, help="Optional CPU thread override.")
    parser.add_argument(
        "--skip-timing",
        action="store_true",
        help="Skip repeated p50/p95 benchmarking on non-representative seeds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        settings = load_malevis_settings(args.config)
        replacements = {}
        for argument, field in (
            (args.image_size, "image_size"),
            (args.epochs, "epochs"),
            (args.batch_size, "batch_size"),
            (args.torch_threads, "torch_threads"),
        ):
            if argument is not None:
                replacements[field] = argument
        if replacements:
            settings = replace(settings, **replacements)
            settings.validate()
        summary = run_malevis_experiment(
            dataset_root=args.dataset_root,
            output_dir=args.output_dir,
            settings=settings,
            seed=args.seed,
            paired_manifest=args.paired_manifest,
            benchmark_timing=not args.skip_timing,
        )
    except (MaleVisExperimentError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({
        "summary": str((args.output_dir / "summary.json").resolve()),
        "seed": summary["seed"],
        "image_size": summary["image_size"],
        "deterministic_accuracy": summary["evaluation"]["deterministic"]["metrics"]["accuracy"],
        "deterministic_macro_f1": summary["evaluation"]["deterministic"]["metrics"]["macro_f1"],
        "mc_accuracy": summary["evaluation"]["mc_dropout"]["metrics"]["accuracy"],
        "mc_macro_f1": summary["evaluation"]["mc_dropout"]["metrics"]["macro_f1"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
