"""E2 silver-evidence retrieval run (E2_prereg_v1).

For each acquired ``<sha>.zlib`` (isolated), decompresses IN MEMORY (static-only,
never to disk), verifies the disarming, derives the overlay stratum, extracts
silver evidence (embedded-artifact byte scope + optional capa function scope),
scores every pre-registered selector at every budget, and scrubs the buffer.

Writes to an isolated path only:
  * ``<out_prefix>_e2_results.json``  — per-sha results (INTERNAL; carries SHA + offsets)
  * ``<out_prefix>_e2_run_record.json`` — provenance (prereg version, config SHA, seed)

Console output is SHA-free (``--verbose`` prints case-NN lines, still SHA-free).
capa is opt-in with ``--enable-capa`` (validate on a few files first); the run
degrades to embedded-artifact silver and records the reason if capa is
unavailable. Runs on the operator machine (cau), never in the cloud session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml  # noqa: E402

from ua_sahi_mal.sorel.e2_pipeline import process_dir, result_to_dict  # noqa: E402
from ua_sahi_mal.sorel.e2_tiles import BUDGETS, PRIMARY_BUDGET, TILE_BYTES  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402

_DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "sorel20m_e2_v2.yaml"


def _read_shalist(path: str) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--compressed-dir", required=True, help="isolated dir with <sha>.zlib files")
    p.add_argument("--sha-list", default=None, help="effective_sha256.txt (one SHA per line)")
    p.add_argument("--manifest", default=None, help="alternative to --sha-list: effective manifest CSV ...")
    p.add_argument("--split", default=None, choices=["train", "validation", "test"],
                   help="... with the official split to take from it (E2 v3)")
    p.add_argument("--learned-scores", default=None,
                   help="E2 v3: JSON from sorel20m_e2_score.py; adds learned selectors to the evaluation")
    p.add_argument("--out-prefix", required=True, help="isolated output prefix")
    p.add_argument("--static-only", action="store_true", help="affirm static-only isolated env (required)")
    p.add_argument("--config", default=str(_DEFAULT_CONFIG), help="frozen E2 config (default: E2_prereg_v2)")
    p.add_argument("--enable-yara", action="store_true",
                   help="enable YARA byte-scope silver (in-memory scan; AV-safe)")
    p.add_argument("--yara-rules", default=None, help="path to a YARA rules dir/file (or compiled .yac)")
    p.add_argument("--enable-capa", action="store_true",
                   help="enable capa function-scope silver. REFUSED without --capa-work-dir; capa writes the "
                        "sample to disk (vivisect) -> run ONLY in an isolated env WITHOUT resident AV, never on cau")
    p.add_argument("--capa-rules", default=None, help="path to the capa rules directory")
    p.add_argument("--capa-work-dir", default=None,
                   help="isolated dir capa may write its temp workspace to (required for --enable-capa)")
    p.add_argument("--capa-version", default="", help="capa version string to record (capa.__version__)")
    p.add_argument("--verbose", action="store_true", help="print SHA-free case-NN lines")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.static_only:
        print("error: refusing to decompress without --static-only", file=sys.stderr)
        return 2

    cfg_bytes = Path(ns.config).read_bytes()
    cfg = yaml.safe_load(cfg_bytes)
    cfg_sha = hashlib.sha256(cfg_bytes).hexdigest()
    # drift guard: the code constants must match the frozen prereg config
    if int(cfg["geometry"]["tile_bytes"]) != TILE_BYTES:
        print(f"error: config tile_bytes {cfg['geometry']['tile_bytes']} != code {TILE_BYTES}", file=sys.stderr)
        return 2
    if [round(float(b), 4) for b in cfg["budgets"]] != [round(b, 4) for b in BUDGETS]:
        print(f"error: config budgets {cfg['budgets']} != code {BUDGETS}", file=sys.stderr)
        return 2
    seed = int(cfg["random_seed"])
    capa_timeout = int(((cfg.get("silver") or {}).get("capa") or {}).get("timeout_seconds", 300))

    if ns.enable_capa:
        if not ns.capa_work_dir:
            print("error: --enable-capa requires --capa-work-dir (an isolated dir). capa writes the "
                  "decompressed sample to disk via vivisect; run ONLY in an isolated environment WITHOUT "
                  "resident AV — never on cau.", file=sys.stderr)
            return 2
        assert_isolated_output(ns.capa_work_dir, kind="capa work dir")  # refuse repo/sync paths
        print("WARNING: capa writes the (disarmed) sample to disk under the work dir to disassemble it. "
              "Run this ONLY in a dedicated isolated environment WITHOUT resident AV.", file=sys.stderr)

    if ns.sha_list:
        shas = _read_shalist(ns.sha_list)
    elif ns.manifest and ns.split:
        from ua_sahi_mal.sorel.e2_dataset import shas_for_split

        shas = shas_for_split(ns.manifest, ns.split)
        print(f"{len(shas)} effective SHAs in split {ns.split!r}")
    else:
        print("error: pass --sha-list, or --manifest together with --split", file=sys.stderr)
        return 2

    extra_scores_by_sha = None
    if ns.learned_scores:
        payload = json.loads(Path(ns.learned_scores).read_text(encoding="utf-8"))
        extra_scores_by_sha = payload.get("scores") or {}
        print(f"learned selectors: {payload.get('selectors')} for {len(extra_scores_by_sha)} files "
              f"(prereg {payload.get('prereg_version')})")

    results = process_dir(
        ns.compressed_dir, shas, static_only=True,
        enable_capa=ns.enable_capa, enable_yara=ns.enable_yara,
        capa_timeout=capa_timeout, capa_rules_path=ns.capa_rules, capa_work_dir=ns.capa_work_dir,
        capa_version=ns.capa_version, yara_rules_path=ns.yara_rules, seed=seed,
        extra_scores_by_sha=extra_scores_by_sha,
    )

    results_path = assert_isolated_output(f"{ns.out_prefix}_e2_results.json", kind="e2 results")
    results_path.write_text(
        json.dumps([result_to_dict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")

    record = {
        "prereg_version": cfg.get("version", "E2_prereg_v1"),
        "config_sha256": cfg_sha,
        "utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "enable_yara": ns.enable_yara,
        "yara_rules": ns.yara_rules,
        "enable_capa": ns.enable_capa,
        "capa_timeout_seconds": capa_timeout,
        "capa_version": ns.capa_version,
        "capa_rules": ns.capa_rules,
        "capa_work_dir": ns.capa_work_dir,
        "split": ns.split,
        "learned_scores": ns.learned_scores,
        "n_shas": len(shas),
        "tile_bytes": TILE_BYTES,
        "primary_budget": PRIMARY_BUDGET,
    }
    record_path = assert_isolated_output(f"{ns.out_prefix}_e2_run_record.json", kind="e2 run record")
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_summary(results, verbose=ns.verbose)
    print(f"\nresults: {results_path}")
    print(f"run record: {record_path}")
    print(f"config SHA256: {cfg_sha[:16]}... (prereg {record['prereg_version']})")
    return 0


def _print_summary(results, *, verbose: bool) -> None:
    ok = [r for r in results if r.ok]
    excluded = [r for r in results if not r.ok]
    print(f"processed {len(results)}; ok {len(ok)}; excluded {len(excluded)}")

    reasons: dict[str, int] = {}
    for r in excluded:
        key = (r.exclusion_reason or "unknown").split(":", 1)[0]
        reasons[key] = reasons.get(key, 0) + 1
    for key, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  excluded {key:24s} x{n}")

    for source in ("yara_status", "capa_status"):
        counts: dict[str, int] = {}
        for r in ok:
            key = str(r.silver.get(source, "?")).split(":", 1)[0]
            counts[key] = counts.get(key, 0) + 1
        print(f"  {source.replace('_status', '')} status:", {k: v for k, v in sorted(counts.items())})

    budget_key = f"{PRIMARY_BUDGET:.2f}"
    learned = sorted({n for r in ok for n in r.evaluation.get("selectors", {})
                      if n not in ("random", "uniform", "front_first", "back_first", "entropy",
                                   "entropy_boundary", "oracle_silver")})
    preview_names = ("front_first", "entropy_boundary", "random", *learned)
    for stratum in ("overlay_dominant", "non_dominant"):
        files = [r for r in ok if r.stratum == stratum]
        with_silver = [r for r in files if r.evaluation.get("has_silver")]
        preview = {}
        for name in preview_names:
            vals = [r.evaluation["selectors"][name][budget_key]["coverage"] for r in with_silver
                    if budget_key in (r.evaluation["selectors"].get(name) or {})]
            preview[name] = round(sum(vals) / len(vals), 3) if vals else None
        print(f"  {stratum:16s} n={len(files):3d} with_silver={len(with_silver):3d}  "
              f"coverage@{budget_key} {preview}")

    if verbose:
        for i, r in enumerate(results, start=1):
            print(r.public_summary(f"case-{i:03d}"))


if __name__ == "__main__":
    raise SystemExit(main())
