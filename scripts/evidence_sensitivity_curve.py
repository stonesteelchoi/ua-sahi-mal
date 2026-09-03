"""How much of a sample has to carry a family's signal before occlusion can see it.

The synthetic control set failed D1 outright -- Byte-IoU 0.00 on positives, the
same 0.00 on their matched negatives -- and the reason is not a bug in the
search.  A 16 KB graft is 0.7% of a 2.35 MB sample; masking it moves the donor
family's log-likelihood by less than the masking artifact does, and the positive
and its negative move together (-3.635 against -3.684).  The protocol was being
asked to find a signal that is not there.

This script measures where the signal starts.  It builds samples whose family
evidence is confined to a window of known size by construction -- keep a window
of family Y's bytes, overwrite everything else with family X's -- and sweeps the
window fraction.  Reported per fraction:

* whether the classifier predicts Y at all (if it does not, there is no judgment
  to explain, and nothing for the search to find)
* the NLL rise when the preserved window is masked
* the same for a random window of identical size, which is the control that
  separates "the evidence matters" from "masking matters"

The output is the detection floor of the whole protocol, and it belongs in the
paper whichever way it comes out.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ua_sahi_mal.evidence import (  # noqa: E402
    classifiers,
    corpus,
    metrics,
    occlusion,
    training,
)

DEFAULT_FRACTIONS = (0.05, 0.10, 0.20, 0.30, 0.50, 0.70)
BLOCK = 4096


def build_preserved(host: np.ndarray, filler: np.ndarray, fraction: float) -> tuple[np.ndarray, tuple[int, int]]:
    """Keep a centred window of ``host``; overwrite the rest with ``filler`` bytes."""
    window = max(BLOCK, int(host.size * fraction) // BLOCK * BLOCK)
    window = min(window, host.size // BLOCK * BLOCK)
    start = ((host.size - window) // 2) // BLOCK * BLOCK
    if filler.size < host.size:
        filler = np.resize(filler, host.size)
    data = filler[: host.size].copy()
    data[start : start + window] = host[start : start + window]
    return data, (start, start + window)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--rasters", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--hosts", type=int, default=12)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    entries, _ = corpus.read_manifest(args.manifest)
    store = training.SampleStore(args.rasters)
    model = classifiers.TiledClassifier.load(Path(args.models) / "classifier_tiled.pt")
    rng = np.random.default_rng(args.seed)

    test = sorted(corpus.split_entries(entries, corpus.SPLIT_TEST), key=lambda e: e.sample_id)
    train = sorted(corpus.split_entries(entries, corpus.SPLIT_TRAIN), key=lambda e: e.sample_id)
    hosts = [entry for entry in test if 150_000 < entry.byte_count < 3_000_000][: args.hosts]
    fillers: dict[int, corpus.CorpusEntry] = {}
    for entry in train:
        fillers.setdefault(entry.label, entry)

    started = time.time()
    rows: list[dict] = []
    for host in hosts:
        host_bytes = store.get(host)
        filler_label = next(label for label in sorted(fillers) if label != host.label)
        filler_bytes = store.get(fillers[filler_label])

        for fraction in DEFAULT_FRACTIONS:
            data, window = build_preserved(host_bytes, filler_bytes, fraction)
            plan = occlusion.make_fill_plan(occlusion.PRIMARY_FILL, data)
            baseline = model.log_probabilities(data)

            masked = occlusion.occlude(data, [window], plan, rng)
            control_window = occlusion.random_control_ranges(np.asarray([window]), data.size, rng)
            control = occlusion.occlude(data, control_window, plan, rng)

            evidence_nll = float(-model.log_probabilities(masked)[host.label])
            control_nll = float(-model.log_probabilities(control)[host.label])
            base_nll = float(-baseline[host.label])

            rows.append(
                {
                    "host": host.sample_id,
                    "family": host.label,
                    "filler_family": filler_label,
                    "byte_count": int(data.size),
                    "fraction": fraction,
                    "window_bytes": int(window[1] - window[0]),
                    "predicted": int(np.argmax(baseline)),
                    "predicts_family": bool(int(np.argmax(baseline)) == host.label),
                    "baseline_nll": base_nll,
                    "delta_evidence": evidence_nll - base_nll,
                    "delta_control": control_nll - base_nll,
                }
            )
        print(f"{host.sample_id[:8]} family {host.label} done", flush=True)

    summary = []
    for fraction in DEFAULT_FRACTIONS:
        subset = [row for row in rows if row["fraction"] == fraction]
        recognized = [row for row in subset if row["predicts_family"]]
        entry = {
            "fraction": fraction,
            "n": len(subset),
            "recognized": len(recognized),
            "mean_delta_evidence": float(np.mean([row["delta_evidence"] for row in subset])),
            "mean_delta_control": float(np.mean([row["delta_control"] for row in subset])),
        }
        if len(subset) >= 2:
            paired = metrics.summarize_paired(
                [row["delta_evidence"] for row in subset],
                [row["delta_control"] for row in subset],
                label=f"preserve {fraction:.0%}: evidence window vs random window",
                seed=args.seed,
            )
            entry["paired"] = paired
        if recognized:
            entry["mean_delta_evidence_recognized"] = float(
                np.mean([row["delta_evidence"] for row in recognized])
            )
        summary.append(entry)

    document = {
        "format": "evidence-sensitivity-1",
        "question": (
            "What fraction of a sample must carry a family's signal before masking "
            "that region moves the classifier more than masking a random region of "
            "the same size?"
        ),
        "hosts": len(hosts),
        "block_bytes": BLOCK,
        "seconds": round(time.time() - started, 1),
        "summary": summary,
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'frac':>6} {'n':>3} {'recog':>5} {'d_evidence':>11} {'d_control':>10} {'CI excludes 0':>14}")
    for entry in summary:
        interval = entry.get("paired", {}).get("difference", {})
        print(
            f"{entry['fraction']:>6.2f} {entry['n']:>3} {entry['recognized']:>5} "
            f"{entry['mean_delta_evidence']:>11.3f} {entry['mean_delta_control']:>10.3f} "
            f"{str(interval.get('excludes_zero')):>14}"
        )
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
