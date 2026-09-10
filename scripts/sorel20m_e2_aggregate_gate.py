"""E2 aggregate report + pre-registered gate, behind the G0-S publication gate.

Reads ``<...>_e2_results.json`` (isolated, SHA-carrying) and emits an aggregate
report with NO SHA and NO sample-linked offset: per-stratum coverage means, paired
bootstrap comparisons with Holm-Bonferroni correction, and the gate verdict.

* default (v1/v2): byte-scope heuristics (entropy, entropy_boundary) vs random / front_first.
* ``--learned`` (E2_prereg_v3): learned selectors vs front_first / entropy_boundary /
  random / position_only; the gate is evaluated for ``--best-learned`` — the selector
  chosen on the VALIDATION split (never on test).

``--run-record`` carries the run's prereg_version into the report (otherwise the
label defaults to "unknown"). Without ``--publication-authorization`` the report is
INTERNAL_ONLY. The output is verified SHA-free before it is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.e2_report import LEARNED_SELECTORS, assert_no_sample_link, build_report  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", required=True, help="<...>_e2_results.json from the E2 run")
    p.add_argument("--out", required=True, help="isolated output JSON for the aggregate report")
    p.add_argument("--run-record", default=None, help="<...>_e2_run_record.json (for prereg_version)")
    p.add_argument("--prereg-version", default=None, help="override the prereg label")
    p.add_argument("--learned", default=None,
                   help="E2 v3: comma-separated learned selectors, or 'default' for "
                        + ",".join(LEARNED_SELECTORS))
    p.add_argument("--best-learned", default=None, help="E2 v3: selector chosen on validation (gate target)")
    p.add_argument("--primary-budget", type=float, default=0.10)
    p.add_argument("--iterations", type=int, default=1000)
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--publication-authorization", default=None,
                   help="operator-attested written-clarification reference (unset = INTERNAL_ONLY)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    results = json.loads(Path(ns.results).read_text(encoding="utf-8"))

    prereg = ns.prereg_version
    if prereg is None and ns.run_record:
        prereg = json.loads(Path(ns.run_record).read_text(encoding="utf-8")).get("prereg_version")
    prereg = prereg or "unknown"

    learned = None
    if ns.learned:
        learned = LEARNED_SELECTORS if ns.learned == "default" else tuple(x.strip() for x in ns.learned.split(","))

    report = build_report(
        results, prereg_version=prereg, primary_budget=ns.primary_budget, iterations=ns.iterations,
        seed=ns.seed, authorization_ref=ns.publication_authorization, learned=learned, best_learned=ns.best_learned,
    )
    assert_no_sample_link(report)  # belt and braces

    out = assert_isolated_output(ns.out, kind="e2 aggregate report")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\naggregate report: {out}")
    gate = report["gate"]
    print(f"GATE ({prereg}): {json.dumps(gate, ensure_ascii=False)}")
    if report["publication_scope"] != "authorized":
        print("NOTE (G0-S): INTERNAL ONLY — aggregate publication needs written §2(c) clarification.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
