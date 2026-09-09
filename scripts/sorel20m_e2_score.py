"""E2 v3 scoring: per-tile learned-selector scores for the TEST split (E2_prereg_v3).

Loads the trained checkpoints, fits the strengthened positional baseline
(``position_only``) from a TRAIN-split E2 results JSON (silver density vs
normalised offset — never from test), and writes ``{sha: {selector: [scores]}}``
to an isolated JSON that ``sorel20m_e2_run.py --learned-scores`` consumes.

Static-only, in memory. Console output is SHA-free. Runs on the operator machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.sorel.e2_dataset import SorelTileStore, shas_for_split  # noqa: E402
from ua_sahi_mal.sorel.e2_learned import fit_positional_prior_from_results, score_file  # noqa: E402
from ua_sahi_mal.sorel.e2_models import load_checkpoint, resolve_device  # noqa: E402
from ua_sahi_mal.sorel.paths import assert_isolated_output  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, help="selection_v2_manifest_effective.csv (isolated)")
    p.add_argument("--compressed-dir", required=True)
    p.add_argument("--out", required=True, help="isolated JSON: {sha: {selector: scores}}")
    p.add_argument("--static-only", action="store_true", help="affirm static-only isolated env (required)")
    p.add_argument("--split", default="test", choices=["train", "validation", "test"])
    p.add_argument("--meanmax-ckpt", default=None, help="e2v3_meanmax.pt (attr_tile_conf / attr_occlusion)")
    p.add_argument("--attention-ckpt", default=None, help="e2v3_attention.pt (mil_attention)")
    p.add_argument("--train-results", default=None,
                   help="E2 results JSON of the TRAIN split (silver) to fit position_only; never test")
    p.add_argument("--prior-bins", type=int, default=20)
    p.add_argument("--device", default="auto")
    p.add_argument("--seed", type=int, default=20260909)
    p.add_argument("--cache-gb", type=float, default=4.0)
    p.add_argument("--limit", type=int, default=0, help="smoke: score only the first N files")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(argv)
    if not ns.static_only:
        print("error: refusing to decompress without --static-only", file=sys.stderr)
        return 2
    if not (ns.meanmax_ckpt or ns.attention_ckpt or ns.train_results):
        print("error: nothing to score — pass a checkpoint and/or --train-results", file=sys.stderr)
        return 2

    device = resolve_device(ns.device) if (ns.meanmax_ckpt or ns.attention_ckpt) else None
    meanmax = load_checkpoint(ns.meanmax_ckpt, device=device)[0] if ns.meanmax_ckpt else None
    attention = load_checkpoint(ns.attention_ckpt, device=device)[0] if ns.attention_ckpt else None
    prior = None
    if ns.train_results:
        train_results = json.loads(Path(ns.train_results).read_text(encoding="utf-8"))
        prior = fit_positional_prior_from_results(train_results, bins=ns.prior_bins)
        print(f"position_only prior: fitted on {prior.n_files} train files with silver, {prior.bins} bins")

    shas = shas_for_split(ns.manifest, ns.split)
    if ns.limit:
        shas = shas[: ns.limit]
    store = SorelTileStore(ns.compressed_dir, static_only=True, cache_bytes=int(ns.cache_gb * (1 << 30)))

    scores: dict[str, dict[str, list[float]]] = {}
    failures: dict[str, int] = {}
    for sha in shas:
        try:
            bag = store.get(sha)
            scores[sha] = score_file(bag, meanmax_model=meanmax, attention_model=attention, prior=prior,
                                     device=device, seed=ns.seed)
        except Exception as exc:  # noqa: BLE001 - record, never crash a 1000-file run
            key = type(exc).__name__
            failures[key] = failures.get(key, 0) + 1

    out = assert_isolated_output(ns.out, kind="learned scores")
    payload = {"prereg_version": "E2_prereg_v3", "split": ns.split, "seed": ns.seed,
               "selectors": sorted({k for v in scores.values() for k in v}),
               "position_prior": prior.to_dict() if prior else None,
               "scores": scores}
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    print(f"scored {len(scores)}/{len(shas)} {ns.split} files; selectors={payload['selectors']}")
    if failures:
        print("failures:", failures)
    print(f"scores: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
