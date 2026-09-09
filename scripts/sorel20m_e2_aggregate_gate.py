"""E2 aggregate report + pre-registered gate, behind the G0-S publication gate.

Reads ``<...>_e2_results.json`` (isolated, SHA-carrying) and emits an aggregate
report with NO SHA and NO sample-linked offset: per-stratum coverage means, paired
bootstrap comparisons of the byte-scope selectors vs the naive baselines with
Holm-Bonferroni correction, and the gate verdict. Without
``--publication-authorization`` the report is INTERNAL_ONLY (Terms §2(c) pending).
The output is verified SHA-free before it is written. Runs on the operator machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.e2_report import assert_no_sample_link, build_report  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", required=True, help="<...>_e2_results.json from the E2 run")
    p.add_argument("--out", required=True, help="isolated output JSON for the aggregate report")
    p.add_argument("--primary-budget", type=float, default=0.10)
    p.add_argument("--iterations", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--publication-authorization", default=None,
                   help="operator-attested written-clarification reference (unset = INTERNAL_ONLY)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    results = json.loads(Path(ns.results).read_text(encoding="utf-8"))
    report = build_report(
        results, primary_budget=ns.primary_budget, iterations=ns.iterations, seed=ns.seed,
        authorization_ref=ns.publication_authorization,
    )
    assert_no_sample_link(report)  # belt and braces

    out = assert_isolated_output(ns.out, kind="e2 aggregate report")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\naggregate report: {out}")
    gate = report["gate"]
    print(f"GATE pass={gate['gate_pass']} "
          f"(both_strata={gate['both_strata_pass']}, overlay>front={gate['overlay_dominant_beats_front_first']})")
    if report["publication_scope"] != "authorized":
        print("NOTE (G0-S): INTERNAL ONLY — aggregate publication needs written §2(c) clarification.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
