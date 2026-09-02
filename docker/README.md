# Docker 재현 환경

UA-SAHI-MAL 을 어느 장비에서나 같은 의존성 조합으로 돌리기 위한 컨테이너 정의다.
데이터셋·체크포인트·실행 산출물은 이미지에 굽지 않고 호스트에서 마운트한다.

## 빠른 시작

```bash
# 1) 빌드 (CPU)
docker compose -f docker/docker-compose.yml build

# 2) 환경 검증 — 정적 검사 + 테스트 107건 + 외부 데이터 없는 합성 스모크
docker compose -f docker/docker-compose.yml run --rm verify

# 3) 네트워크를 완전히 끊고 같은 검증 (오프라인 fail-closed 확인)
docker compose -f docker/docker-compose.yml run --rm offline

# 4) 대화형 셸
docker compose -f docker/docker-compose.yml run --rm shell
```

검증 결과는 `runs/verification/<타임스탬프>/verification.json` 에 남는다.

## 빌드 인자

| 인자 | 기본값 | 용도 |
|---|---|---|
| `PYTHON_VERSION` | `3.12` | `pyproject.toml` 이 `>=3.10,<3.13` 을 요구한다 |
| `TORCH_VERSION` | `2.8.0` | |
| `TORCHVISION_VERSION` | `0.23.0` | |
| `TORCH_INDEX_URL` | `https://download.pytorch.org/whl/cpu` | GPU 는 `.../whl/cu124`. 사내 프록시가 이 호스트를 막으면 `pypi` 로 지정하면 PyPI 에서 받는다(리눅스 휠은 CUDA 런타임을 포함하므로 이미지가 커진다). |

```bash
docker build -f docker/Dockerfile \
  --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124 \
  -t ua-sahi-mal:cu124 .
```

GPU 로 실행할 때는 compose 서비스에 `deploy.resources.reservations.devices` 또는
`docker run --gpus all` 을 추가한다.

## 설계 메모

- **torch 를 별도 레이어로 먼저 설치한다.** 소스가 바뀌어도 가장 무거운 레이어가 재사용된다.
- **벤더링된 SAHI 를 `--no-deps -e` 로 설치한다.** `pyproject.toml` 이 `sahi==0.12.2` 를 핀하고
  `external/sahi` 도 같은 0.12.2 이므로, 편집 가능 설치가 핀을 충족해 PyPI 에서 다시 받지 않는다.
- **`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` 을 고정한다.** 스레드 수가 흔들리면 CPU latency
  측정이 재현되지 않는다. 처리량이 필요한 실행에서는 명시적으로 올려서 쓰고, 그 값을 함께 보고할 것.
- **`opencv-python`(headless 아님) 때문에 `libgl1`, `libglib2.0-0` 이 필요하다.** 의존성 핀을
  건드리지 않기 위해 헤드리스로 바꾸는 대신 시스템 라이브러리를 넣었다.
- `YOLO_CONFIG_DIR=/tmp/ultralytics` — Ultralytics 가 홈 디렉터리에 설정을 쓰려다 실패하는 것을 막는다.

## 검증 상태 (정직하게)

2026-09-02 기준, **이미지 빌드 자체는 아직 실행되지 않았다.** 작성 환경의 egress 프록시가
Docker Hub·ECR Public·GHCR·quay.io·mirror.gcr.io 를 모두 403 으로 차단해 베이스 이미지를
받을 수 없었기 때문이다.

대신 **동일한 인터프리터·동일한 핀 조합을 네이티브로 구성해 다음을 실측 검증했다.**

| 항목 | 결과 |
|---|---|
| Python | 3.12.3 |
| torch / torchvision | 2.8.0 / 0.23.0 (CUDA 미사용, `cuda_available=false`) |
| ultralytics / sahi | 8.4.67 / 0.12.2 (벤더링 편집 설치) |
| numpy / opencv-python / shapely | 2.2.6 / 4.14.0.94 / 2.1.2 |
| 의존성 해결 | 충돌 없음 |
| `ruff check src scripts tests` | 통과 (`external/` 의 서드파티 경고 19건은 범위에서 제외) |
| `pytest` | **107 passed** |
| 합성 스모크 | 통과 — `detector_call_reduction=0.5`, `tile_recall=1.0` |
| 재실행 | 동일 결과 (멱등) |

즉 **위험한 부분(의존성 그래프와 테스트)은 검증되었고, 검증되지 않은 것은 베이스 이미지 pull 한 줄**이다.
네트워크가 되는 장비에서 위 `docker compose build` 를 한 번 돌려 `verification.json` 의
`all_passed: true` 를 확인한 뒤 그 파일을 커밋하면 검증이 완결된다.

## GPU 실험이 아직 남아 있다

README 상단의 "후속 단계"에 있는 항목 중 GPU 가 필요한 것:

- 공식 Upsample Anything test-time optimization 의 실제 GPU 비용·정확도
- dataset 수준 COCO `AP_S`, end-to-end p50/p95 latency, peak VRAM 자동 측정

이 컨테이너는 `TORCH_INDEX_URL` 만 CUDA 인덱스로 바꾸면 그대로 GPU 장비에서 쓸 수 있다.
latency 를 보고할 때는 `OMP_NUM_THREADS` 값과 warm-up 횟수, CUDA synchronize 여부를 함께 적을 것.
