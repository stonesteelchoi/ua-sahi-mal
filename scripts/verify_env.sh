#!/usr/bin/env bash
# 환경 검증 스크립트. Docker 컨테이너 안/밖 어디서든 동일하게 동작한다.
#
#   bash scripts/verify_env.sh [출력디렉터리]
#
# 수행 항목
#   1. 인터프리터·핵심 패키지 버전 기록
#   2. ruff 정적 검사 (저장소 코드만. external/ 는 서드파티라 제외)
#   3. pytest 전체 실행
#   4. 외부 데이터·GPU 없이 도는 합성 end-to-end 스모크
#   5. 결과를 verification.json 으로 저장
set -uo pipefail

OUT="${1:-runs/verification/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
PY="${PYTHON:-python}"

export YOLO_CONFIG_DIR="${YOLO_CONFIG_DIR:-/tmp/ultralytics}"
export MPLBACKEND="${MPLBACKEND:-Agg}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

echo "== 1/4 환경 =="
"$PY" - <<'PYEOF' | tee "$OUT/environment.json"
import json, platform
from importlib.metadata import version, PackageNotFoundError
pkgs = ["torch","torchvision","ultralytics","sahi","numpy","opencv-python","shapely",
        "pillow","PyYAML","click","tqdm","pytest","ruff"]
def v(p):
    try: return version(p)
    except PackageNotFoundError: return None
info = {"python": platform.python_version(), "platform": platform.platform(),
        "machine": platform.machine(), "packages": {p: v(p) for p in pkgs}}
try:
    import torch
    info["torch_cuda_available"] = bool(torch.cuda.is_available())
    info["torch_device_count"] = torch.cuda.device_count() if torch.cuda.is_available() else 0
except Exception as exc:
    info["torch_error"] = repr(exc)
print(json.dumps(info, indent=2))
PYEOF

echo "== 2/4 ruff (저장소 코드) =="
ruff check src scripts tests > "$OUT/ruff.txt" 2>&1
RUFF=$?; tail -3 "$OUT/ruff.txt"

echo "== 3/4 pytest =="
# 프로젝트 addopts 에 이미 -q 가 있다. 여기서 -q 를 또 주면 -qq 가 되어 요약 줄이 사라진다.
"$PY" -m pytest --no-header > "$OUT/pytest.txt" 2>&1
PYTEST=$?; tail -3 "$OUT/pytest.txt"

echo "== 4/4 합성 스모크 =="
# smoke 는 비어 있지 않은 디렉터리를 거부한다(덮어쓰기 사고 방지). 재실행 시 비운다.
rm -rf "$OUT/smoke"
"$PY" -m ua_sahi_mal smoke --output-dir "$OUT/smoke" > "$OUT/smoke.txt" 2>&1
SMOKE=$?; tail -15 "$OUT/smoke.txt"

"$PY" - "$OUT" "$RUFF" "$PYTEST" "$SMOKE" <<'PYEOF'
import json, pathlib, re, sys, datetime
out, ruff, pytest_rc, smoke = pathlib.Path(sys.argv[1]), *map(int, sys.argv[2:5])
def read(name):
    p = out / name
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
m = re.search(r"(\d+) passed", read("pytest.txt"))
summary = {
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "environment": json.loads(read("environment.json") or "{}"),
    "ruff": {"exit_code": ruff, "passed": ruff == 0, "scope": "src scripts tests"},
    "pytest": {"exit_code": pytest_rc, "passed": pytest_rc == 0,
               "tests_passed": int(m.group(1)) if m else None},
    "smoke": {"exit_code": smoke, "passed": smoke == 0},
}
sp = out / "smoke" / "smoke_summary.json"
if sp.exists():
    summary["smoke"]["summary"] = json.loads(sp.read_text(encoding="utf-8"))
summary["all_passed"] = all(s["passed"] for s in (summary["ruff"], summary["pytest"], summary["smoke"]))
(out / "verification.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: summary[k] for k in ("ruff", "pytest", "smoke", "all_passed")},
                 indent=2, ensure_ascii=False))
print(f"\n-> {out/'verification.json'}")
sys.exit(0 if summary["all_passed"] else 1)
PYEOF
