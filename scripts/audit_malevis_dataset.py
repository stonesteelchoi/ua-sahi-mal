from __future__ import annotations

import argparse
import json
from pathlib import Path

from ua_sahi_mal.malevis_experiment import MaleVisExperimentError, audit_malevis_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit one MaleVis train/val image tree without changing dataset files."
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--image-size", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--no-content-hashes",
        action="store_true",
        help="Use path/size fingerprint only; exact duplicate detection will be unavailable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    try:
        audit = audit_malevis_dataset(
            args.dataset_root,
            expected_image_size=args.image_size,
            hash_files=not args.no_content_hashes,
            verify_images=True,
        )
    except MaleVisExperimentError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "class_count": audit["class_count"],
        "split_counts": audit["split_counts"],
        "invalid_image_count": audit["invalid_image_count"],
        "cross_split_duplicate_group_count": audit["cross_split_duplicate_group_count"],
        "dataset_fingerprint_sha256": audit["dataset_fingerprint_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
