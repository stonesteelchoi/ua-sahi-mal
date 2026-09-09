"""Build the parser disagreement ledger for a static-stage run (amendment §7 E1).

Reads ``<prefix>_static_results.json``, selects artefacts whose
``independent_parser_status`` is not "ok", rebuilds both parser views in memory
(static-only; no decompressed bytes are written) and classifies each disagreement.

Outputs (isolated path):
  <out_prefix>_disagreement_ledger.json   full entries (private: carries SHAs + header fields)
Console: SHA-free case lines + category counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.ledger import build_ledger_entry, entry_to_dict  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_binary_dir, assert_isolated_output  # noqa: E402
from ua_sahi_mal.sorel.record import build_run_record, write_run_record  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", required=True, help="<prefix>_static_results.json")
    p.add_argument("--compressed-dir", required=True, help="isolated dir with <sha>.zlib files")
    p.add_argument("--out-prefix", required=True, help="isolated output prefix")
    p.add_argument("--static-only", action="store_true",
                   help="affirm an approved static-only isolated environment (required)")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.static_only:
        print("error: refusing to decompress without --static-only", file=sys.stderr)
        return 2
    root = assert_isolated_binary_dir(ns.compressed_dir)
    results = json.loads(Path(ns.results).read_text(encoding="utf-8"))
    disagreeing = [r for r in results
                   if r.get("independent_parser_status") and r["independent_parser_status"] != "ok"
                   and not str(r["independent_parser_status"]).startswith("skipped")]

    entries = []
    for i, r in enumerate(disagreeing, 1):
        sha = r["sorel_original_sha256"]
        path = root / f"{sha}.zlib"
        case_id = f"case-{i:02d}"
        if not path.exists():
            print(f"{case_id}: missing:zlib_not_found")
            continue
        entry = build_ledger_entry(path.read_bytes(), sha256=sha, case_id=case_id,
                                   strict_status=r["independent_parser_status"], static_only=True)
        entries.append(entry)
        print(entry.public_summary())

    out = assert_isolated_output(f"{ns.out_prefix}_disagreement_ledger.json", kind="ledger")
    out.write_text(json.dumps([entry_to_dict(e) for e in entries], ensure_ascii=False, indent=2),
                   encoding="utf-8")

    cats: dict[str, int] = {}
    for e in entries:
        cats[e.category] = cats.get(e.category, 0) + 1
    raw_agree = sum(1 for e in entries if e.raw_agreement)
    print(f"\ndisagreements: {len(entries)}  categories: {cats}  raw_agreement_true: {raw_agree}/{len(entries)}")
    print(f"ledger: {out}")

    record = build_run_record("sorel_disagreement_ledger", repo_root=Path(__file__).resolve().parents[1],
                              n_disagreements=len(entries), categories=cats,
                              raw_agreement_true=raw_agree, outputs={"ledger": str(out)},
                              publication_status="INTERNAL_ONLY (G0-S)")
    write_run_record(f"{ns.out_prefix}_disagreement_ledger_record.json", record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
