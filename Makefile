# UA-SAHI-MAL — 자주 쓰는 명령 모음.
# Windows 에서는 scripts/setup_docker.ps1 을 쓰십시오.

COMPOSE := docker compose -f docker/docker-compose.yml
PYTHON  ?= python

.PHONY: help build verify offline shell lint test smoke check clean-verify

help:
	@echo "build          컨테이너 이미지 빌드"
	@echo "verify         컨테이너 안에서 검증 (ruff + pytest + 합성 스모크)"
	@echo "offline        네트워크를 끊고 같은 검증"
	@echo "shell          컨테이너 대화형 셸"
	@echo "check          컨테이너 없이 호스트에서 같은 검증"
	@echo ""
	@echo "프록시가 막힌 환경이면 .env 에 BASE_IMAGE / TORCH_INDEX_URL / APT_MIRROR 를 지정하십시오."

build:
	$(COMPOSE) build

verify:
	$(COMPOSE) run --rm verify

offline:
	$(COMPOSE) run --rm offline

shell:
	$(COMPOSE) run --rm shell

lint:
	ruff check src scripts tests

test:
	$(PYTHON) -m pytest

smoke:
	$(PYTHON) -m ua_sahi_mal smoke --output-dir runs/smoke-$$(date -u +%Y%m%dT%H%M%SZ)

check:
	bash scripts/verify_env.sh

clean-verify:
	rm -rf runs/verification
