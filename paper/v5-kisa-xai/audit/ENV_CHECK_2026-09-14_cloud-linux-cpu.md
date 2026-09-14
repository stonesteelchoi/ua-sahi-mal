# 환경 구축·회귀검사 기록 — 2026-09-14 (클라우드 Linux CPU 샌드박스)

이 기록은 `HANDOFF_PROMPT_KO.md` 3절의 절차를 **GPU가 없는 Linux 샌드박스**에서 수행한 결과다. Windows NVIDIA 장비의 CUDA 검증은 아직 수행되지 않았다(→ `scripts/kisa_xai_env_check.ps1`로 수행 예정). 합성 smoke와 기존 테스트 통과는 저장소 코드의 회귀검사이며 v5 실험 결과가 아니다.

## 1. 저장소

| 항목 | 값 |
|---|---|
| clone | `git clone --branch research/kisa-xai-v5 --single-branch https://github.com/stonesteelchoi/ua-sahi-mal.git` |
| branch | `research/kisa-xai-v5` (origin과 일치) |
| HEAD | `d6b23867dd1510f4ec5a71cf7553f84772602e82` (`docs: add KISA XAI v5 LLM handoff`) |
| `4b1f6ee` ancestor | 예 (`git merge-base --is-ancestor 4b1f6ee HEAD` 성공) |
| 업로드된 인수인계 문서 vs 저장소 사본 | 줄바꿈(CRLF/LF) 정규화 후 동일 |

## 2. 실행 환경

| 항목 | 값 |
|---|---|
| OS | Ubuntu 24.04.4 LTS (Linux 6.18.44, x86_64), Anthropic 클라우드 샌드박스 |
| CPU / RAM | Intel Xeon 2.10GHz 2 vCPU / 7.8 GiB (swap 없음) |
| GPU | 없음 (`nvidia-smi` 없음, `/dev/nvidia*` 없음) |
| 디스크 | 설치 전 여유 30 GB → 설치 후 19 GB (`.venv` 7.4 GB; PyPI torch cu128 wheel + nvidia 런타임 포함) |
| Python | 3.12.3 (`python3.12 -m venv .venv`); 3.10.20, 3.11.15도 존재 |
| Git | 2.43.0 |

## 3. 설치 (`runs/kisa-xai-env-20260914-142740/install_cpu_linux.sh`, `scripts/setup.ps1` 절차를 bash로 재현)

| 단계 | 결과 |
|---|---|
| `git submodule update --init --recursive` | 성공 (external/sahi, external/upsample-anything, external/deepreflect) |
| pip/setuptools/wheel 업그레이드 | 1차 시도는 `files.pythonhosted.org` read timeout → `--retries 10 --timeout 180`으로 재시도 성공 |
| `torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu` | **실패**: 프록시가 `download.pytorch.org`를 `403 Forbidden`(조직 egress 정책)으로 차단 |
| 대체: PyPI `torch==2.8.0 torchvision==0.23.0` | 성공. 설치본은 `2.8.0+cu128` 빌드(CPU에서 실행, `cuda_available=false`) — 동일 버전 pin, 인덱스만 다름 |
| `opencv-python>=4.12.0.88,<5` + `-e external/sahi` | 성공 (cv2 4.14.0) |
| `-e .[dev]` | 성공 |
| `pip check` | `No broken requirements found.` |
| `ua_sahi_mal doctor` | torch 2.8.0 / torchvision 0.23.0 / sahi 0.12.2 / ultralytics 8.4.67, `bilinear_smoke_ok: true` |

## 4. 회귀검사 (`runs/kisa-xai-env-20260914-142740/summary.tsv`)

| 검사 | 결과 |
|---|---|
| `pip check` | 통과 |
| `ua_sahi_mal doctor --strict` | 통과 (`cuda_available: false`, `cuda_runtime: "12.8"`) |
| CUDA 계산 검사 | **실패 (예상됨)** — `AssertionError: CUDA unavailable`; GPU 없는 샌드박스 |
| CPU 행렬곱 대체 검사 | 통과 |
| `ruff check src tests scripts` | `All checks passed!` |
| `pytest` | **390 passed** in 6.29s |
| `ua_sahi_mal smoke` | 통과 (`tile_recall 1.0`, `detector_call_reduction 0.5`) |
| `ua_sahi_mal.evidence smoke` | 통과 (`search_recovers_planted_range`, `evidence_beats_random_control`, `budget_reduces_forward_passes` 모두 true, `mean_byte_iou 1.0`) |
| `scripts/check_repository_safety.py` | 통과 |
| `scripts/audit_paper_numbers.py` | `검사 285건 중 0건 실패` |
| `python -m build` | `ua_sahi_mal-0.2.0.tar.gz`, `ua_sahi_mal-0.2.0-py3-none-any.whl` 생성 |

