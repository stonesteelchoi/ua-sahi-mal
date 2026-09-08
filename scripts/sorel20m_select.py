"""Freeze a deterministic, time-split, tag-stratified SOREL-20M selection.

Reads only ``meta.db`` (no network, no binaries) and writes, to an ISOLATED path
(never the repo, never a sync folder):

  * ``<out_prefix>_manifest.csv``   — full private manifest (all metadata + status columns)
  * ``<out_prefix>_selected_sha256.txt`` — one 64-hex SHA per line (primary rows only)

G0-S: the SHA manifest is NOT publishable without written authorization. The path
guard refuses to write it inside a repository tree or a cloud-sync folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.manifest import rows_from_selection, write_manifest  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402
from ua_sahi_mal.sorel.select import SPLITS, select  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--meta-db", required=True, help="path to SOREL meta.db (read-only)")
    p.add_argument("--out-prefix", required=True,
                   help=r"isolated output prefix, e.g. D:\datasets\sorel20m-private\selection_v1")
    p.add_argument("--seed", required=True, help="selection seed string (frozen)")
    p.add_argument("--train", type=int, default=0)
    p.add_argument("--validation", type=int, default=0)
    p.add_argument("--test", type=int, default=0)
    p.add_argument("--table", default="meta")
    p.add_argument("--include-reserve-in-shalist", action="store_true",
                   help="also list reserve rows in the selected_sha256.txt file")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    targets = {"train": ns.train, "validation": ns.validation, "test": ns.test}
    if sum(targets.values()) == 0:
        print("error: at least one of --train/--validation/--test must be > 0", file=sys.stderr)
        return 2

    manifest_path = assert_isolated_output(f"{ns.out_prefix}_manifest.csv", kind="manifest")
    shalist_path = assert_isolated_output(f"{ns.out_prefix}_selected_sha256.txt", kind="SHA list")

    selection = select(ns.meta_db, seed=ns.seed, targets=targets, table=ns.table)
    rows = rows_from_selection(selection, seed=ns.seed)
    write_manifest(manifest_path, rows)

    roles = {"primary"} if not ns.include_reserve_in_shalist else {"primary", "reserve"}
    shas = [r.sorel_original_sha256 for r in rows if r.selection_role in roles]
    shalist_path.write_text("".join(f"{s}\n" for s in shas), encoding="utf-8")

    for split in SPLITS:
        sel = selection[split]
        print(f"{split:11s} target={sel.target:5d} selected={len(sel.selected):5d} "
              f"reserve={len(sel.reserve):5d}")
    print(f"manifest : {manifest_path}")
    print(f"sha list : {shalist_path}  ({len(shas)} shas)")
    print("NOTE (G0-S): this SHA manifest is NOT publishable without written authorization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
