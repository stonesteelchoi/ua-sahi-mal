"""Static-only analysis stage for acquired SOREL artefacts.

Decompresses each ``<sha>.zlib`` IN MEMORY (never to disk), verifies the disarming
is intact (Machine/Subsystem still zero; refuses armed files, never re-arms), hashes
the decompressed disarmed binary, and — when the peatlas package is available — runs
the coordinate-integrity / coverage mapping plus an optional pefile cross-check.

Writes only derived, non-executable results to an isolated path:
  * updates the private manifest (disarmed_local_sha256, statuses, exclusions)
  * writes ``<out_prefix>_static_results.json`` (internal; per-sha results)

Requires --static-only (affirming an approved static-only isolated environment).
Runs on the operator machine (cau), never in the cloud session.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.manifest import read_manifest, write_manifest  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402
from ua_sahi_mal.sorel.static_stage import analyze_dir  # noqa: E402


def _read_shalist(path: str) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--compressed-dir", required=True, help="isolated dir with <sha>.zlib files")
    p.add_argument("--sha-list", required=True, help="selected_sha256.txt")
    p.add_argument("--manifest", help="private manifest CSV to update in place (optional)")
    p.add_argument("--out-prefix", required=True, help="isolated output prefix for results JSON")
    p.add_argument("--static-only", action="store_true",
                   help="affirm an approved static-only isolated environment (required)")
    p.add_argument("--no-pefile", action="store_true", help="skip the pefile cross-check")
    p.add_argument("--no-peatlas", action="store_true", help="skip the peatlas coverage mapping")
    p.add_argument("--verbose", action="store_true",
                   help="print one line per SHA prefix (default: SHA-free summary; details in results JSON)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.static_only:
        print("error: refusing to decompress without --static-only", file=sys.stderr)
        return 2

    shas = _read_shalist(ns.sha_list)
    results = analyze_dir(ns.compressed_dir, shas, static_only=True,
                          run_peatlas=not ns.no_peatlas, run_pefile=not ns.no_pefile)

    results_path = assert_isolated_output(f"{ns.out_prefix}_static_results.json", kind="results")
    results_path.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")

    if ns.manifest:
        by_sha = {r.sorel_original_sha256: r for r in results}
        rows = read_manifest(ns.manifest)
        for row in rows:
            r = by_sha.get(row.sorel_original_sha256)
            if r is None:
                continue
            row.disarmed_local_sha256 = r.disarmed_local_sha256
            row.zlib_status = "ok" if r.decompressed_size > 0 else (r.exclusion_reason or "error")
            row.peatlas_status = r.peatlas_status
            row.independent_parser_status = r.independent_parser_status
            if r.exclusion_reason and not row.exclusion_reason:
                row.exclusion_reason = r.exclusion_reason
        write_manifest(ns.manifest, rows)

    ok = sum(1 for r in results if r.disarm_ok and r.peatlas_status in ("ok", "skipped:peatlas_unavailable"))
    armed = sum(1 for r in results if r.exclusion_reason.startswith("not_disarmed"))
    if ns.verbose:
        for r in results:
            cov = f"{r.coverage_ok_fraction:.4f}" if r.coverage_ok_fraction is not None else "n/a"
            flag = r.exclusion_reason or r.peatlas_status or "ok"
            print(f"{r.sorel_original_sha256[:12]}...  disarm={int(r.disarm_ok)}  cov={cov}  {flag}")
    else:
        flags: dict[str, int] = {}
        for r in results:
            key = (r.exclusion_reason or r.peatlas_status or "ok").split(":", 1)[0]
            flags[key] = flags.get(key, 0) + 1
        for key, n in sorted(flags.items(), key=lambda kv: -kv[1]):
            print(f"{key:28s} x{n}")
    print(f"\nprocessed {len(results)}; disarm-intact analyses {ok}; armed/refused {armed}")
    print(f"results: {results_path}")
    if armed:
        print("WARNING: armed artefacts were refused and flagged; they were NOT re-armed or analyzed.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
