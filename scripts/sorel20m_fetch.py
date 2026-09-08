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
    assert_within_budget,
    fetch,
    preflight,
)


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
    p.add_argument("--bucket", default="sorel-20m")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.accept_terms:
        print("error: refusing to download without --accept-terms (SOREL Terms acknowledgement)",
              file=sys.stderr)
        return 2

    shas = _read_shalist(ns.sha_list)
    client = AwsCliClient(bucket=ns.bucket)

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
    for r in results:
        print(f"{r.download_status:16s} {r.sha256}  {r.dest}")
    print(f"\nstored {ok}/{len(results)} artefacts (kept zlib-compressed) in {ns.dest_dir}")
    print("REMINDER: do not decompress or re-arm here; that is a later static-only step.")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
