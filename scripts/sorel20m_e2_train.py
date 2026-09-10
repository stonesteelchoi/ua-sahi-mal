"""E2 v3 training: content-only tile models on the SOREL train split (E2_prereg_v3).

Trains the ``meanmax`` (TiledNet-parity; drives attr_tile_conf / attr_occlusion)
and ``attention`` (gated attention-MIL; drives mil_attention) models on the
dominant behavior tag, evaluates on the validation split, applies the
pre-registered model sanity gate, and saves checkpoints + a SHA-free report to an
isolated directory.

Samples are decompressed IN MEMORY (static-only) from the isolated compressed
dir; nothing decompressed is written to disk. The silver evidence is never used.
Runs on the operator machine (cau GPU); ``--limit-*`` allows a quick smoke run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.e2_dataset import SorelTileStore, load_label_set  # noqa: E402
from ua_sahi_mal.sorel.e2_models import save_checkpoint  # noqa: E402
from ua_sahi_mal.sorel.e2_train import TrainConfig, train_model  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, help="selection_v2_manifest_effective.csv (isolated)")
    p.add_argument("--compressed-dir", required=True, help="isolated dir with <sha>.zlib files")
    p.add_argument("--out-dir", required=True, help="isolated dir for checkpoints + reports")
    p.add_argument("--static-only", action="store_true", help="affirm static-only isolated env (required)")
    p.add_argument("--pooling", default="both", choices=["meanmax", "attention", "both"])
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--accumulate", type=int, default=16)
    p.add_argument("--max-train-tiles", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", default="auto", help="auto | cuda | cpu")
    p.add_argument("--min-class-support", type=int, default=150)
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--cache-gb", type=float, default=8.0, help="RAM cache for decoded tiles (never disk)")
    p.add_argument("--limit-train", type=int, default=0, help="smoke: use only the first N train samples")
    p.add_argument("--limit-val", type=int, default=0, help="smoke: use only the first N val samples")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.static_only:
        print("error: refusing to decompress without --static-only", file=sys.stderr)
        return 2
    out_dir = Path(ns.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    assert_isolated_output(out_dir / "e2v3_probe", kind="training output dir")

    labels = load_label_set(ns.manifest, min_class_support=ns.min_class_support)
    summary = labels.public_summary()
    print("classes:", summary["classes"])
    print("train support:", summary["train_support"])
    print("splits:", summary["splits"])

    train = labels.split("train", trainable_only=True)
    val = labels.split("validation", trainable_only=True)
    if ns.limit_train:
        train = train[: ns.limit_train]
    if ns.limit_val:
        val = val[: ns.limit_val]
    print(f"training on {len(train)} samples, validating on {len(val)}; classes={labels.class_count}")

    store = SorelTileStore(ns.compressed_dir, static_only=True, cache_bytes=int(ns.cache_gb * (1 << 30)))
    poolings = ["meanmax", "attention"] if ns.pooling == "both" else [ns.pooling]
    overall_ok = True
    for pooling in poolings:
        config = TrainConfig(pooling=pooling, epochs=ns.epochs, accumulate=ns.accumulate,
                             max_train_tiles=ns.max_train_tiles, learning_rate=ns.lr, seed=ns.seed,
                             device=ns.device)
        print(f"\n=== training {pooling} on {config.device} ===")
        model, report = train_model(train, store, class_count=labels.class_count, config=config, validation=val)
        ckpt = out_dir / f"e2v3_{pooling}.pt"
        save_checkpoint(model, ckpt, meta={"prereg_version": "E2_prereg_v3", "class_names": labels.class_names,
                                            "config": config.to_dict(), "sanity": report.sanity})
        report_path = assert_isolated_output(out_dir / f"e2v3_{pooling}_train_report.json", kind="train report")
        report_path.write_text(json.dumps({**report.to_dict(), "label_summary": summary}, ensure_ascii=False,
                                          indent=2), encoding="utf-8")
        print(f"validation: {report.validation}")
        print(f"sanity gate: {'PASS' if report.sanity.get('pass') else 'FAIL'}  {report.sanity}")
        print(f"checkpoint: {ckpt}\nreport: {report_path}  ({report.seconds:.0f}s)")
        overall_ok = overall_ok and bool(report.sanity.get("pass"))
    print("\nMODEL SANITY GATE:", "PASS" if overall_ok else "FAIL (attribution evaluation must not proceed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
