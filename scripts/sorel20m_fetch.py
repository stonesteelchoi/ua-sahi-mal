"""Gated download of selected SOREL-20M disarmed binaries into an isolated path.

Guards enforced before any byte is fetched:
  * --accept-terms is required (SOREL Terms acknowledgement).
  * the destination must be an isolated path (not a repo, not a sync folder).
  * a byte budget cap (--budget-mb) is enforced against the preflight total.

Binaries are stored as ``<sha>.zlib`` exactly as served. This script NEVER
decompresses and NEVER re-arms (Machine/Subsystem stay zeroed). Decompression is
done later, only in an approved static-only isolated environment, by other code.

Runs on the operator's isolated machine (needs the AWS CLI). Not run in the cloud
session.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.acquire import (  # noqa: E402
    AwsCliClient,
    AwsCliNotFoundError,
    assert_within_budget,
    fetch,
    preflight,
    read_preflight_csv,
)
from ua_sahi_mal.sorel.manifest import read_manifest, write_manifest  # noqa: E402
from ua_sahi_mal.sorel.record import build_run_record, write_run_record  # noqa: E402


def _read_shalist(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sha-list", required=True, help="selected_sha256.txt (one SHA per line)")
    p.add_argument("--dest-dir", required=True,
                   help=r"isolated directory, e.g. D:\datasets\sorel20m-private\compressed")
    p.add_argument("--budget-mb", type=float, required=True,
                   help="hard cap on total download size in MB")
    p.add_argument("--accept-terms", action="store_true",
                   help="acknowledge the SOREL Terms; required to download")
    p.add_argument("--terms-revision", default="",
                   help="identifier/date of the SOREL Terms revision you accepted (recorded)")
    p.add_argument("--record-prefix", default=None,
                   help="isolated prefix for the acquisition record JSON (default: <dest-dir>/../acquisition)")
    p.add_argument("--bucket", default="sorel-20m")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--aws-bin", default="aws", help="AWS CLI executable (name on PATH or full path)")
    p.add_argument("--manifest", default=None,
                   help="private (effective) manifest CSV to update in place with s3_etag/content_length/"
                        "download_status/stored_artifact_sha256/zlib_status")
    p.add_argument("--preflight-csv", default=None,
                   help="reuse HEAD results from sorel20m_preflight --out-csv instead of re-HEADing "
                        "(only shas present and ok in the CSV are fetched; others are skipped as not-preflighted)")
    p.add_argument("--verbose", action="store_true",
                   help="print one line per SHA (default: SHA-free summary; details in the manifest/record)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.accept_terms:
        print("error: refusing to download without --accept-terms (SOREL Terms acknowledgement)",
              file=sys.stderr)
        return 2

    shas = _read_shalist(ns.sha_list)
    try:
        client = AwsCliClient(bucket=ns.bucket, aws=ns.aws_bin)
    except AwsCliNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if ns.preflight_csv:
        by_sha = {h.sha256: h for h in read_preflight_csv(ns.preflight_csv)}
        missing = [s_ for s_ in shas if s_ not in by_sha]
        if missing:
            print(f"error: {len(missing)} sha(s) in --sha-list are absent from --preflight-csv; "
                  "re-run preflight on this list first", file=sys.stderr)
            return 3
        heads = [by_sha[s_] for s_ in shas]
    else:
        heads = preflight(shas, client)
    max_bytes = int(ns.budget_mb * 1024 * 1024)
    try:
        total = assert_within_budget([h for h in heads if h.ok], max_bytes=max_bytes)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(f"preflight total: {total} bytes ({total / (1024*1024):.1f} MB) within cap "
          f"{ns.budget_mb:.1f} MB")

    results = fetch(shas, client, ns.dest_dir, terms_accepted=True, max_bytes=max_bytes,
                    preflighted=heads, overwrite=ns.overwrite)

    ok = sum(1 for r in results if r.download_status in ("ok", "skipped:exists"))

    if ns.manifest:
        head_by = {h.sha256: h for h in heads}
        res_by = {r.sha256: r for r in results}
        rows = read_manifest(ns.manifest)
        for row in rows:
            r = res_by.get(row.sorel_original_sha256)
            if r is None:
                continue
            h = head_by.get(row.sorel_original_sha256)
            row.s3_etag = h.etag if h and h.ok else row.s3_etag
            row.content_length = r.content_length or row.content_length
            row.download_status = r.download_status
            row.stored_artifact_sha256 = r.stored_artifact_sha256 or row.stored_artifact_sha256
            row.zlib_status = r.zlib_status
        write_manifest(ns.manifest, rows)

    # Acquisition provenance record (amendment §9): access time, Terms revision, code
    # commit, budget, per-status counts. Hashes/paths/counts only; no binary content.
    status_counts: dict[str, int] = {}
    for r in results:
        key = r.download_status.split(":", 1)[0]
        status_counts[key] = status_counts.get(key, 0) + 1
    rec_prefix = ns.record_prefix or str(Path(ns.dest_dir).resolve().parent / "acquisition")
    record = build_run_record(
        "sorel_acquisition", repo_root=Path(__file__).resolve().parents[1],
        terms_accepted=True, terms_revision=ns.terms_revision,
        bucket=ns.bucket, sha_list=str(Path(ns.sha_list).resolve()), n_requested=len(shas),
        budget_mb=ns.budget_mb, preflight_total_bytes=total,
        dest_dir=str(Path(ns.dest_dir).resolve()), status_counts=status_counts,
        kept_compressed=True, never_rearmed=True,
    )
    record_path = write_run_record(f"{rec_prefix}_record.json", record)
    if ns.verbose:
        for r in results:
            print(f"{r.download_status:16s} {r.sha256}  {r.dest}")
    else:
        for key, n in sorted(status_counts.items(), key=lambda kv: -kv[1]):
            print(f"{key:16s} x{n}")
    print(f"\nstored {ok}/{len(results)} artefacts (kept zlib-compressed) in {ns.dest_dir}")
    print(f"record: {record_path}")
    print("REMINDER: do not decompress or re-arm here; that is a later static-only step.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
