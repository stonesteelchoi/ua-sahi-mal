"""HEAD-only preflight of a selected SHA list against s3://sorel-20m.

Downloads NOTHING. For each 64-hex SHA it issues an anonymous S3 head-object and
reports ContentLength + ETag, then prints the total byte budget so the operator
can confirm the download size before fetching.

Runs on the operator's isolated machine (needs the AWS CLI). Not run in the cloud
session.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.acquire import (  # noqa: E402
    AwsCliClient,
    AwsCliNotFoundError,
    budget_total,
    preflight,
)
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402


def _read_shalist(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sha-list", required=True, help="selected_sha256.txt (one SHA per line)")
    p.add_argument("--out-csv", help="optional isolated CSV to write preflight results")
    p.add_argument("--bucket", default="sorel-20m")
    p.add_argument("--budget-mb", type=float, default=None,
                   help="if set, warn when the total exceeds this many MB")
    p.add_argument("--aws-bin", default="aws", help="AWS CLI executable (name on PATH or full path)")
    p.add_argument("--verbose", action="store_true",
                   help="print one line per SHA (default: summary only; per-SHA detail goes to --out-csv). "
                        "G0-S: SHA lists are private — keep console output SHA-free unless needed.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    shas = _read_shalist(ns.sha_list)
    try:
        client = AwsCliClient(bucket=ns.bucket, aws=ns.aws_bin)
    except AwsCliNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    results = preflight(shas, client)

    ok = [r for r in results if r.ok]
    bad = [r for r in results if not r.ok]
    total = budget_total(results)
    total_mb = total / (1024 * 1024)

    if ns.verbose:
        for r in results:
            if r.ok:
                print(f"OK   {r.sha256}  {r.content_length:>10d}  {r.etag}")
            else:
                print(f"FAIL {r.sha256}  {r.error}")
    else:
        # SHA-free summary of failure causes (G0-S): reason -> count
        reasons: dict[str, int] = {}
        for r in bad:
            key = r.error.split(":", 1)[0] if r.error else "unknown"
            reasons[key] = reasons.get(key, 0) + 1
        for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"FAIL x{n}: {reason}")

    print(f"\nresolved {len(ok)}/{len(results)} objects; failed {len(bad)}")
    print(f"total budget: {total} bytes ({total_mb:.1f} MB)")
    if ns.budget_mb is not None and total_mb > ns.budget_mb:
        print(f"WARNING: total {total_mb:.1f} MB exceeds requested budget {ns.budget_mb:.1f} MB",
              file=sys.stderr)

    if ns.out_csv:
        out = assert_isolated_output(ns.out_csv, kind="preflight CSV")
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["sha256", "ok", "content_length", "etag", "error"])
            for r in results:
                w.writerow([r.sha256, int(r.ok), r.content_length, r.etag, r.error])
        print(f"preflight csv: {out}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
