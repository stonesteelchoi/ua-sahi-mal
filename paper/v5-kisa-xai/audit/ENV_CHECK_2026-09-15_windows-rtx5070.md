# 환경 검증 기록 — 2026-09-15 (Windows 11, RTX 5070 Laptop 8 GB)

`scripts/kisa_xai_env_check.ps1`(설치 옵션 없이, 기존 `.venv` 사용)를 사용자가 `C:\research\ua-sahi-mal`에서 실행한 결과다. 원본 산출물은 로컬 `runs/kisa-xai-env-20260915-004124/`(gitignore)에 있고, 이 문서는 그중 `summary.json`, `nvidia-smi.txt`, `03_cuda_compute.log`, `06_pytest.log`, `pip-freeze.txt`를 읽어 옮긴 것이다. 회귀검사 통과는 v5 실험 결과가 아니다.

## 1. 장비·소프트웨어

| 항목 | 값 |
|---|---|
| OS | Microsoft Windows 11 Home 10.0.26200 |
| RAM | 31.7 GiB (검사 시 여유 14.0 GiB) |
| 디스크 | C: 352.8 GiB 중 145.4 GiB 여유, D: 600 GiB 중 590.4 GiB 여유 |
| GPU | NVIDIA GeForce RTX 5070 Laptop GPU, 8151 MiB (WDDM), compute capability (12, 0) |
| 드라이버 | NVIDIA-SMI / KMD 616.56, CUDA UMD 13.4 (드라이버 표시값; torch 런타임과는 별개) |
| Python | 3.12.10 (`.venv` 존재) |
| torch / torchvision | 2.8.0+cu128 / 0.23.0+cu128, `torch.version.cuda` = 12.8 |
| 저장소 | `research/kisa-xai-v5` @ `0dfa9a9`, `4b1f6ee` ancestor = true, `git_dirty = true`(루트의 미추적 `.patch`/`.bundle` 때문; 추적 파일 수정 없음) |

## 2. 실제 CUDA 계산 (`03_cuda_compute`)

```text
torch= 2.8.0+cu128
cuda_runtime= 12.8
gpu= NVIDIA GeForce RTX 5070 Laptop GPU (12, 0)
vram_total_mib= 8123 vram_free_mib= 7013
CUDA computation OK: cuda:0
```

`doctor --strict`도 `cuda_available: true`, `cuda_device: NVIDIA GeForce RTX 5070 Laptop GPU`를 보고했다. 8 GB VRAM 중 검사 시점 여유는 약 7.0 GB였으므로 프로토콜의 `batch_size: measured_on_rtx5070_8gb`는 pilot에서 실측해야 한다.

## 3. 회귀검사 (`summary.json`, 총 1분 45초)

| 단계 | 결과 | 시간 |
|---|---|---|
| 01_pip_check | ok — `No broken requirements found.` | 2.7 s |
| 02_doctor_strict | ok | 52.7 s |
| 03_cuda_compute | ok | 2.4 s |
| 04_pip_freeze | ok (131개 패키지) | 0.6 s |
| 05_ruff | ok — `All checks passed!` | 7.3 s |
| 06_pytest | ok — **420 passed in 16.25s** | 19.8 s |
| 07_smoke | ok (`tile_recall 1.0`, `detector_call_reduction 0.5`) | 0.2 s |
| 08_evidence_smoke | ok (`mean_byte_iou 1.0`, 세 판정 모두 true) | 2.5 s |
| 09_repository_safety | ok | 1.7 s |
| 10_audit_paper_numbers | ok — 285건 중 0건 실패 | 0.1 s |
| 11_build | ok — sdist·wheel 생성 (stderr 진행 메시지가 빨간 NativeCommandError로 표시됐으나 exit 0) | 10.9 s |

## 4. 아직 안 된 것

- `xai` 선택 의존성(grad-cam, scikit-learn 등)은 Windows `.venv`에 **미설치** (`pip freeze`에 grad-cam·scikit-learn 없음, scipy 1.18.1만 존재). → `.\.venv\Scripts\python.exe -m pip install -e ".[dev,xai]"` 후 `import cv2`가 4.x인지 확인.
- **CUDA Grad-CAM 1건 미수행** → `scripts/kisa_xai_gradcam_smoke.py --out runs/kisa-xai-env-<tag>/gradcam_smoke.json` (이번 커밋에서 추가; CPU에서는 seed 43 라이브러리 vs hook Spearman ≈ 1.0, seed 42 empty CAM 확인).
- 100~500개 비실행 정적 pilot(시간·VRAM·디스크·파싱 실패율)은 데이터 확보 후.

## 5. 스크립트 수정 (이번 커밋)

- 로그를 UTF-8로 기록(이전 실행 로그는 Windows PowerShell 5.1 `Tee-Object` 기본값인 UTF-16으로 저장됨).
- 네이티브 stderr를 문자열로 변환해 `python -m build` 진행 메시지가 빨간 오류 블록으로 표시되지 않게 함. 판정 로직(exit code)은 동일.

## 6. pip freeze

[`pip-freeze_2026-09-15_windows-rtx5070-py312.txt`](pip-freeze_2026-09-15_windows-rtx5070-py312.txt) (원본 UTF-16 → UTF-8 변환, 131줄).
