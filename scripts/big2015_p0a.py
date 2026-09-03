"""P0-a: BIG2015 .bytes <-> .asm 좌표계 검증 + W=512 행 정렬 검증.

연구설계서 v1 §5 Tier 2 의 전제를 실제 데이터로 확인한다.
"""
import glob
import json
import os
import re

import numpy as np

BYTES_LINE = re.compile(r"^([0-9A-Fa-f]{6,16})\s")
ASM_LINE = re.compile(r"^([\w.$]+):([0-9A-Fa-f]{6,16})\b")
W = 512
# IDA 가 붙이는 라벨 중 실제 PE 섹션인 것
REAL_SECTIONS = {".text", ".rdata", ".data", ".rsrc", ".reloc", ".bss", "CODE", "DATA", "UPX0", "UPX1"}

def parse_bytes(path):
    """VA 인덱싱된 hex 덤프 -> (uint8 배열, base VA, 유효 마스크)."""
    data, mask, base = bytearray(), bytearray(), None
    with open(path, encoding="latin-1", errors="ignore") as f:
        for line in f:
            m = BYTES_LINE.match(line)
            if not m:
                continue
            va = int(m.group(1), 16)
            if base is None:
                base = va
            off = va - base
            if off < 0:
                continue
            while len(data) < off:            # 주소 공백은 0 으로 메우고 무효 표시
                data.append(0)
                mask.append(0)
            for t in line.split()[1:]:
                if t == "??":
                    data.append(0)
                    mask.append(0)
                else:
                    data.append(int(t, 16))
                    mask.append(1)
    return np.frombuffer(bytes(data), np.uint8), base or 0, np.frombuffer(bytes(mask), np.uint8).astype(bool)

def parse_asm(path):
    seg = {}
    with open(path, encoding="latin-1", errors="ignore") as f:
        for line in f:
            m = ASM_LINE.match(line)
            if not m:
                continue
            name, va = m.group(1), int(m.group(2), 16)
            lohi = seg.setdefault(name, [va, va])
            lohi[0] = min(lohi[0], va)
            lohi[1] = max(lohi[1], va)
    return seg

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

out = {"samples": [], "width": W}
for b in sorted(glob.glob("datasets/big2015_sample/*.bytes")):
    sid = os.path.basename(b)[:-6]
    buf, base, mask = parse_bytes(b)
    seg = parse_asm(b[:-6] + ".asm")
    rows = []
    for name, (lo, hi) in sorted(seg.items(), key=lambda kv: kv[1][0]):
        off = lo - base
        rows.append({
            "name": name, "va_lo": lo, "va_hi": hi, "dump_offset": off,
            "real_section": name in REAL_SECTIONS,
            "in_range": 0 <= off < buf.size,
            "aligned_512": off % 512 == 0, "aligned_4096": off % 4096 == 0,
        })
    ent = row_entropy(buf)
    out["samples"].append({
        "id": sid, "base_va": base, "dump_bytes": int(buf.size),
        "valid_fraction": float(mask.mean()),
        "unknown_fraction": float(1 - mask.mean()),
        "rows": int(np.ceil(buf.size / W)),
        "row_entropy_mean": float(ent.mean()),
        "row_entropy_p05": float(np.percentile(ent, 5)),
        "row_entropy_p95": float(np.percentile(ent, 95)),
        "segments": rows,
    })
    np.save(f"{sid}.bytes.npy", buf)
    np.save(f"{sid}.mask.npy", mask)
    np.save(f"{sid}.ent.npy", ent)
    json.dump(rows, open(f"{sid}.segments.json", "w"), indent=1)

# --- 집계 판정 ---
real = [s for smp in out["samples"] for s in smp["segments"] if s["real_section"] and s["in_range"]]
sub = [s for smp in out["samples"] for s in smp["segments"] if not s["real_section"]]
out["verdict"] = {
    "n_real_sections": len(real),
    "real_sections_aligned_512": sum(s["aligned_512"] for s in real),
    "real_sections_aligned_4096": sum(s["aligned_4096"] for s in real),
    "n_nonsection_labels": len(sub),
    "nonsection_aligned_512": sum(s["aligned_512"] for s in sub),
    "coordinate_systems_match": all(
        any(s["in_range"] for s in smp["segments"]) for smp in out["samples"]),
}
json.dump(out, open("p0a_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps({"verdict": out["verdict"],
                  "per_sample": [{k: v for k, v in s.items() if k != "segments"} for s in out["samples"]]},
                 ensure_ascii=False, indent=2))
