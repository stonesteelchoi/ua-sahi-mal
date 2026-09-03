"""격자에 어긋난 경계에서의 복원 실험 — 설계가 실제로 겨냥하는 조건.

실제 PE 섹션 경계는 4096 정렬이고 P3 한 셀도 8행 x 512B = 4096B 이므로,
경계가 저해상도 격자에 정확히 떨어진다. 복원할 셀 내부 정보가 없으니
업샘플러 간 차이가 나타날 수 없다. 설계가 겨냥하는 것은 주입 페이로드처럼
**임의 오프셋의 경계**이므로, GT 밴드를 셀 내부로 이동시켜 그 조건을 만든다.

동시에 가이드 채널의 판별력을 직접 측정해 JBU 열세의 원인을 진단한다.
"""
import collections
import json
import sys

import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from uasahimal.upsample import BilinearUpsampler, FixedJBUUpsampler, NearestUpsampler  # noqa: E402

W, STRIDE = 512, 8              # P3
SHIFT_ROWS = [0, 1, 2, 3, 4]    # 셀(8행) 안에서의 경계 위치
UPS = {"nearest": NearestUpsampler(), "bilinear": BilinearUpsampler(),
       "jbu": FixedJBUUpsampler(sigma_s=1.0, sigma_r=0.12, radius=3)}

