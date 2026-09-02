from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an evidence-backed overview figure from aggregated MaleVis runs."
    )
    parser.add_argument("--aggregate", type=Path, required=True)
    parser.add_argument("--isolated-timing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _group_map(aggregate: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    return {
        (int(group["image_size"]), str(group["mode"])): group
        for group in aggregate["groups"]
    }


def _per_class_means(
    aggregate: dict[str, Any], *, mode: str
) -> tuple[list[str], dict[int, dict[str, float]]]:
    values: dict[int, dict[str, list[float]]] = {}
    for run_dir in aggregate["source_runs"]:
        summary = _load_json(Path(run_dir) / "summary.json")
        image_size = int(summary["image_size"])
        for row in summary["evaluation"][mode]["per_class"]:
            values.setdefault(image_size, {}).setdefault(row["class_name"], []).append(
                float(row["f1"])
            )
    means = {
        image_size: {
            class_name: sum(class_values) / len(class_values)
            for class_name, class_values in class_map.items()
        }
        for image_size, class_map in values.items()
    }
    class_names = sorted(set.intersection(*(set(item) for item in means.values())))
    return class_names, means


def create_figure(aggregate_path: Path, isolated_timing_path: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    aggregate = _load_json(aggregate_path)
    if aggregate.get("schema") != "ua-sahi-mal-malevis-aggregate-v1":
        raise ValueError(f"unexpected aggregate schema: {aggregate.get('schema')!r}")
    isolated_timing = _load_json(isolated_timing_path)
    if isolated_timing.get("schema") != "ua-sahi-mal-malevis-isolated-timing-v1":
        raise ValueError(f"unexpected timing schema: {isolated_timing.get('schema')!r}")
    timing_map = {
        (int(run["image_size"]), mode): values
        for run in isolated_timing["runs"]
        for mode, values in run["modes"].items()
    }

    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update(
        {
            "font.family": ["Malgun Gothic", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
        }
    )
    colors = {"deterministic": "#2E74B5", "mc_dropout": "#E69F00"}
    labels = {"deterministic": "Deterministic", "mc_dropout": "MC dropout (T=5)"}
    group_map = _group_map(aggregate)
    resolutions = (224, 300)
    modes = ("deterministic", "mc_dropout")

    fig, axes = plt.subplots(2, 2, figsize=(10.6, 6.4), constrained_layout=True)

    ax = axes[0, 0]
    x = np.arange(len(resolutions))
    width = 0.18
    offsets = (-1.5, -0.5, 0.5, 1.5)
    series = []
    for mode in modes:
        for metric, short_label, hatch in (
            ("accuracy", "Acc.", ""),
            ("macro_f1", "Macro-F1", "//"),
        ):
            series.append((mode, metric, short_label, hatch))
    for offset, (mode, metric, short_label, hatch) in zip(offsets, series, strict=True):
        means = [group_map[(size, mode)]["metrics"][metric]["mean"] for size in resolutions]
        stds = [
            group_map[(size, mode)]["metrics"][metric]["standard_deviation"] or 0.0
            for size in resolutions
        ]
        ax.bar(
            x + offset * width,
            means,
            width,
            yerr=stds,
            capsize=3,
            color=colors[mode],
            alpha=0.88,
            hatch=hatch,
            edgecolor="white" if not hatch else "#23364D",
            linewidth=0.6,
            label=f"{labels[mode]} · {short_label}",
        )
    ax.set_title("(a) Final-test performance (mean ± seed SD)")
    ax.set_xticks(x, [f"{size}×{size}" for size in resolutions])
    ax.set_ylim(0.70, 0.90)
    ax.set_ylabel("Score")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=7, ncol=2, loc="lower right")

    ax = axes[0, 1]
    width = 0.32
    for index, mode in enumerate(modes):
        means = [
            group_map[(size, mode)]["metrics"]["expected_calibration_error"]["mean"]
            for size in resolutions
        ]
        stds = [
            group_map[(size, mode)]["metrics"]["expected_calibration_error"][
                "standard_deviation"
            ]
            or 0.0
            for size in resolutions
        ]
        ax.bar(
            x + (index - 0.5) * width,
            means,
            width,
            yerr=stds,
            capsize=3,
            color=colors[mode],
            label=labels[mode],
        )
    ax.set_title("(b) Calibration error (lower is better)")
    ax.set_xticks(x, [f"{size}×{size}" for size in resolutions])
    ax.set_ylabel("ECE")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    class_names, class_means = _per_class_means(aggregate, mode="mc_dropout")
    ranked = sorted(
        class_names,
        key=lambda name: sum(class_means[size][name] for size in resolutions) / len(resolutions),
    )[:8]
    y = np.arange(len(ranked))
    for index, size in enumerate(resolutions):
        ax.barh(
            y + (index - 0.5) * 0.34,
            [class_means[size][name] for name in ranked],
            0.34,
            color=("#56B4E9", "#009E73")[index],
            label=f"{size}×{size}",
        )
    ax.set_title("(c) Lowest class-wise MC F1 (3-seed mean)")
    ax.set_yticks(y, ranked)
    ax.invert_yaxis()
    ax.set_xlim(0.0, 1.0)
    ax.set_xlabel("F1")
    ax.grid(axis="x", alpha=0.22)
    ax.legend(fontsize=8, loc="lower right")

    ax = axes[1, 1]
    timing_values = []
    timing_labels = []
    timing_colors = []
    for size in resolutions:
        for mode in modes:
            timing_values.append(float(timing_map[(size, mode)]["latency_p95_ms_per_image"]))
            timing_labels.append(f"{size}\n{('Det.' if mode == 'deterministic' else 'MC×5')}")
            timing_colors.append(colors[mode])
    positions = np.arange(len(timing_values))
    ax.bar(positions, timing_values, color=timing_colors)
    ax.set_title("(d) Batched model-forward p95 (representative seed)")
    ax.set_xticks(positions, timing_labels)
    ax.set_ylabel("ms / image")
    ax.grid(axis="y", alpha=0.22)
    for position, value in zip(positions, timing_values, strict=True):
        ax.text(position, value, f"{value:.1f}", ha="center", va="bottom", fontsize=8)

    fig.suptitle(
        "MaleVis DECODE-transfer: performance, calibration, class weakness, and compute cost",
        fontsize=12,
        fontweight="bold",
        color="#17365D",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    create_figure(args.aggregate, args.isolated_timing, args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