## 5. `xai` 선택 의존성 검증

PyPI 조회(2026-09-14): grad-cam 최신 1.5.7 (2026-08-21), scikit-learn 1.9.1 (2026-09-10, Python ≥3.11), scipy 1.18.1 (2026-08-21, Python ≥3.12), pefile 2024.8.26.

`pyproject.toml`에 추가한 그룹:

```toml
xai = [
  "grad-cam>=1.5.5,<1.6",
  "opencv-python-headless>=4.12.0.88,<5",
  "pefile>=2024.8.26,<2025",
  "scikit-learn>=1.6,<2",
  "scipy>=1.13,<2",
]
```

| 검사 | 결과 |
|---|---|
| `pip install "grad-cam>=1.5.5,<1.6" "scikit-learn>=1.6,<2" "scipy>=1.13,<2"` | grad-cam 1.5.7, scikit-learn 1.9.1, scipy 1.18.1 설치. **부작용**: grad-cam 의존성 `opencv-python-headless` 5.0.0.93이 설치되어 `import cv2`가 5.0.0으로 바뀜(같은 `cv2/` 디렉터리 공유). 이 상태에서도 `smoke`·`pytest`는 통과했지만 프로젝트 pin(`opencv-python<5`)과 어긋남 |
| 조치 | `opencv-python-headless>=4.12.0.88,<5`를 xai 그룹에 명시 → headless 4.14.0.94 재설치, `import cv2` → 4.14.0, `pip check` 통과 |
| `pip install -e ".[dev,xai]"` | 성공, `pip check` 통과 |
| import smoke | `cv2 4.14.0, sklearn 1.9.1, scipy 1.18.1, pefile 2024.8.26, pytorch_grad_cam` 정상 |
| CPU Grad-CAM 1건 (`xai_gradcam_smoke.py`) | ResNet-18(랜덤 가중치, `conv1` 1채널, `num_classes=2`), 합성 입력 2×1×224×224, target layer `layer4.1`(=`model.layer4[-1]`, 7×7×512), target = class-1 logit. CAM 224×224 유한값. seed 43/44: 라이브러리 CAM과 forward/backward hook 기반 자체 구현(bilinear, `align_corners=False`)의 Spearman ρ ≈ 0.99999. seed 42: 양수 CAM이 전혀 없는 **empty CAM** 사례 재현(라이브러리·자체 구현 모두 0) → 프로토콜의 `cam_empty=true` 보존 정책이 필요함을 확인 |
| CUDA Grad-CAM 1건 | **미수행** (GPU 없음) — Windows 장비에서 수행 필요 |
| `pip freeze` | [`pip-freeze_2026-09-14_cloud-linux-cpu-py312.txt`](pip-freeze_2026-09-14_cloud-linux-cpu-py312.txt) |

주의: torchvision 사전학습 가중치(`ResNet18_Weights`)는 `download.pytorch.org`에서 받으므로 이 샌드박스와 KISA 폐쇄망 모두에서 자동 다운로드가 불가능하다. 가중치 파일과 SHA-256을 사전에 확보·기록해야 한다.

## 6. 이 세션에서 생성·수정한 파일

- 수정: `pyproject.toml` — `[project.optional-dependencies] xai` 추가
- 추가: `scripts/kisa_xai_env_check.ps1` — Windows GPU 장비용 환경·CUDA·회귀검사 일괄 기록 스크립트 (PowerShell 7.5.2 파서로 구문 검사 통과; Windows 실행은 미검증)
- 추가: `paper/v5-kisa-xai/audit/data_access_audit_20260914.json`, `DATA_ACCESS_AUDIT_2026-09-14.md`, 본 문서, pip freeze 사본
- 로컬 전용(gitignore): `runs/kisa-xai-env-20260914-142740/` (설치 로그 3회 시도, 검사 로그, `summary.tsv`, `pip-freeze*.txt`, Grad-CAM smoke JSON), `runs/smoke/20260914_144015/`, `.venv/`

## 7. 미완료

- Windows NVIDIA 장비의 `setup.ps1 -TorchIndex cu128`, 실제 CUDA 계산, CUDA Grad-CAM, VRAM/RAM/디스크 기록
- KISA 데이터 확보 및 P0 본 감사 (→ `DATA_ACCESS_AUDIT_2026-09-14.md`)
