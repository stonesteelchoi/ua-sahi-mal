# UA-SAHI-MAL 재현 환경 (CPU 기본)
#
#   docker build -f docker/Dockerfile -t ua-sahi-mal:cpu .
#
# 막힌 네트워크에서의 탈출구는 두 개의 ARG 다.
#   BASE_IMAGE       사내 레지스트리 미러로 통째로 교체 (예: registry.corp/library/python:3.12-slim)
#   TORCH_INDEX_URL  download.pytorch.org 가 막히면 `pypi`, GPU 면 CUDA 인덱스
#
# 자세한 사용법과 현재 검증 상태는 docker/README.md 참조.

ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.title="ua-sahi-mal" \
      org.opencontainers.image.description="Reproduction environment for UA-SAHI-MAL malware-image research" \
      org.opencontainers.image.source="https://github.com/stonesteelchoi/ua-sahi-mal" \
      org.opencontainers.image.licenses="MIT"

# opencv-python(headless 아님)이 요구하는 런타임 라이브러리.
# 의존성 핀을 바꾸지 않기 위해 headless 로 교체하는 대신 시스템 라이브러리를 넣는다.
# APT_MIRROR 로 사내 미러를 지정할 수 있다 (예: http://mirror.corp/debian).
ARG APT_MIRROR=""
RUN set -eux; \
    if [ -n "${APT_MIRROR}" ]; then \
        find /etc/apt -name '*.sources' -o -name '*.list' \
          | xargs -r sed -i "s|https\?://deb.debian.org/debian|${APT_MIRROR}|g"; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends libgl1 libglib2.0-0 ca-certificates; \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONHASHSEED=0 \
    # Ultralytics 가 홈 디렉터리에 설정을 쓰려다 실패하는 것을 막는다
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    MPLBACKEND=Agg \
    # 스레드 수가 흔들리면 CPU latency 측정이 재현되지 않는다
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /workspace

# ---------------------------------------------------------------------------
# 1) torch 를 독립 레이어로 먼저. 소스가 바뀌어도 가장 무거운 레이어를 재사용한다.
# ---------------------------------------------------------------------------
ARG TORCH_VERSION=2.8.0
ARG TORCHVISION_VERSION=0.23.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN set -eux; \
    if [ "${TORCH_INDEX_URL}" = "pypi" ]; then \
        pip install "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}"; \
    else \
        pip install --index-url "${TORCH_INDEX_URL}" \
            "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}"; \
    fi; \
    python -c "import torch, torchvision; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

# ---------------------------------------------------------------------------
# 2) 벤더링된 서드파티. --no-deps 편집 설치라 pyproject 의 sahi==0.12.2 핀을 충족하며
#    PyPI 에서 다시 받지 않는다.
# ---------------------------------------------------------------------------
COPY external/sahi /workspace/external/sahi
RUN pip install --no-deps -e /workspace/external/sahi

COPY external/upsample-anything /workspace/external/upsample-anything
RUN pip install --no-deps -e /workspace/external/upsample-anything

# ---------------------------------------------------------------------------
# 3) 프로젝트 본체
# ---------------------------------------------------------------------------
COPY pyproject.toml README.md LICENSE MANIFEST.in /workspace/
COPY src /workspace/src
RUN pip install -e ".[dev]" \
 && python -c "import ua_sahi_mal, sahi, ultralytics, cv2; print('imports ok')"

COPY configs /workspace/configs
COPY scripts /workspace/scripts
COPY tests /workspace/tests
COPY docs /workspace/docs

# 데이터셋·산출물은 이미지에 굽지 않고 마운트한다 (docker/docker-compose.yml).
VOLUME ["/workspace/datasets", "/workspace/runs", "/workspace/output"]

# 기본 동작: 저장소 자체 검증. 외부 데이터도 GPU 도 필요 없다.
CMD ["bash", "/workspace/scripts/verify_env.sh"]
