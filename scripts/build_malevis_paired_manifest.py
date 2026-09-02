from __future__ import annotations

import argparse
import json
from pathlib import Path

from ua_sahi_mal.malevis_experiment import MaleVisExperimentError, build_paired_malevis_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one immutable, leak-controlled split shared by MaleVis 224 and 300."
    )
    parser.add_argument("--root-224", type=Path, required=True)
    parser.add_argument("--root-300", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    try:
        document = build_paired_malevis_manifest(args.root_224, args.root_300)
    except (MaleVisExperimentError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "eligible_sample_count": document["eligible_sample_count"],
        "eligible_split_counts": document["eligible_split_counts"],
        "excluded_sample_count": document["excluded_sample_count"],
        "split_mismatch_count": len(document["cross_resolution_split_mismatches"]),
        "label_mismatch_count": len(document["cross_resolution_label_mismatches"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
