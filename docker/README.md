# Docker 재현 환경

장비 간 의존성 차이를 없애기 위한 컨테이너 정의. 데이터셋·체크포인트·실행 산출물은
이미지에 굽지 않고 호스트에서 마운트한다.

## 빠른 시작

```bash
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml run --rm verify    # ruff + pytest 107건 + 합성 스모크
docker compose -f docker/docker-compose.yml run --rm offline   # 네트워크를 끊고 같은 검증
docker compose -f docker/docker-compose.yml run --rm shell     # 대화형 셸
```

`make build`, `make verify`, `make offline`, `make shell` 로도 같은 일을 한다.

**Windows** 에서는 한 번에 처리하는 스크립트를 쓴다.

```powershell
.\scripts\setup_docker.ps1
```

빌드 → 검증 → 오프라인 재검증을 순서대로 돌리고, 결과 `verification.json` 을
`docs/verification/` 에 복사해 바로 커밋할 수 있는 상태로 만든다.

## 막힌 네트워크에서의 탈출구

사내 프록시가 외부를 막는 환경을 전제로 설계했다. 세 개의 손잡이가 있다.

| ARG / 환경변수 | 기본값 | 언제 쓰나 |
|---|---|---|
| `BASE_IMAGE` | `python:3.12-slim` | Docker Hub 가 막힐 때 사내 레지스트리 미러로 교체 |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cpu` | 이 호스트가 막히면 `pypi`. GPU 면 `.../whl/cu124` |
| `APT_MIRROR` | (없음) | `deb.debian.org` 가 막힐 때 사내 Debian 미러 |

`.env` 파일에 넣거나 명령줄로 넘긴다.

```bash
# .env
BASE_IMAGE=registry.corp/library/python:3.12-slim
TORCH_INDEX_URL=pypi
APT_MIRROR=http://mirror.corp/debian
```

```powershell
.\scripts\setup_docker.ps1 -TorchIndexUrl pypi -BaseImage registry.corp/library/python:3.12-slim
```

GPU 로 쓰려면 `TORCH_INDEX_URL` 을 CUDA 인덱스로 바꾸고 실행 시 `--gpus all` 을 준다.

## 설계 메모

- **torch 를 독립 레이어로 먼저 설치한다.** 소스가 바뀌어도 가장 무거운 레이어가 재사용된다.
- **벤더링된 SAHI 를 `--no-deps -e` 로 설치한다.** `pyproject.toml` 의 `sahi==0.12.2` 핀과
  `external/sahi` 가 같은 0.12.2 이므로, 편집 가능 설치가 핀을 충족해 PyPI 에서 다시 받지 않는다.
- **`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` 고정.** 스레드 수가 흔들리면 CPU latency 측정이
  재현되지 않는다. 처리량이 필요하면 명시적으로 올리고 그 값을 함께 보고할 것.
- **`libgl1`, `libglib2.0-0` 을 넣는다.** `opencv-python`(headless 아님) 핀을 바꾸지 않기 위해서다.
- **설치 직후 import 스모크를 건다.** 레이어가 조용히 깨진 채 넘어가지 않도록 빌드 중에 잡는다.

## 검증 상태

| 항목 | 상태 |
|---|---|
| Dockerfile 파싱 및 `BASE_IMAGE` ARG 치환 | 확인됨 |
| `docker compose config` | 통과 |
| 의존성 해결 (Python 3.12.3 / torch 2.8.0 / torchvision 0.23.0 / ultralytics 8.4.67 / SAHI 0.12.2) | 충돌 없음 |
| `ruff check src scripts tests` | 통과 (`external/` 서드파티 19건은 범위 밖) |
| `pytest` | **107 passed** |
| 합성 스모크 | 통과 (`detector_call_reduction=0.5`, `tile_recall=1.0`) |
| 재실행 멱등성 | 확인됨 |
| **이미지 빌드 실행** | **미실행** — 아래 참조 |

이미지 빌드만 아직 실행되지 않았다. 작성 환경의 egress 프록시가 Docker Hub·ECR Public·
GHCR·quay.io·mirror.gcr.io 와 `deb.debian.org` 를 전부 403 으로 차단해 베이스 이미지를
받을 수 없었기 때문이다. 위험한 부분(의존성 그래프와 테스트)은 동일 핀 조합을 네이티브로
구성해 실측 검증했고, 남은 것은 베이스 이미지 pull 한 줄이다.

**이 칸은 두 경로 중 하나로 채워진다.**

1. `.github/workflows/verify.yml` — GitHub 에 push 하면 러너가 이미지를 빌드하고 컨테이너
   안에서, 그리고 `--network none` 으로 한 번 더 검증한다. 결과는 아티팩트와 job summary 로 남는다.
2. 네트워크가 되는 장비에서 `.\scripts\setup_docker.ps1` 을 한 번 실행하고, 생성된
   `docs/verification/verification-<날짜>-docker.json` 을 커밋한다.

## 아직 남은 GPU 실험

- 공식 Upsample Anything test-time optimization 의 실제 GPU 비용·정확도
- dataset 수준 COCO `AP_S`, end-to-end p50/p95 latency, peak VRAM 자동 측정

latency 를 보고할 때는 스레드 수, warm-up 횟수, CUDA synchronize 여부를 함께 적을 것.