def row_entropy(buf, width=W):
    n = buf.size
    h = max(1, -(-n // width))
    pad = np.zeros(h * width, np.uint8)
    pad[:n] = buf
    flat = pad.astype(np.int64) + (np.repeat(np.arange(h, dtype=np.int64), width) << 8)
    hist = np.bincount(flat, minlength=h << 8).reshape(h, 256).astype(np.float64)
    cnt = np.full(h, float(width))
    if n % width:
        hist[-1, 0] -= (width - n % width)
        cnt[-1] = n % width
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(hist > 0, hist * np.log2(hist), 0.0)
    return (np.log2(np.maximum(cnt, 1)) - terms.sum(1) / np.maximum(cnt, 1)).astype(np.float32)

def guides(buf, H):
    total = H * W
    flat = np.zeros(total, np.uint8)
    flat[:buf.size] = buf
    g1 = np.stack([flat.reshape(H, W)] * 3, -1)
    ent = np.repeat(np.clip(row_entropy(buf) / 8 * 255, 0, 255).astype(np.uint8), W)
    ent = np.resize(ent, total).reshape(H, W)
    c = np.bincount(buf, minlength=256)
    rank = np.argsort(np.argsort(-c)).astype(np.uint8)
    frq = np.zeros(total, np.uint8)
    frq[:buf.size] = rank[buf]
    g3 = np.stack([flat.reshape(H, W), ent, frq.reshape(H, W)], -1)
    return {"G1": g1, "G3": g3}

records, diag = [], []
for sid in ["0A32eTdBKayjCWhZqDOQ", "0ACDbR5M3ZhBJajygTuf"]:
    buf = np.load(f"{sid}.bytes.npy")
    segs = [s for s in json.load(open(f"{sid}.segments.json"))
            if s["real_section"] and s["in_range"] and s["aligned_512"]]
    H0 = int(np.ceil(buf.size / W))
    Hp = -(-H0 // STRIDE) * STRIDE
    G = guides(buf, Hp)
    ent_rows = row_entropy(buf)

    base = []
    for i, s in enumerate(segs):
        r0 = s["dump_offset"] // W
        end = segs[i + 1]["dump_offset"] if i + 1 < len(segs) else buf.size
        r1 = min(H0, max(r0 + 1, -(-end // W)))
        if r1 - r0 > 16:
            base.append((s["name"], r0, r1))
    if len(base) < 2:
        continue

    # --- 진단: 경계에서 바이트값 vs 행 엔트로피 중 무엇이 판별적인가 ---
    for name, r0, _r1 in base[1:]:
        a, b = slice(max(0, r0 - 8), r0), slice(r0, min(H0, r0 + 8))
        va = buf[a.start * W:a.stop * W].astype(float)
        vb = buf[b.start * W:b.stop * W].astype(float)
        ea, eb = ent_rows[a], ent_rows[b]
        pool_v = np.sqrt((va.var() + vb.var()) / 2) or 1e-9
        pool_e = np.sqrt((ea.var() + eb.var()) / 2) or 1e-9
        diag.append(dict(sample=sid, boundary=name,
                         cohen_d_byte_value=round(float(abs(va.mean() - vb.mean()) / pool_v), 3),
                         cohen_d_row_entropy=round(float(abs(ea.mean() - eb.mean()) / pool_e), 3)))

    for shift in SHIFT_ROWS:
        bands = [(n, r0 + shift, r1 + shift) for n, r0, r1 in base
                 if r1 + shift <= H0]
        if len(bands) < 2:
            continue
        gt = np.zeros((len(bands), Hp, W), np.float32)
        for c, (_, r0, r1) in enumerate(bands):
            gt[c, r0:r1, :] = 1.0
        h_lr, w_lr = Hp // STRIDE, W // STRIDE
        lr = gt[:, :, :w_lr * STRIDE].reshape(len(bands), h_lr, STRIDE, w_lr, STRIDE).mean((2, 4))
        for chan, guide in G.items():
            for upname, up in UPS.items():
                if chan == "G3" and upname != "jbu":
                    continue
                hr = up(guide, lr.astype(np.float32))
                hr = hr.transpose(1, 2, 0) if hr.ndim == 3 else hr[..., None]
                for c, (segname, r0, r1) in enumerate(bands):
                    prof = hr[..., c].mean(1)
                    on = np.where(prof >= 0.5)[0]
                    if on.size == 0:
                        d0 = d1 = (r1 - r0) * W
                    else:
                        d0, d1 = abs(int(on[0]) - r0) * W, abs(int(on[-1]) + 1 - r1) * W
                    records.append(dict(sample=sid, section=segname, shift_rows=shift,
                                        channels=chan, upsampler=upname,
                                        d_start_bytes=int(d0), d_end_bytes=int(d1)))

json.dump({"records": records, "diagnostic": diag}, open("offgrid_raw.json", "w"), indent=1)

print("=== 진단: 섹션 경계 전후 8행의 표준화 평균차 (Cohen's d) ===")
dv = np.array([d["cohen_d_byte_value"] for d in diag])
de_ = np.array([d["cohen_d_row_entropy"] for d in diag])
print(f"  바이트 값      d = {dv.mean():.3f}  (중앙값 {np.median(dv):.3f})")
print(f"  행 엔트로피    d = {de_.mean():.3f}  (중앙값 {np.median(de_):.3f})")
print(f"  -> 엔트로피가 바이트 값보다 {de_.mean()/max(dv.mean(),1e-9):.1f}배 판별적\n")

agg = collections.defaultdict(list)
for r in records:
    agg[(r["shift_rows"], r["channels"], r["upsampler"])].append(r)
print("=== 경계를 셀(8행=4096B) 안으로 이동시켰을 때 MAE_start (바이트) ===")
print(f"{'shift':>5} {'':>3} " + "".join(f"{n:>12}" for n in ["G1 nearest","G1 bilinear","G1 jbu","G3 jbu"]))
print("-" * 62)
summary = []
for sh in SHIFT_ROWS:
    cells = []
    for chan, up in [("G1","nearest"),("G1","bilinear"),("G1","jbu"),("G3","jbu")]:
        rs = agg.get((sh, chan, up), [])
        if not rs:
            cells.append("     -")
            continue
        m = float(np.mean([r["d_start_bytes"] for r in rs]))
        cells.append(f"{m:>12.0f}")
        summary.append(dict(shift_rows=sh, channels=chan, upsampler=up, n=len(rs),
                            mae_start_bytes=round(m, 1)))
    print(f"{sh:>5} 행 " + "".join(cells))
json.dump(summary, open("offgrid_summary.json", "w"), indent=1)
