#
# UA-SAHI-MAL 재현 환경 (CPU 기본).
#
# 빌드:
#   docker build -f docker/Dockerfile -t ua-sahi-mal:cpu .
#
# GPU 로 빌드하려면 CUDA 휠 인덱스를 넘긴다:
#   docker build -f docker/Dockerfile \
#     --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124 \
#     -t ua-sahi-mal:cu124 .
#
# 사내 프록시가 download.pytorch.org 를 막는 환경에서는 PyPI 로 폴백한다:
#   docker build -f docker/Dockerfile --build-arg TORCH_INDEX_URL=pypi -t ua-sahi-mal:cpu .
#   (PyPI 의 linux/amd64 torch 휠은 CUDA 런타임을 포함하므로 이미지가 커진다.)

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS base

# opencv-python(headless 아님) 이 요구하는 런타임 라이브러리.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Ultralytics 가 홈 디렉터리에 쓰려다 실패하지 않도록 고정
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    MPLBACKEND=Agg \
    # 재현성: BLAS 스레드 수를 고정하지 않으면 CPU latency 측정이 흔들린다
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /workspace

# ---------------------------------------------------------------------------
# 1) torch 를 먼저, 독립 레이어로. 소스가 바뀌어도 이 레이어는 재사용된다.
# ---------------------------------------------------------------------------
ARG TORCH_VERSION=2.8.0
ARG TORCHVISION_VERSION=0.23.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN if [ "$TORCH_INDEX_URL" = "pypi" ]; then \
        pip install "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" ; \
    else \
        pip install --index-url "${TORCH_INDEX_URL}" \
            "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" ; \
    fi \
 && python -c "import torch, torchvision; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"

# ---------------------------------------------------------------------------
# 2) 벤더링된 SAHI 를 먼저 설치 (pyproject 의 sahi==0.12.2 핀과 같은 버전).
#    requirements.txt 의 `-e ./external/sahi` 와 동일한 소스를 쓴다.
# ---------------------------------------------------------------------------
COPY external/sahi /workspace/external/sahi
RUN pip install --no-deps -e /workspace/external/sahi

# Upsample Anything 공식 구현 (external/upsample-anything).
COPY external/upsample-anything /workspace/external/upsample-anything
RUN pip install --no-deps -e /workspace/external/upsample-anything

# ---------------------------------------------------------------------------
# 3) 프로젝트 본체
# ---------------------------------------------------------------------------
COPY pyproject.toml README.md LICENSE MANIFEST.in /workspace/
COPY src /workspace/src
RUN pip install -e ".[dev]"

COPY configs /workspace/configs
COPY scripts /workspace/scripts
COPY tests /workspace/tests
COPY docs /workspace/docs

# 데이터셋·산출물은 이미지에 굽지 않고 마운트한다(docker/docker-compose.yml 참조).
VOLUME ["/workspace/datasets", "/workspace/runs", "/workspace/output"]

# 기본 동작: 저장소 자체 검증(테스트 + 합성 스모크). 외부 데이터·GPU 불필요.
CMD ["bash", "-lc", "pytest && python -m ua_sahi_mal smoke --output-dir /workspace/runs/smoke"]
