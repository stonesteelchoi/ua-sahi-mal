from __future__ import annotations

import argparse
import json
from pathlib import Path

from ua_sahi_mal.malevis_experiment import MaleVisExperimentError, aggregate_malevis_runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate immutable MaleVis seed/resolution runs.")
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = aggregate_malevis_runs(args.run_dir, args.output_dir)
    except (MaleVisExperimentError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps({
        "aggregate": str((args.output_dir / "aggregate.json").resolve()),
        "run_count": result["run_count"],
        "group_count": len(result["groups"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
