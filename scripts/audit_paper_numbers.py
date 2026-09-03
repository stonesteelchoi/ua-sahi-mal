#!/usr/bin/env python3
"""논문(output/paper)에 인쇄된 수치를 집계 산출물로부터 독립 재계산해 대조한다.

논문 본문·표를 고칠 때 근거 데이터와 어긋나면 여기서 실패한다.
즉 이 스크립트는 **논문에 대한 회귀 테스트**다.

데이터 출처는 다음 순서로 찾는다.
  1. runs/malevis/aggregate-20260829/  (원본. 이 머신에 실행 결과가 있을 때)
  2. docs/results/                      (커밋된 사본. CI·컨테이너용)

검증 범위 — 정직하게 밝힌다.
  검증한다   : 집계·대응비교·신뢰구간의 산술, 유의성 판정, 논문 표/본문 전사,
               사전 판정 기준의 재적용, t 계수 강건성
  검증 못한다: 개별 예측(predictions.*.csv)으로부터의 지표 계산 그 자체,
               학습 재현(GPU·데이터셋 필요)

사용:
    python scripts/audit_paper_numbers.py [--output runs/audit/paper.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

T_EXACT = 4.302652729911275   # t(0.975, df=2) 정확값
T_USED = 4.3030               # 집계 구현이 실제로 쓴 값(72개 CI 전부에서 역산, spread 5.6e-13)
N_SEEDS = 3
REPO = Path(__file__).resolve().parent.parent

SOURCES = [
    (REPO / "runs/malevis/aggregate-20260829", REPO / "runs/malevis/isolated-timing-20260829.json", "runs (원본)"),
    (REPO / "docs/results", REPO / "docs/results/isolated_timing.json", "docs/results (커밋된 사본)"),
]

# --- 논문에 인쇄된 값. 논문을 고치면 여기도 같이 고쳐야 한다. -----------------
TABLE2 = {
    "accuracy":                   {"224d": "0.769", "224m": "0.780", "300d": "0.751", "300m": "0.764"},
    "macro_f1":                   {"224d": "0.820", "224m": "0.821", "300d": "0.802", "300m": "0.808"},
    "weighted_f1":                {"224d": "0.774", "224m": "0.785", "300d": "0.752", "300m": "0.765"},
    "top5_accuracy":              {"224d": "0.883", "224m": "0.891", "300d": "0.884", "300m": "0.885"},
    "negative_log_likelihood":    {"224d": "0.892", "224m": "0.956", "300d": "0.961", "300m": "1.033"},
    "multiclass_brier":           {"224d": "0.304", "224m": "0.322", "300d": "0.337", "300m": "0.351"},
    "expected_calibration_error": {"224d": "0.048", "224m": "0.138", "300d": "0.049", "300m": "0.144"},
}
MCD = "mc_dropout_minus_deterministic"
ECE = "expected_calibration_error"
TABLE3 = [
    ("MC-Det. (224) 정확도", MCD, "image_size=224", "accuracy",
     "+0.011", "[−0.007, +0.029]", False),
    ("MC-Det. (224) Macro F1", MCD, "image_size=224", "macro_f1",
     "+0.001", "[−0.011, +0.013]", False),
    ("MC-Det. (224) ECE", MCD, "image_size=224", ECE,
     "+0.091", "[+0.071, +0.110]", True),
    ("MC-Det. (300) 정확도", MCD, "image_size=300", "accuracy",
     "+0.013", "[−0.015, +0.040]", False),
    ("MC-Det. (300) ECE", MCD, "image_size=300", ECE,
     "+0.096", "[+0.081, +0.111]", True),
    ("MC-Det. (300) NLL", MCD, "image_size=300", "negative_log_likelihood",
     "+0.072", "[+0.022, +0.122]", True),
    ("300-224 (Det.) Macro F1", "300_minus_224", "mode=deterministic", "macro_f1",
     "−0.017", "[−0.033, −0.002]", True),
    ("300-224 (Det.) Macro recall", "300_minus_224", "mode=deterministic", "macro_recall",
     "−0.012", "[−0.023, −0.000]", True),
]
TABLE4 = {  # 표 4 에 인쇄된 p50 / p95 / throughput
    ("224", "deterministic"): ("1.41", "1.80", "198.5"),
    ("224", "mc_dropout"):    ("7.03", "29.45", "84.9"),
    ("300", "deterministic"): ("2.52", "9.03", "127.4"),
    ("300", "mc_dropout"):    ("13.30", "22.73", "53.0"),
}
# 표 5: 실험 2 (BIG2015 경계 복원). shift -> {업샘플러: 인쇄된 MAE_start(bytes)}
TABLE5 = {
    0: {("G1", "nearest"): 0,    ("G1", "bilinear"): 0,   ("G1", "jbu"): 1609, ("G3", "jbu"): 0},
    1: {("G1", "nearest"): 512,  ("G1", "bilinear"): 171, ("G1", "jbu"): 2645, ("G3", "jbu"): 341},
    2: {("G1", "nearest"): 1024, ("G1", "bilinear"): 683, ("G1", "jbu"): 2816, ("G3", "jbu"): 1024},
    3: {("G1", "nearest"): 1536, ("G1", "bilinear"): 853, ("G1", "jbu"): 3157, ("G3", "jbu"): 1365},
    4: {("G1", "nearest"): 2048, ("G1", "bilinear"): 683, ("G1", "jbu"): 3328, ("G3", "jbu"): 1707},
}
TABLE5_MEANS = {("G1", "nearest"): 1280, ("G1", "bilinear"): 597,
                ("G1", "jbu"): 2987, ("G3", "jbu"): 1109}   # shift 1-4 평균
BODY_COHEN_D = {"byte_value": 0.96, "row_entropy": 8.50, "ratio": 8.8}
BODY_JBU_INFLATION = 5.0   # 본문 "바이트 값 가이드는 오차가 5.0배"

BODY_RATIOS = [("224 p50", "224", "latency_p50_ms_per_image", 5.0),
               ("224 p95", "224", "latency_p95_ms_per_image", 16.4),
               ("300 p50", "300", "latency_p50_ms_per_image", 5.3)]

DERIVE = {
    (MCD, "image_size=224"): ((224, "mc_dropout"), (224, "deterministic")),
    (MCD, "image_size=300"): ((300, "mc_dropout"), (300, "deterministic")),
    ("300_minus_224", "mode=deterministic"): ((300, "deterministic"), (224, "deterministic")),
    ("300_minus_224", "mode=mc_dropout"):    ((300, "mc_dropout"), (224, "mc_dropout")),
}


class Audit:
    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []

    def __call__(self, ok: bool, name: str, detail: str = "") -> bool:
        self.checks += 1
        if not ok:
            self.failures.append(f"{name}  {detail}".rstrip())
        return ok


def sig(lo: float, hi: float) -> bool:
    return lo > 0 or hi < 0


def fmt(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v):.3f}"


def pick_source() -> tuple[Path, Path, str]:
    for agg_dir, timing, label in SOURCES:
        if (agg_dir / "aggregate.csv").exists() and timing.exists():
            return agg_dir, timing, label
    raise SystemExit(
        "집계 산출물을 찾지 못했습니다. "
        "runs/malevis/aggregate-20260829/ 또는 docs/results/ 를 확인하십시오."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="논문 수치 독립 재계산 감사")
    ap.add_argument("--output", default=None, help="결과 JSON 경로")
    args = ap.parse_args()

    agg_dir, timing_path, label = pick_source()
    a = Audit()
    print(f"데이터 출처: {label}  ({agg_dir})\n")

    agg = {}
    with open(agg_dir / "aggregate.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            agg[(int(r["image_size"]), r["mode"], r["metric"])] = {
                k: float(v) for k, v in r.items() if k not in ("image_size", "mode", "metric")}
    pair = {}
    with open(agg_dir / "paired_comparisons.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pair[(r["comparison"], r["context"], r["metric"])] = {
                "mean_difference": float(r["mean_difference"]),
                "sd": float(r["standard_deviation_of_differences"]),
                "lo": float(r["ci95_lower"]), "hi": float(r["ci95_upper"])}
    tim = json.load(open(timing_path, encoding="utf-8"))
    tr = tim["runs"] if "runs" in tim and isinstance(tim["runs"], dict) else None
    if tr is None:   # 원본 형식(runs 가 리스트)
        tr = {str(x["image_size"]): {m: v for m, v in x["modes"].items()} for x in tim["runs"]}

    # A. 집계 CI 가 t 분포와 일치하는가
    for k, r in agg.items():
        hw = T_USED * r["standard_deviation"] / math.sqrt(N_SEEDS)
        a(abs((r["ci95_between_seed_upper"] - r["mean"]) - hw) < 1e-11, f"[A] agg CI upper {k}")
        a(abs((r["mean"] - r["ci95_between_seed_lower"]) - hw) < 1e-11, f"[A] agg CI lower {k}")
        a(r["minimum"] <= r["mean"] <= r["maximum"], f"[A] agg mean in range {k}")
    print(f"[A] 집계 CI · 범위      {len(agg)}개 지표")

    # B. 대응비교 평균차 == 집계 평균의 차
    for (cmp_, ctx, metric), r in pair.items():
        (asz, amd), (bsz, bmd) = DERIVE[(cmp_, ctx)]
        exp = agg[(asz, amd, metric)]["mean"] - agg[(bsz, bmd, metric)]["mean"]
        a(abs(r["mean_difference"] - exp) < 5e-9, f"[B] paired mean {cmp_}/{ctx}/{metric}",
          f"보고={r['mean_difference']:.12f} 기대={exp:.12f}")
        hw = T_USED * r["sd"] / math.sqrt(N_SEEDS)
        a(abs((r["hi"] - r["mean_difference"]) - hw) < 1e-11, f"[B] paired CI {cmp_}/{ctx}/{metric}")
    print(f"[B] 대응비교 정합성     {len(pair)}개 비교")

    # C. 표 2
    COL = {"224d": (224, "deterministic"), "224m": (224, "mc_dropout"),
           "300d": (300, "deterministic"), "300m": (300, "mc_dropout")}
    for metric, cells in TABLE2.items():
        for col, printed in cells.items():
            sz, md = COL[col]
            actual = f"{agg[(sz, md, metric)]['mean']:.3f}"
            a(actual == printed, f"[C] 표2 {metric} {col}", f"인쇄={printed} 실제={actual}")
    print(f"[C] 논문 표 2           {sum(len(v) for v in TABLE2.values())}개 셀")

    # D. 표 3
    for lab, cmp_, ctx, metric, p_mean, p_ci, p_sig in TABLE3:
        r = pair[(cmp_, ctx, metric)]
        a(fmt(r["mean_difference"]) == p_mean, f"[D] 표3 평균 {lab}", f"인쇄={p_mean} 실제={fmt(r['mean_difference'])}")
        ci = f"[{fmt(r['lo'])}, {fmt(r['hi'])}]"
        a(ci == p_ci, f"[D] 표3 CI {lab}", f"인쇄={p_ci} 실제={ci}")
        a(sig(r["lo"], r["hi"]) == p_sig, f"[D] 표3 유의 {lab}")
    print(f"[D] 논문 표 3           {len(TABLE3)}행")

    # E. 표 4 와 본문 배수
    for (sz, md), (p50, p95, tp) in TABLE4.items():
        m = tr[sz][md]
        a(f"{m['latency_p50_ms_per_image']:.2f}" == p50, f"[E] 표4 p50 {sz}/{md}")
        a(f"{m['latency_p95_ms_per_image']:.2f}" == p95, f"[E] 표4 p95 {sz}/{md}")
        a(f"{m['throughput_images_per_second']:.1f}" == tp, f"[E] 표4 tput {sz}/{md}")
    ratios = {}
    for lab, sz, key, printed in BODY_RATIOS:
        ratio = tr[sz]["mc_dropout"][key] / tr[sz]["deterministic"][key]
        ratios[lab] = ratio
        a(round(ratio, 1) == printed, f"[E] 본문 배수 {lab}", f"인쇄={printed} 실제={ratio:.4f}")
    a(round(max(ratios.values()), 1) == 16.4, "[E] 초록 '최대 16.4배'")
    print(f"[E] 표 4 · 본문 배수    {len(TABLE4)*3 + len(BODY_RATIOS) + 1}개 값")

    # E2. 실험 2 (BIG2015) — 표 5 와 본문 진단 수치
    big = REPO / "docs/results/big2015"
    if (big / "offgrid_summary.json").exists():
        off = json.load(open(big / "offgrid_summary.json", encoding="utf-8"))
        got = {(r["shift_rows"], r["channels"], r["upsampler"]): r["mae_start_bytes"] for r in off}
        for sh, cells in TABLE5.items():
            for (ch, up), printed in cells.items():
                a(abs(got[(sh, ch, up)] - printed) < 0.5, f"[E2] 표5 shift{sh} {ch}/{up}",
                  f"인쇄={printed} 실제={got[(sh, ch, up)]}")
        for (ch, up), printed in TABLE5_MEANS.items():
            vals = [got[(sh, ch, up)] for sh in (1, 2, 3, 4)]
            a(round(sum(vals) / len(vals)) == printed, f"[E2] 표5 평균 {ch}/{up}",
              f"인쇄={printed} 실제={sum(vals)/len(vals):.1f}")
        d = json.load(open(big / "guide_discriminability.json", encoding="utf-8"))["per_boundary"]
        dv = sum(x["cohen_d_byte_value"] for x in d) / len(d)
        de = sum(x["cohen_d_row_entropy"] for x in d) / len(d)
        a(round(dv, 2) == BODY_COHEN_D["byte_value"], "[E2] 본문 Cohen d 바이트값", f"실제={dv:.3f}")
        a(round(de, 2) == BODY_COHEN_D["row_entropy"], "[E2] 본문 Cohen d 행엔트로피", f"실제={de:.3f}")
        a(round(de / dv, 1) == BODY_COHEN_D["ratio"], "[E2] 본문 판별력 배수", f"실제={de/dv:.2f}")
        infl = (TABLE5_MEANS[("G1", "jbu")] / TABLE5_MEANS[("G1", "bilinear")])
        a(round(infl, 1) == BODY_JBU_INFLATION, "[E2] 본문 '5.0배'", f"실제={infl:.3f}")
        p0 = json.load(open(big / "p0a_result.json", encoding="utf-8"))["verdict"]
        a(p0["coordinate_systems_match"], "[E2] P0-a 좌표계 일치")
        a(p0["real_sections_aligned_4096"] == p0["n_real_sections"] == 8,
          "[E2] 본문 '실제 PE 섹션 8개 모두 4096 정렬'", f"실제={p0}")
        print(f"[E2] 실험 2 (BIG2015)   표5 {sum(len(v) for v in TABLE5.values())}칸 + "
              f"평균 4 + 진단 6")
    else:
        print("[E2] 실험 2 근거 없음 — 건너뜀 (docs/results/big2015/)")

    # F. 사전 판정 기준 재적용
    gates = {}
    for sz in ("224", "300"):
        f1 = pair[(MCD, f"image_size={sz}", "macro_f1")]
        ece = pair[(MCD, f"image_size={sz}", ECE)]
        ratio = (tr[sz]["mc_dropout"]["latency_p95_ms_per_image"]
                 / tr[sz]["deterministic"]["latency_p95_ms_per_image"])
        g = {"ga_macro_f1_not_worse": not (f1["hi"] < 0),
             "gb_ece_not_worse": not (ece["lo"] > 0),
             "gc_p95_within_3x": ratio <= 3.0, "p95_ratio": round(ratio, 4)}
        g["adopt"] = g["ga_macro_f1_not_worse"] and g["gb_ece_not_worse"] and g["gc_p95_within_3x"]
        gates[sz] = g
        a(g["ga_macro_f1_not_worse"], f"[F] {sz} (가) macro F1 유지")
        a(not g["gb_ece_not_worse"], f"[F] {sz} (나) ECE 악화 — 논문은 미달로 보고")
        a(not g["adopt"], f"[F] {sz} 채택 불가 판정")
    print("[F] 사전 판정 기준      224/300 재적용 -> 두 해상도 모두 채택 불가")

    # G. 정확한 t 로 재계산해도 유의성이 뒤집히지 않는가
    flipped = []
    for (cmp_, ctx, metric), r in pair.items():
        hw = T_EXACT * r["sd"] / math.sqrt(N_SEEDS)
        if sig(r["lo"], r["hi"]) != sig(r["mean_difference"] - hw, r["mean_difference"] + hw):
            flipped.append(f"{cmp_}/{ctx}/{metric}")
    a(not flipped, "[G] 정확 t 강건성", f"뒤집힌 항목 {flipped}")
    marg = pair[("300_minus_224", "mode=deterministic", "macro_recall")]
    marg_hi_exact = marg["mean_difference"] + T_EXACT * marg["sd"] / math.sqrt(N_SEEDS)
    print(f"[G] t 강건성            뒤집힘 {len(flipped)}개 · 최소여유 항목 상한 "
          f"{marg['hi']:+.6f} (정확 t {marg_hi_exact:+.6f})")

    print()
    ok = not a.failures
    print(f"{'통과' if ok else '실패'}: 검사 {a.checks}건 중 {len(a.failures)}건 실패")
    for f in a.failures[:40]:
        print("  FAIL " + f)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "source": label, "source_dir": str(agg_dir),
            "t_used": T_USED, "t_exact": T_EXACT, "n_seeds": N_SEEDS,
            "checks": a.checks, "failures": a.failures, "all_passed": ok,
            "latency_ratios": {k: round(v, 4) for k, v in ratios.items()},
            "pre_registered_gates": gates,
            "scope_verified": [
                "집계·대응비교·신뢰구간 산술", "유의성 판정",
                "논문 표2/표3/표4·본문 전사", "사전 판정 기준 재적용", "t 계수 강건성",
            ],
            "scope_not_verified": [
                "predictions.*.csv 로부터의 지표 계산", "학습 재현(GPU·데이터셋 필요)",
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n-> {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
