"""Aggregate-only reporting behind the G0-S publication gate.

Reads the internal static-stage results and emits an aggregate report containing
NO SHA and NO sample-linked interval. Without --publication-authorization the
report is stamped INTERNAL_ONLY with the Terms §2(c) pending note. The output is
verified SHA-free before it is written.

Runs on the operator machine (cau).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.aggregate import assert_no_sample_link, build_report  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402
from ua_sahi_mal.sorel.static_stage import StaticResult  # noqa: E402


def _load_results(path: str) -> list[StaticResult]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: list[StaticResult] = []
    for d in raw:
        out.append(StaticResult(
            sorel_original_sha256=d.get("sorel_original_sha256", ""),
            disarmed_local_sha256=d.get("disarmed_local_sha256", ""),
            decompressed_size=int(d.get("decompressed_size") or 0),
            disarm_ok=bool(d.get("disarm_ok")),
            peatlas_status=d.get("peatlas_status", ""),
            independent_parser_status=d.get("independent_parser_status", ""),
            coverage_ok_fraction=d.get("coverage_ok_fraction"),
            status_histogram=d.get("status_histogram") or {},
            is_pe32_plus=d.get("is_pe32_plus"),
            n_sections=d.get("n_sections"),
            overlay_bytes=d.get("overlay_bytes"),
            roundtrip_points=int(d.get("roundtrip_points") or 0),
            roundtrip_errors=int(d.get("roundtrip_errors") or 0),
            pixel_roundtrip_points=int(d.get("pixel_roundtrip_points") or 0),
            pixel_roundtrip_errors=int(d.get("pixel_roundtrip_errors") or 0),
            independent_raw_agreement=d.get("independent_raw_agreement"),
            exclusion_reason=d.get("exclusion_reason", ""),
        ))
    return out


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", required=True, help="<...>_static_results.json from the static stage")
    p.add_argument("--out", required=True, help="isolated output JSON for the aggregate report")
    p.add_argument("--publication-authorization", default=None,
                   help="operator-attested written-clarification reference (leave unset = INTERNAL_ONLY)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    results = _load_results(ns.results)
    report = build_report(results, authorization_ref=ns.publication_authorization)
    assert_no_sample_link(report)  # belt and braces
    if report.get("independent_considered", 0) == 0:
        print("WARNING: independent_considered == 0 — the pefile cross-check was skipped in the static "
              "stage (pefile likely missing from that interpreter). Re-run static_stage in the venv.",
              file=sys.stderr)

    out = assert_isolated_output(ns.out, kind="aggregate report")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\naggregate report: {out}")
    print(f"publication_status: {report['publication_status']}")
    if report["publication_status"] != "cleared":
        print("NOTE (G0-S): INTERNAL ONLY — aggregate publication needs written §2(c) clarification.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
