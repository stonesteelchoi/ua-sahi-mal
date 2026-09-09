"""Apply deterministic reserve replacements after a preflight/fetch/static stage.

Reads a (frozen or effective) private manifest plus the stage's per-sha results,
excludes failed effective rows with a recorded reason, promotes the next reserve of
the same split in frozen order, and writes DERIVED files only:

  <out_prefix>_manifest_effective.csv   full manifest with updated roles/exclusions
  <out_prefix>_effective_sha256.txt     current effective sample (one sha per line)
  <out_prefix>_replacement_record.json  SHA-free counts + reasons + provenance

The frozen selection files are never overwritten (refused if targeted). Newly
promoted replacements have NOT been preflighted yet: re-run sorel20m_preflight on the
effective list, then re-run this tool with the new CSV until nothing fails.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.acquire import read_preflight_csv  # noqa: E402
from ua_sahi_mal.sorel.manifest import read_manifest, write_manifest  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402
from ua_sahi_mal.sorel.record import build_run_record, file_identity, write_run_record  # noqa: E402
from ua_sahi_mal.sorel.replace import apply_replacements, effective_rows  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, help="input manifest CSV (frozen or a previous *_effective)")
    p.add_argument("--preflight-csv", required=True, help="per-sha results for the current effective list")
    p.add_argument("--out-prefix", required=True, help="isolated output prefix for the derived files")
    p.add_argument("--stage", default="preflight", choices=["preflight", "fetch", "static"],
                   help="stage label recorded in exclusion_reason")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    in_manifest = Path(ns.manifest).resolve()
    out_manifest = assert_isolated_output(f"{ns.out_prefix}_manifest_effective.csv", kind="effective manifest")
    out_shalist = assert_isolated_output(f"{ns.out_prefix}_effective_sha256.txt", kind="effective SHA list")
    if out_manifest == in_manifest:
        print("error: refusing to overwrite the input manifest; the frozen selection must stay intact "
              "(use a different --out-prefix)", file=sys.stderr)
        return 2

    rows = read_manifest(in_manifest)
    results = read_preflight_csv(ns.preflight_csv)
    new_rows, report = apply_replacements(rows, results, stage=ns.stage)

    write_manifest(out_manifest, new_rows)
    eff = effective_rows(new_rows)
    out_shalist.write_text("".join(f"{r.sorel_original_sha256}\n" for r in eff), encoding="utf-8")

    record = build_run_record(
        "sorel_replacement", repo_root=Path(__file__).resolve().parents[1],
        input_manifest=file_identity(in_manifest), results_csv=file_identity(ns.preflight_csv),
        report=report.as_dict(), effective_count=len(eff),
        outputs={"manifest_effective": str(out_manifest), "effective_sha_list": str(out_shalist)},
        publication_status="INTERNAL_ONLY (G0-S)",
    )
    record_path = write_run_record(f"{ns.out_prefix}_replacement_record.json", record)

    print(f"stage={ns.stage}  excluded={report.excluded}  promoted={report.promoted}  "
          f"effective={len(eff)}")
    for split, d in report.per_split.items():
        print(f"  {split:11s} excluded={d['excluded']:3d} promoted={d['promoted']:3d} "
              f"effective_after={d['effective_after']:4d} reserve_remaining={d['reserve_remaining']:3d}")
    for reason, n in sorted(report.reasons.items(), key=lambda kv: -kv[1]):
        print(f"  reason x{n}: {reason}")
    if report.reserve_exhausted:
        print(f"WARNING: reserve exhausted for split(s): {report.reserve_exhausted}", file=sys.stderr)
    print(f"manifest_effective : {out_manifest}")
    print(f"effective sha list : {out_shalist}")
    print(f"record             : {record_path}")
    if report.promoted:
        print("NEXT: re-run sorel20m_preflight on the effective list; promoted replacements are not yet preflighted.")
    return 0 if not report.reserve_exhausted else 1


if __name__ == "__main__":
    raise SystemExit(main())
