# 연구 방향 재설계

[비전 / XAI] "악성코드 시각화와 설명 가능성"
앞서 고민하셨던 '정적 PE 이미지화 및 위치화(Localization)' 연구의 가장 훌륭한 타협안입니다. 복잡한 Bounding Box 정답을 만드는 대신 XAI(설명 가능한 AI)로 우회합니다.

타겟 데이터셋: phoenixml/Maldataset-2021

데이터 특징: 원본 악성코드를 224x224 RGB 이미지(PNG)로 이미 변환해 둔 데이터셋입니다. 28개의 악성 패밀리로 분류되어 있어 전처리가 전혀 필요 없습니다.

논문 아이디어 (가제): Beyond Accuracy: Explainable Malware Family Classification using Structure-Aware XAI (정확도를 넘어: 구조 인지형 XAI를 활용한 설명 가능한 악성코드 패밀리 분류)

역설계 스토리라인:

"기존의 비전 기반 악성코드 탐지 논문들은 정확도(Accuracy)만 자랑할 뿐, 대체 이미지의 어느 부분을 보고 악성이라 판단했는지 설명하지 못하는 블랙박스다"라고 비판합니다.

ResNet이나 ViT로 패밀리 분류기를 학습시킨 후, Grad-CAM이나 Attention Map을 추출해 붉은색 히트맵을 띄웁니다.

"랜섬웨어는 주로 이미지의 특정 부분(예: 리소스 섹션)에서 붉게 반응한다"며, 정답 박스(Ground Truth) 없이 모델의 판단 근거를 보여주는 것만으로 시각적으로 훌륭한 논문이 됩니다.

장점: 시각적인 결과물(컬러풀한 히트맵)이 나와서 포스터 발표나 논문의 Figure로 쓸 때 심사위원의 눈길을 사로잡기 가장 좋습니다.


# UA-SAHI-MAL

**정적 악성코드 분석을 위한 예산 제한 지역화 연구**

파일 단위 라벨에서 출발해, 분석가가 검토할 함수·basic block·바이트 구간의 우선순위를 찾습니다.

[![검증](https://github.com/stonesteelchoi/ua-sahi-mal/actions/workflows/verify.yml/badge.svg)](https://github.com/stonesteelchoi/ua-sahi-mal/actions/workflows/verify.yml)
[![Python 3.10–3.12](https://img.shields.io/badge/Python-3.10%E2%80%933.12-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Project license: MIT](https://img.shields.io/badge/Project_license-MIT-green)](LICENSE)
[![Research: v3 pre-results](https://img.shields.io/badge/Research-v3_pre--results-orange)](paper/README.md)

[빠른 시작](#quickstart) · [현재 연구 상태](#research-status) · [가중치·데이터셋](#artifacts) · [실험 재현](#reproduction) · [결과와 검증](#results) · [문서 지도](#documentation)

> **현재 논문은 v3 설계·구현 준비 단계(pre-results)입니다.**
>
> DeepReflect를 주 정적 지역화 비교군으로 채택했습니다. PE 좌표 매핑, gold corpus, baseline adapter와 분석가 평가를 완성하기 전이므로 성능 향상이나 분석 시간 절감은 아직 주장하지 않습니다. 기존 DECODE/YOLO, MaleVis, BIG2015 결과는 별도 과거 연구선으로 보존합니다.

<a id="quickstart"></a>

## 빠른 시작

**다른 컴퓨터로 이전한다면:** [새 GPU 컴퓨터 설치·최소 다운로드·LLM 인수인계](docs/NEW_MACHINE_HANDOFF.md)를 먼저 확인하십시오. 기존 BIG2015 v2 A/B 학습·추론은 CPU 전용이며, 현재 v3는 추가 구현이 필요한 단계입니다.

**Python 3.10–3.12와 Git**이 필요합니다. 합성 smoke test는 실제 데이터셋·가중치·GPU 없이 실행할 수 있으며, 최초 의존성 설치에는 네트워크가 필요합니다. 아래는 Windows PowerShell 기준입니다.

```powershell
git clone https://github.com/stonesteelchoi/ua-sahi-mal.git ua-sahi-mal-yolo
Set-Location ua-sahi-mal-yolo
powershell -ExecutionPolicy Bypass -File scripts/setup_cpu.ps1

# 기존 탐지 파이프라인의 데이터 준비 → 라우팅 → 병합을 합성 데이터로 검사
.\.venv\Scripts\python.exe -m ua_sahi_mal smoke

# v2 근거 구간 프로토콜을 알려진 판정 규칙의 합성 모델로 검사
.\.venv\Scripts\python.exe -m ua_sahi_mal.evidence smoke --out runs/smoke-evidence
```

첫 번째 smoke test 결과는 `runs/smoke/<timestamp>/`에 저장됩니다. smoke 통과는 구현 경로가 연결된다는 뜻이며, 실제 악성코드의 지역화 성능을 검증한 결과는 아닙니다. 출력 경로가 이미 있으면 새 이름을 사용하십시오.

<details>
<summary><strong>GPU 설치, 환경 진단, 실험 설정 검증</strong></summary>

CUDA 환경에서는 CPU 설치 대신 다음을 실행합니다. 설치 스크립트는 PyTorch `2.8.0`, torchvision `0.23.0`, Ultralytics `8.4.67`과 개발 도구를 설치합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -TorchIndex cu128
.\.venv\Scripts\python.exe -m ua_sahi_mal doctor --strict
.\.venv\Scripts\python.exe -m ua_sahi_mal --help

# 이 설정은 보존된 v1 DECODE/YOLO 실험 계약입니다.
.\.venv\Scripts\python.exe -m ua_sahi_mal validate-config `
  --config configs/experiments/decode_primary.example.yaml
```

호환 PyTorch/CUDA와 장치별 동작을 확인한 뒤 학습하십시오. Linux·Docker의 설치 및 검증 경로는 [Docker 재현 안내](docker/README.md)를 참고합니다. `external/sahi`와 `external/upsample-anything`은 현재 Git에 포함된 일반 소스 디렉터리입니다.

</details>

<a id="research-status"></a>

## 현재 연구 상태

| 연구선 | 질문과 평가 단위 | 현재 상태 | 시작 문서 |
|---|---|---|---|
| **v3 · 현재 논문** | 고정된 검토·연산 예산에서 검증된 PE 악성 구성요소를 얼마나 회수하는가 | **Pre-results**. 좌표 매핑·gold 데이터·비교군 평가 준비 | [논문 허브](paper/README.md) · [연구 계획](paper/plan/RESEARCH_PLAN_v3.md) |
| v2 · BIG2015 근거 구간 | 어떤 바이트 구간이 파일의 계열 판정을 지지하는가 | 1차 결과는 **잠정**. 감사에서 확인된 문제를 반영해 재학습·재실행 필요 | [프로토콜](docs/EVIDENCE_PROTOCOL.md) · [감사](docs/RESEARCH_AUDIT_2026-09-04.md) |
| v1 · DECODE/YOLO | coarse map으로 SAHI tile 예산을 줄일 수 있는가 | 인코더·학습·추론·합성 검증 경로 구현. 전체 전략의 실제 성능 검증은 별도 | [실행 안내](docs/DECODE_PIPELINE.md) |
| MaleVis · 전이 분류 | 정적 이미지에서 해상도와 MC dropout이 분류·보정에 미치는 영향 | 224/300 해상도, 3개 seed의 집계·timing 근거 보존 | [결과 근거](docs/results/README.md) |

### v3에서 고정한 원칙

- **기준 좌표:** 원본 파일의 half-open byte interval union, 즉 `[start, end)` 구간들의 합집합. 함수·basic block·mask·bbox는 이 좌표에 연결되는 표현입니다.
- **주 비교군:** DeepReflect. random/uniform/entropy, attribution, MIL, capa/YARA, exhaustive 및 gold 학습 데이터가 있을 때 supervised 기준선을 같은 예산·표본 단위로 비교합니다.
- **주 지표:** top-K 함수에서의 악성 구성요소 recall, 검토 바이트 비율별 gold byte recall, 첫 구성요소를 찾는 데 드는 시간·함수 수, 전체 지연시간과 분석 가능 비율.
- **라벨 구분:** 합성 위치 정답, 규칙 기반 silver, 독립 검토 gold, 실제 분석가 평가를 분리합니다. 파일 분류 정확도나 Grad-CAM pseudo-box를 구성요소 정답으로 취급하지 않습니다.

DECODE는 동적 API-call 이미지와 pseudo-box를 다루므로 v3의 직접 수치 비교에서 제외하고 관련 연구로 유지합니다. 선택 이유와 재현 조건은 [DeepReflect baseline 결정 기록](paper/decisions/ADR-001-deepreflect-baseline.md)에 있습니다.

```text
v3에서 구현·검증할 흐름

승인된 정적 PE + 파일 라벨
    → 파일 offset ↔ RVA ↔ 함수/basic block 매핑
    → coarse scoring + 예산 제한 후보 선택·정밀화
    → 순위가 있는 byte-interval union
    → 독립 gold / DeepReflect 및 비교군 / 동일 비용 평가
```

<a id="artifacts"></a>

## 가중치와 데이터셋

가중치와 데이터셋은 `.gitignore` 대상입니다. Git에는 코드·설정·문서와 공개 가능한 집계 근거를 보존하고, 대용량 파일은 별도 Google Drive 보관본으로 연결합니다.

<!-- ASSET_DOWNLOADS_START -->
**가중치·파생 데이터 ZIP 31개와 BIG2015 원본 ZIP 업로드·크기 검증 완료.**

[전체 보관 폴더](https://drive.google.com/drive/folders/1nQWy27-OQmfamBgIvc2822QDXn2_iL4C) · [파일별 다운로드](docs/artifacts/FILES.md) · [복원 안내](docs/artifacts/README.md) · [SHA-256 목록](docs/artifacts/manifest.json)

| 자산 | Drive | 용도·복원 위치 |
|---|---|---|
| MaleVis 224 × 224 · 1.74GB | [기존 ZIP](https://drive.google.com/file/d/1K-AfcaQjoV808AtPZiV7ELPlVpTfmKZo/view?usp=drivesdk) | `datasets/malevis_train_val_224x224/` |
| MaleVis 300 × 300 · 3.14GB | [기존 ZIP](https://drive.google.com/file/d/1oz0I2X-jCPUc78m0d8sgzMEPEiOW8Nc2/view?usp=drivesdk) | `datasets/malevis_train_val_300x300/` |
| 실험 결과·MaleVis 가중치 · 25.1MB ZIP | [다운로드](https://drive.google.com/file/d/1M-LRKgEcpZl3124dcjR4yVNQloNrDLko/view?usp=drivesdk) | `runs/` 전체. MaleVis checkpoint 7개 포함 |
| YOLO11n 초기 가중치 · 5.61MB | [다운로드](https://drive.google.com/file/d/1DWwiQQ23g4cP0s-wb7f-DQhWFZ9MKWm-/view?usp=drivesdk) | 저장소 루트. 일반 사전학습 가중치 |
| 합성 검증용 YOLO 가중치 · 19.7MB ZIP | [다운로드](https://drive.google.com/file/d/1ep4K6FUbcZ_r9pHrsEMB6stOajngd5dU/view?usp=drivesdk) | `.codex-review/`의 원래 경로. checkpoint 4개 |
| BIG2015 파생 이미지 · 독립 ZIP 10개 | [파일 목록](docs/artifacts/FILES.md) | `datasets/big2015/` |
| BIG2015 정적 샘플 · 9.59MB ZIP | [다운로드](https://drive.google.com/file/d/1PAN6ta6oiK6lW295MQ3HMBlDMeZhN50f/view?usp=drivesdk) | `datasets/big2015_sample/` |
| 실험 캐시 · 독립 ZIP 18개 | [파일 목록](docs/artifacts/FILES.md) | `datasets/uasahi_cache/` |
| BIG2015 원본 · 37.9GB | [원본 ZIP 다운로드](https://drive.google.com/file/d/1MgoxMX2OHh3Y6L8Mi4VP40xNL5p496Cy/view?usp=drivesdk) | `datasets/malware-classification.zip`. 내부에 `train.7z` 포함 |

> Drive 링크는 기존의 제한된 접근 권한을 유지합니다. MaleVis ZIP 두 개는 기존 보관본을 연결했으며, 새 ZIP은 SHA-256·CRC를 기록하고 업로드 후 크기를 확인했습니다. **파생 데이터의 독립 ZIP은 모두 저장소 루트에 풀면 되고, BIG2015 원본은 단일 ZIP으로 받습니다.** 가중치는 과거 실험·합성 검증용이며 v3 검증 모델이 아닙니다.
<!-- ASSET_DOWNLOADS_END -->

<a id="reproduction"></a>

## 실험 재현

원하는 연구선을 선택한 뒤 해당 실행 안내를 따르십시오. v1/v2 실행 명령과 산출물을 v3 실험 결과로 합치지 않습니다.

| 목적 | 진입점 | 입력·출력 및 주의할 해석 |
|---|---|---|
| 빠른 구현 확인 | 위의 두 [smoke test](#quickstart) | 합성 데이터와 stub/fake detector. 실제 가중치 불필요 |
| v3 논문 설계·구현 | [연구 계획 v3](paper/plan/RESEARCH_PLAN_v3.md) | PEAtlas, DeepReflect adapter, gold corpus 등의 실행 조건·gate 확인 |
| MaleVis 전이 분류 | [아래 상세 명령](#malevis-reproduction) · [설정](configs/experiments/malevis_decode_transfer.yaml) | 해상도 공통 split, seed 42·43·44, deterministic/MC dropout 분류 |
| BIG2015 v2 근거 구간 | [EVIDENCE_PROTOCOL](docs/EVIDENCE_PROTOCOL.md) | `python -m ua_sahi_mal.evidence`의 prepare/synth/train/run 경로 |
| v1 DECODE형 이미지 탐지 | [DECODE_PIPELINE](docs/DECODE_PIPELINE.md) · [아래 상세 명령](#detector-reproduction) | 승인된 PNG/JPEG·ROI JSON·split map·검증된 checkpoint 필요 |
| 기존 논문 보고 수치 검증 | `python scripts/audit_paper_numbers.py` | Git의 [집계 근거 사본](docs/results/README.md)으로 표와 파생 수치 대조 |

<details>
<summary><strong>전체 환경 검증과 Docker</strong></summary>

```powershell
.\.venv\Scripts\python.exe scripts/check_repository_safety.py
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ua_sahi_mal doctor --strict
.\.venv\Scripts\python.exe scripts/audit_paper_numbers.py
.\.venv\Scripts\python.exe -m build
```

Docker에서는 다음을 사용합니다.

```bash
make build      # 컨테이너 이미지 빌드
make verify     # lint, tests, 합성 smoke, 논문 수치 감사
make offline    # 네트워크를 끊고 재검증
```

Windows orchestration은 `scripts/setup_docker.ps1`, 컨테이너 없는 공통 검증은 `bash scripts/verify_env.sh` 또는 `make check`입니다. 레지스트리·PyTorch·APT 미러 설정과 검증 한계는 [Docker README](docker/README.md), 보존된 실행 근거는 [환경 검증 기록](docs/verification/README.md)을 참고하십시오.

현재 [verify 워크플로](.github/workflows/verify.yml)는 Ubuntu의 Python 3.10·3.12 네이티브 검증, Docker 빌드·실행·오프라인 검증, 저장소 안전 검사를 정의합니다. 실제 실행 상태는 [GitHub Actions](https://github.com/stonesteelchoi/ua-sahi-mal/actions/workflows/verify.yml)에서 확인합니다.

</details>

<a id="results"></a>

## 결과와 검증 범위

| 근거 | 확인할 수 있는 것 | 해석의 한계 |
|---|---|---|
| [v3 논문 초안](paper/draft/README.md) | 현재 설계와 남은 실험, `[TBD]` 결과 슬롯 | 제출 가능한 완성 논문이나 측정 성과가 아님 |
| [MaleVis·BIG2015 집계 근거](docs/results/README.md) | 보존된 분류·보정·forward timing 및 경계 복원 실험의 보고 수치 | 집계 감사는 재학습이나 개별 예측에서의 지표 계산 검증과 구분 |
| [v2 첫 실행 결과](docs/results/evidence/README.md) | 사전등록 기준 5개 중 4개 미달인 당시 관측 | validity mask·class weighting·random control 감사 후 재실행 전까지 잠정 결과 |
| [환경 검증 기록](docs/verification/README.md) | 해당 시점의 환경·lint·테스트·합성 smoke 실행 근거 | 최신 코드의 전체 실험 성공이나 과학적 성능을 보증하지 않음 |

MaleVis의 timing은 batch의 모델 forward 시간을 batch size로 나눈 값입니다. 데이터 로딩·디코딩을 포함한 단일 요청의 end-to-end latency와 구분해 읽어야 합니다.

<a id="documentation"></a>

## 문서 지도와 저장소 구조

| 읽고 싶은 내용 | 문서 |
|---|---|
| 현재 논문 전체 맥락 | [논문 허브](paper/README.md) · [v3 계획](paper/plan/RESEARCH_PLAN_v3.md) · [초안 재검토](paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md) |
| 비교군 선정·선행연구 | [ADR-001](paper/decisions/ADR-001-deepreflect-baseline.md) · [참고문헌](paper/references/README.md) |
| 데이터 계약·실행 경로 | [데이터 계약](docs/DATA_CONTRACT.md) · [v1 탐지](docs/DECODE_PIPELINE.md) · [v2 근거 구간](docs/EVIDENCE_PROTOCOL.md) |
| 결과·재현·감사 | [근거 데이터](docs/results/README.md) · [연구 감사](docs/RESEARCH_AUDIT_2026-09-04.md) · [환경 검증](docs/verification/README.md) |
| 전체 문서·연구 이력 | [문서 인덱스](docs/README.md) · [원격탐사 원형](docs/legacy_remote_sensing/README.md) |
| 보안·외부 코드 | [SECURITY](SECURITY.md) · [THIRD_PARTY](THIRD_PARTY.md) · [LICENSE](LICENSE) |

```text
ua-sahi-mal-yolo/
├─ paper/                  현재 v3 계획 · 결정 기록 · 초안 · 참고문헌
├─ src/ua_sahi_mal/         인코딩 · 데이터 계약 · YOLO/SAHI · CLI
│  └─ evidence/            v2 바이트 근거 구간 프로토콜
├─ scripts/                설치 · 데이터 감사 · 학습 · 집계 · 검증
├─ configs/experiments/    버전이 고정된 실험 설정
├─ tests/                  단위·통합·합성 검증
├─ docs/                   실행 안내 · 역사적 연구 계획 · 결과 근거
├─ external/               SAHI·UPA 소스와 DeepReflect 연결 안내
├─ docker/                 CPU 컨테이너 재현 환경
├─ output/paper/           보존된 이전 논문 초고와 생성 스크립트
├─ datasets/               로컬 데이터셋 (Git 제외)
└─ runs/                   실행 결과·가중치 (Git 제외)
```

## 보존된 연구선의 상세 실행 안내

아래는 기존 연구선의 재현 경로입니다. 상세 명령의 `C:\secure-research\...`와 Python 실행 파일 경로는 자신의 승인된 저장 위치·가상환경 경로로 바꾸십시오.

<details>
<summary><strong>v1/v2 연구 배경 · 입력과 라벨 · 기존 구현 상태</strong></summary>

## 보존된 v1/v2 연구선

> **[2026-09-03] 연구 질문이 바뀌었습니다 — v2**
>
> "이미지화된 코드에서 악성코드의 **위치**를 판별한다"는 v1의 목표는 성립하지 않는 문제였습니다. BIG2015 검체는 대부분 파일 전체가 악성이라 "위치"의 지시 대상이 없고, 공개 벤치마크 어디에도 바이트 수준 경계 라벨이 없습니다.
>
> v2는 질문을 바꿉니다: **어느 바이트 구간이 계열 판정의 근거인가.** 마스킹 후 재추론이라는 연산으로 정의되고 검증되며, 사람 주석을 요구하지 않습니다. 순환 평가는 탐색에 참여하지 않은 독립 모델과 이미지를 보지 않는 모델로 끊습니다.
>
> **1차 실행 결과는 부정적이지만 현재 잠정 결과입니다.** 사전등록 기준 5개 중 4개 미달 — 개별 4 KB 블록이 계열 판정을 거의 움직이지 않았습니다(블록당 ΔNLL 0.0056). 다만 2026-09-04 감사에서 `.bytes` validity mask 누락, A의 class-weight 상쇄, random-control overlap 가능성을 확인했으므로 “근거가 국소화되지 않는다”는 결론은 수정 코드로 재학습·재실행하기 전에는 논문에 사용할 수 없습니다. 자세한 수치: [`docs/results/evidence/README.md`](docs/results/evidence/README.md), 감사 판정: [`docs/RESEARCH_AUDIT_2026-09-04.md`](docs/RESEARCH_AUDIT_2026-09-04.md)
>
> - 설계·사전등록: [`docs/RESEARCH_PLAN_v2.md`](docs/RESEARCH_PLAN_v2.md)
> - 실행 안내: [`docs/EVIDENCE_PROTOCOL.md`](docs/EVIDENCE_PROTOCOL.md)
> - 선행연구 점검: [`docs/LITERATURE_REVIEW.md`](docs/LITERATURE_REVIEW.md)
> - 당시 DECODE 검토 기록: [`docs/DECODE_BASELINE_PLAN.md`](docs/DECODE_BASELINE_PLAN.md) — v3 baseline 결정으로 대체됨
> - 구현: `src/ua_sahi_mal/evidence/` · 진입점 `python -m ua_sahi_mal.evidence`
>
> **아래 v1 문서는 재현용으로 보존합니다.** 완성된 논문 초고(부정 결과 2건)와 285건 수치 감사가 그 코드에 걸려 있어, 지우면 재현 경로가 사라집니다. v1 자산과 v2 파이프라인은 같은 저장소에서 독립적으로 돌아갑니다.

이 저장소는 기존 위성영상용 `UA-SAHI-YOLO` 프로토타입을 새 논문 주제에 맞게 전환한 연구 구현입니다. 현재는 승인된 정적 DECODE PNG/JPEG와 ROI JSON을 가져와 YOLO11을 학습하고, 같은 full-image forward pass의 P3/P4/P5 pre-NMS score로 coarse map을 만든 뒤 JBU/UPA와 예산 제한 SAHI를 실행하는 경로까지 연결되어 있습니다.

> 이 저장소는 방어적 연구 도구입니다. 실제 악성코드의 검색·다운로드·압축 해제·실행·샌드박스 제어를 자동화하지 않습니다. 주 DECODE workflow의 입력은 별도 승인 환경이 이미 생성한 PNG/JPEG, ROI JSON, split JSON입니다. 원본 PE/APK/DEX와 API 키는 Git에 넣지 않으며, 파생 이미지도 민감 데이터로 취급합니다.

## 연구 가설과 사전 성공 기준

주 비교군은 모든 슬라이스를 추론하는 `Full SAHI-100`입니다. `B=0.5` 예산의 UA-SAHI-MAL이 다음 세 기준을 모두 만족하는지 검증합니다.

- `AP_S` 하락: Full SAHI 대비 1.5 AP point 이내
- 검출기 처리 이미지 수: 40% 이상 감소
- end-to-end p95 latency: 25% 이상 감소

`AP50`, `mAP50:95`, Tile Recall, peak VRAM, detector invocation/image count를 함께 보고합니다. 현재 README는 성능 향상을 주장하지 않습니다. 위 기준은 실험 전에 고정한 기각/채택 게이트입니다.

## 데이터와 라벨의 의미

지원하는 입력 계약은 네 가지입니다. 논문의 주 데이터 경로는 `existing-image`이며 나머지는 표현 방식 ablation 또는 합성 검증용입니다.

| 모드 | 입력 | 이미지 변환 | 원본 좌표 |
|---|---|---|---|
| `existing-image` | 이미 안전하게 생성된 DECODE/API 이미지 | 크기 변경 없이 RGB로 정규화 | pixel index 또는 직접 bbox |
| `opcode-3gram-rgb` | `AA 48 FF ...` 형식의 정제된 hex token 텍스트 | 연속 3개 opcode를 sliding RGB pixel로 변환 | opcode offset |
| `word16-rgb` | 승인된 정적 바이트 | big-endian 2-byte word를 `(high, low, high XOR low)` RGB pixel로 변환 | byte offset |
| `raw-rgb` | 로컬 바이너리의 바이트 | 비중첩 3 byte를 RGB pixel로 변환 | byte offset |

`word16-rgb`와 `raw-rgb`는 데이터를 실행하지 않고 읽기만 하지만, 실제 악성 실행 파일을 이 개발 workspace로 반입하라는 뜻이 아닙니다. 조직 정책이 승인한 비실행 정적 export 또는 합성 데이터에만 사용하십시오. `opcode-3gram-rgb`는 objdump나 PE를 직접 실행하지 않고, 별도 격리 단계에서 추출한 엄격한 2자리 hex token만 받습니다. 모든 모드는 고정 크기로 resize하지 않아 원본 순서와 좌표를 보존하며, `word16-rgb`의 홀수 마지막 바이트는 오른쪽에 0을 패딩합니다.

별도 `encode-behavior-report` 명령은 **이미 생성된 정적 CAPE-shaped JSON**의 `behavior.processes[].calls[]`에서 `category`와 `api` 이름만 읽어 512×512의 DECODE형 4분할 이미지를 만듭니다. `process | registry / network | filesystem` 순서이며 call arguments와 payload는 읽어 픽셀에 넣지 않습니다. 이 구현은 `decode-static-behavior-v1`로 버전된 안전한 전처리 변형이지, DECODE 공개 코드의 모든 중복 제거·padding·tiling 규칙을 byte-for-byte 재현한 것이 아닙니다. 출력은 이후 `existing-image` 입력으로 사용하고, ROI 라벨은 별도로 검증해 연결해야 합니다.

```powershell
$Python = "C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe"
& $Python -m ua_sahi_mal encode-behavior-report `
  --source C:\secure-research\static-reports\sample.json `
  --output C:\secure-research\decode-images\sample.png `
  --allow-sensitive-output
```

생성 PNG와 기본 `sample.png.json` metadata에는 source SHA-256, quadrant 순서, API call 수, 잘림·반복 문자 수와 민감도 marker가 기록됩니다. API 순서 자체가 행위 정보를 드러낼 수 있으므로 승인된 비-Git 위치에만 저장하십시오.

객체 라벨은 다음을 구분합니다.

- `human_verified`: 분석가가 검토한 박스
- `bayesian_gradcam`: 분류 teacher의 Bayesian Grad-CAM에서 얻은 pseudo-box
- `source_range`: 독립 분석 도구가 제공한 byte/opcode 구간
- `synthetic`: 테스트 전용 박스

Grad-CAM 박스는 실제 악성 코드의 정답 경계가 아니라 “분류 판단에 기여한 영역”입니다. 같은 teacher로 만든 pseudo-label만으로 최종 AP를 평가하면 순환 평가가 되므로, 논문의 주 지역화 결론은 사람 또는 독립 도구가 검증한 test subset을 사용해야 합니다.

기본 detector class는 `malicious_evidence` 하나입니다. DECODE 초기 ROI의 `category_name`은 family target에서 만들어지므로 `roi-family` baseline에는 쓸 수 있지만, 그 박스를 `process/network/registry/filesystem` 의미로 자동 재해석할 근거는 없습니다. 또한 DECODE 최종 object dataset은 family 하나를 object class 하나로 쓰는 것보다, family 안에서 시각적으로 유사한 ROI를 feature-region ID로 grouping하고 family를 supercategory로 유지합니다. 따라서 strict DECODE 재현은 별도 feature-cluster adapter가 필요하며 현재의 `roi-family`와 동일하다고 주장하지 않습니다.

자세한 스키마는 [데이터 계약](docs/DATA_CONTRACT.md), 정적 DECODE 전체 명령은 [DECODE 파이프라인 runbook](docs/DECODE_PIPELINE.md), 연구 순서와 위험은 [구현 계획](docs/RESEARCH_PLAN.md)을 참고하십시오.

## 현재 구현 상태

구현됨:

- 안전한 `existing-image`, `word16-rgb`, `raw-rgb`, sliding `opcode-3gram-rgb` 인코더
- 정적 CAPE-shaped JSON의 API 이름만 사용하는 버전형 DECODE형 4분할 이미지 변환기
- byte/opcode 구간을 행 경계에 맞는 COCO bbox들로 정확히 변환
- 버전형 JSON manifest, SHA-256 검증, 중복 source/family split 누수 차단
- PNG, YOLO label, COCO JSON, `dataset.yaml`, annotation provenance 동시 생성
- 정적 DECODE ROI JSON 어댑터: basename 격리, 이미지 형식/경계/해시/중복/group split 검증
- 기본 `class-agnostic`과 비교용 `roi-family` class policy
- `FullImage`, `FullSAHI`, `BudgetedSAHI` 공통 전략 인터페이스와 class-aware GreedyNMM
- Tile Recall, detector-call reduction, latency reduction, 3중 성공 게이트
- YOLO11 train/evaluate 및 detector metric JSON/CSV 내보내기
- restricted safe-load 체크포인트 SHA-256/class/task/parameter 검증과 COCO checkpoint 거부
- 같은 full-image forward pass의 YOLO11 P3/P4/P5 pre-NMS probability/entropy coarse map
- deterministic CPU anisotropic JBU, bilinear, official UPA adapter 선택
- guard·coverage·fixed-budget tile routing과 선택적 SAHI 단일 이미지 추론
- 정답 JSON이 있을 때 class-aware IoU, TP/FP/FN, precision/recall/F1 자동 평가
- 실행 입력·환경·checkpoint metadata를 담는 `pipeline_inputs.json`
- 미측정 값을 명시하는 논문 표 JSON/CSV 템플릿과 성공 게이트 계산
- 프로세스 수준 outbound socket 차단과 Ultralytics plot 비활성화로 offline fail-closed 실행
- 실제 악성 샘플·모델·비밀정보의 Git 추적을 막는 CI 검사
- 외부 데이터와 GPU가 필요 없는 합성 end-to-end smoke 및 DECODE형 fixture generator
- Windows용 `scripts/run_decode_pipeline.ps1` 전체 orchestration
- MaleVis 224/300 전수 해시 감사, 공통 paired split, compact DECODE 전이 분류, 3-seed/MC-dropout 집계 경로

후속 단계에서 구현/검증할 항목:

- 실제 DECODE feature-grouping category/supercategory를 그대로 보존하는 strict-reproduction adapter
- 사람 검증용 annotation review workflow
- dataset-level COCO `AP_S`, end-to-end p50/p95, peak VRAM 자동 측정 harness
- 공식 UPA test-time optimization의 실제 GPU 비용/정확도 실험
- EfficientDet portability adapter
- 실제 DECODE/KISA 데이터의 학습·평가 및 Pareto report

`predict --coarse-mode dense`가 현재 권장 경로입니다. 설치된 Ultralytics head 형식이 지원되지 않으면 조용히 다른 방법으로 바뀌지 않고 실패합니다. `--coarse-mode boxes`는 post-NMS box+texture를 사용하는 명시적 호환성 baseline입니다. 로컬 JBU는 official Upsample Anything과 동일한 알고리즘이 아니므로 두 결과를 합쳐 보고하지 않습니다.

## 전체 흐름

```text
격리 저장소의 로컬 입력
  ├─ DECODE/API visualization ───────────────┐
  ├─ sanitized opcode tokens → sliding RGB ─┤
  └─ bytes → non-overlapping RGB ───────────┘
                         ↓
      SHA-256 + family/source split validation
                         ↓
   source range/direct bbox → COCO + YOLO + provenance
                         ↓
              YOLO11 baseline train/evaluate
                         ↓
 Full Image / Full SAHI / Bilinear-50 / JBU-50 / UA-SAHI-MAL
                         ↓
       AP_S · AP50 · Tile Recall · calls · p95 latency · VRAM
```

</details>

<a id="malevis-reproduction"></a>

<details>
<summary><strong>MaleVis: 데이터 감사 → 공통 split → 3-seed 학습 → timing → 결과 집계</strong></summary>

## MaleVis에서 재현하는 DECODE 전이 분류 실험

`scripts/run_malevis_experiment.py`는 DECODE의 핵심 아이디어인 시각 표현 학습, dropout 기반 Bayesian 추론, center loss를 MaleVis의 **정적 악성코드 이미지 분류**에 맞게 옮긴 별도 실험 경로입니다. 공개 DECODE 구현은 동적 CAPE API 행동 이미지와 Grad-CAM/EfficientDet 지역화를 사용하지만, MaleVis에는 family 라벨만 있고 bbox가 없습니다. 따라서 이 실험은 strict DECODE 재현이나 객체 지역화 실험이 아니며 `AP`, `AP_S`, Tile Recall, SAHI 성능을 산출하거나 주장하지 않습니다.

실험은 다음 누수 방지 계약을 적용합니다.

- 224×224와 300×300에서 공통으로 존재하는 sample ID만 사용하고, 두 해상도에 동일한 split을 적용
- 두 해상도의 SHA-256 중복 관계를 합쳐 exact duplicate component 단위로 한 샘플만 유지
- 원본 `train`에서만 내부 검증 집합을 계층 추출하고, 원본 `val`은 최종 test로 한 번만 평가
- 해상도마다 seed 42·43·44를 독립 실행하고, deterministic 및 MC dropout 5회 추론을 함께 보고
- accuracy, macro/weighted F1, macro precision/recall, top-5, NLL, Brier, ECE, confusion matrix, class별 지표와 계층 bootstrap 95% CI 저장

아래 명령은 현재 저장소의 `datasets/malevis_train_val_224x224`와 `datasets/malevis_train_val_300x300`을 사용합니다. 감사 및 학습 명령은 기존 데이터 파일을 수정하지 않으며, 출력 디렉터리가 이미 있으면 덮어쓰지 않고 중단합니다.

```powershell
$Python = "C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe"
$MaleVisRun = "runs\malevis\reproduction"
$PairedManifest = "$MaleVisRun\malevis-paired-split-v1.json"

& $Python scripts\audit_malevis_dataset.py `
  --dataset-root datasets\malevis_train_val_224x224 `
  --image-size 224 `
  --output "$MaleVisRun\malevis-224.audit.json"

& $Python scripts\audit_malevis_dataset.py `
  --dataset-root datasets\malevis_train_val_300x300 `
  --image-size 300 `
  --output "$MaleVisRun\malevis-300.audit.json"

& $Python scripts\build_malevis_paired_manifest.py `
  --root-224 datasets\malevis_train_val_224x224 `
  --root-300 datasets\malevis_train_val_300x300 `
  --output $PairedManifest
```

대표 seed 42에서만 run 내부 진단 timing을 측정하고 나머지 seed는 `--skip-timing`으로 학습·정확도 평가만 수행합니다. CPU에서는 한 실행에 수십 분이 걸릴 수 있습니다. 아래 예시는 순차 실행이라 메모리 경쟁이 없고, CUDA가 있으면 코드가 자동으로 단일 GPU를 사용합니다.

```powershell
foreach ($ImageSize in 224, 300) {
  $DatasetRoot = "datasets\malevis_train_val_${ImageSize}x${ImageSize}"
  foreach ($Seed in 42, 43, 44) {
    $RunDir = "$MaleVisRun\${ImageSize}-seed${Seed}"
    $TimingOption = if ($Seed -eq 42) { @() } else { @("--skip-timing") }
    & $Python scripts\run_malevis_experiment.py `
      --config configs\experiments\malevis_decode_transfer.yaml `
      --dataset-root $DatasetRoot `
      --paired-manifest $PairedManifest `
      --image-size $ImageSize `
      --seed $Seed `
      --output-dir $RunDir `
      @TimingOption
    if ($LASTEXITCODE -ne 0) { throw "MaleVis run failed: $RunDir" }
  }
}
```

논문용 timing은 모든 학습이 끝난 뒤 두 seed-42 체크포인트를 새 프로세스에서 순차 측정합니다. 다른 학습 프로세스를 동시에 실행하지 마십시오.

```powershell
& $Python scripts\benchmark_malevis_checkpoints.py `
  --run-dir "$MaleVisRun\224-seed42" `
  --run-dir "$MaleVisRun\300-seed42" `
  --device cpu `
  --output "$MaleVisRun\isolated-timing.json"
```

세 seed와 두 해상도의 결과를 한 파일로 집계합니다.

```powershell
& $Python scripts\aggregate_malevis_results.py `
  --run-dir "$MaleVisRun\224-seed42" `
  --run-dir "$MaleVisRun\224-seed43" `
  --run-dir "$MaleVisRun\224-seed44" `
  --run-dir "$MaleVisRun\300-seed42" `
  --run-dir "$MaleVisRun\300-seed43" `
  --run-dir "$MaleVisRun\300-seed44" `
  --output-dir "$MaleVisRun\aggregate"

& $Python scripts\create_malevis_paper_figure.py `
  --aggregate "$MaleVisRun\aggregate\aggregate.json" `
  --isolated-timing "$MaleVisRun\isolated-timing.json" `
  --output "$MaleVisRun\aggregate\paper-overview.png"
```

각 실행의 `summary.json`은 설정·환경·데이터 fingerprint·split count·최적 epoch·최종 test 지표를, `predictions.*.csv`는 샘플별 확률과 불확실성을 보존합니다. `best_model.pt`, 학습 이력, confusion matrix CSV/PNG, class별 CSV/JSON도 함께 생성됩니다. timing의 p50/p95는 batch를 로드한 뒤의 **모델 forward 시간을 batch size로 나눈 값**이며, 단일 요청의 데이터 디코딩까지 포함한 end-to-end latency로 해석하면 안 됩니다.

</details>

<a id="detector-reproduction"></a>

<details>
<summary><strong>v1 DECODE/YOLO: fixture → manifest → 학습·평가 → 예산 제한 추론</strong></summary>

DECODE형 2×2 행동 영상, ROI JSON, group-aware split map과 직접 YOLO fixture를 모두 만드는 더 큰 무해 fixture도 제공합니다. 모든 내용은 `SYNTH_*`와 정상 API 이름으로 된 ASCII 문자열입니다.

```powershell
$Python = "C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe"
& $Python scripts\generate_safe_decode_fixture.py `
  --output C:\secure-research\fixtures\decode-safe-v1 `
  --train 80 --val 20 --test 20 --seed 260826
```

실제 승인된 DECODE PNG/ROI JSON이 준비되면 전체 Windows 파이프라인을 한 명령으로 실행할 수 있습니다. `WorkRoot`는 비어 있거나 존재하지 않아야 하며 어떤 결과도 덮어쓰지 않습니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_decode_pipeline.ps1 `
  -RepoRoot C:\dev\ua-sahi-mal-yolo `
  -PythonExe C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe `
  -Annotations @(
    "C:\secure-research\decode\roi\dropper_final.json",
    "C:\secure-research\decode\roi\ransomware_final.json"
  ) `
  -ImagesRoot C:\secure-research\decode\images `
  -SplitMap C:\secure-research\decode\splits.json `
  -WorkRoot C:\secure-research\decode\ua-sahi-run-001 `
  -BaseModel C:\secure-research\models\yolo11n.pt `
  -TeacherModel decode-vgg16-bgc-v1 `
  -AnnotationVersion decode-bgc-roi-v1 `
  -DatasetRevision decode-static-v1 `
  -ClassPolicy class-agnostic `
  -Epochs 100 -BatchSize 16 -ImageSize 640 -Device cuda:0 `
  -CoarseMode dense -Upsampler jbu -Budget 0.5
```

먼저 정적 import/prepare만 검증하려면 `-SkipTraining`을 추가합니다. 스크립트는 네트워크 비활성 환경변수에 더해 Python 프로세스에서 non-loopback socket을 차단합니다. 예상치 못한 asset/model fetch는 자동 진행되지 않고 오류로 중단됩니다.

전체 실행은 `manifest.json`, prepared dataset, `best.pt`, checkpoint metadata, detector test JSON/CSV, 예측 산출물, `pipeline_inputs.json`과 함께 모든 셀이 아직 `not_measured`인 `paper-table.input.json`을 만듭니다. 검출기 단일 평가 값을 `AP_S`·전체 latency·VRAM 값으로 자동 대체하지 않으므로 전략별 실측 후 해당 표를 채워야 합니다.

## 데이터 manifest

템플릿을 먼저 생성합니다.

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal manifest-template `
  --output C:\secure-research\decode-manifest.json
```

핵심 형식은 다음과 같습니다. `end`는 exclusive offset입니다.

```json
{
  "version": 1,
  "name": "decode-research-v1",
  "categories": [
    {"id": 1, "name": "ransomware_evidence"}
  ],
  "samples": [
    {
      "sample_id": "decode-train-0001",
      "source": "C:/secure-research/images/sample.png",
      "sha256": "<64 lowercase hex characters>",
      "split": "train",
      "family_id": "family-group-a",
      "encoding": "existing-image",
      "annotations": [
        {
          "category_id": 1,
          "bbox_xywh": [120, 80, 34, 28],
          "annotation_source": "bayesian_gradcam",
          "annotation_version": "bgcam-v1",
          "teacher_model": "checkpoint-sha256",
          "source_score": 0.87,
          "verified": false
        }
      ]
    }
  ]
}
```

위 JSON은 필드 설명을 위한 축약 예입니다. 실제 `prepare-data` 입력에는 최소 한 개의 `train` 샘플과 한 개의 `val` 샘플이 있어야 하며, 최종 평가를 수행하려면 독립적인 `test` split도 추가해야 합니다.

검증과 변환:

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal validate-data `
  --manifest C:\secure-research\decode-manifest.json

.\.venv\Scripts\python.exe -m ua_sahi_mal prepare-data `
  --manifest C:\secure-research\decode-manifest.json `
  --output-dir C:\secure-research\prepared\decode-v1 `
  --allow-sensitive-output
```

출력 구조:

```text
prepared/decode-v1/
├─ images/{train,val,test}/*.png
├─ labels/{train,val,test}/*.txt
├─ annotations/{train,val,test}.json
├─ annotation_provenance.jsonl
├─ prepared_manifest.json
└─ dataset.yaml
```

`prepared_manifest.json`에는 원본 절대 경로 대신 파일명·SHA-256·encoding coordinate metadata가 기록됩니다. `dataset.yaml`은 자신의 위치를 dataset root로 사용하므로 준비된 디렉터리를 통째로 이동할 수 있습니다. 생성 PNG에는 민감도 marker가 들어가며, 이 파일을 강제로 Git에 추가하면 repository safety check가 실패합니다.

## YOLO11 기준선

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal train `
  --data C:\secure-research\prepared\decode-v1\dataset.yaml `
  --model C:\secure-research\models\yolo11n.pt `
  --epochs 100 `
  --image-size 640 `
  --seed 42

.\.venv\Scripts\python.exe -m ua_sahi_mal validate-checkpoint `
  --model runs\train\ua-sahi-mal-yolo11\weights\best.pt `
  --data C:\secure-research\prepared\decode-v1\dataset.yaml `
  --dataset-revision decode-v1 `
  --output runs\train\checkpoint.metadata.json

.\.venv\Scripts\python.exe -m ua_sahi_mal evaluate `
  --data C:\secure-research\prepared\decode-v1\dataset.yaml `
  --model runs\train\ua-sahi-mal-yolo11\weights\best.pt `
  --split test `
  --dataset-revision decode-v1 `
  --metrics-json runs\val\detector-test.metrics.json `
  --metrics-csv runs\val\detector-test.metrics.csv
```

최종 test split은 설정 선택에 사용하지 않습니다. 원본 source group을 먼저 split한 뒤 teacher와 detector를 학습해야 합니다. `validate-checkpoint`는 `.pt`를 restricted safe-load하여 dataset class order를 정확히 대조하고 COCO `person/car/airplane/truck` checkpoint를 거부합니다. 기본 `evaluate`가 내보내는 값은 detector-only summary이며 `AP_S`, Tile Recall, detector work, end-to-end p95, peak VRAM은 별도 전략 실험에서 측정해야 합니다.

## Dense coarse + 선택적 UA-SAHI 추론

준비된 이미지와 검증된 malware-specific detector checkpoint에 대해 dense router를 실행합니다. `predict` 자체도 generic COCO checkpoint를 거부합니다.

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal predict `
  --source C:\secure-research\prepared\decode-v1\images\test\sample.png `
  --model C:\secure-research\weights\best.pt `
  --data C:\secure-research\prepared\decode-v1\dataset.yaml `
  --dataset-revision decode-v1 `
  --output-dir C:\secure-research\results `
  --device cuda:0 `
  --coarse-mode dense `
  --upsampler jbu `
  --slice-height 400 `
  --slice-width 400 `
  --budget 0.5 `
  --probability-weight 0.8 `
  --entropy-weight 0.2 `
  --ground-truth C:\secure-research\prepared\decode-v1\annotations\test.json `
  --iou-threshold 0.5 `
  --tile-recall-coverage 0.5
```

산출물에는 `annotated.png`, `predictions.json`, `routing_heatmap.png`, `selected_tiles.png`, `summary.json`이 들어갑니다. `summary.json`은 모든 candidate tile의 bbox/score/guard/selection과 dense probability·entropy 범위를 보존합니다. 정답을 주면 `localization_evaluation.json/.csv`와 routing Tile Recall도 생성되며 class match, confidence, IoU, FP/FN, selected/candidate tile 수, detector images/invocations를 기록합니다. detector count에는 full-image coarse pass 1회를 포함합니다. 공식 UPA는 이미지마다 test-time optimization을 수행해 느리고 큰 VRAM을 사용할 수 있으므로 `bilinear`와 `jbu`를 먼저 측정하고, `upa`의 전체 시간과 VRAM을 별도 행으로 보고하십시오.

논문 표를 먼저 동결하고 실제 측정값만 채우려면 다음 명령을 사용합니다. 모든 초기 셀은 `null + not_measured`이며 0으로 위장되지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal paper-table-template `
  --experiment-id decode-yolo11-primary-v1 `
  --dataset-revision decode-v1 `
  --checkpoint-sha256 <best.pt-sha256> `
  --output runs\paper\table.input.json

# table.input.json에 실제 측정 셀만 status=measured/value=<number>로 기록한 뒤:
.\.venv\Scripts\python.exe -m ua_sahi_mal compile-paper-table `
  --input runs\paper\table.input.json `
  --output-json runs\paper\table.compiled.json `
  --output-csv runs\paper\table.compiled.csv
```

</details>

<details>
<summary><strong>기존 논문 초고와 수치 감사 경로</strong></summary>

## 논문 초고

`output/paper/` 에 전자공학회논문지 정규논문 양식의 초고와 생성 스크립트가 있다.

| 파일 | 내용 |
|---|---|
| `UA-SAHI-MAL_논문초고_v2.docx` | 초고 본문 (5쪽). 실험 1 = MaleVis MC dropout, 실험 2 = BIG2015 경계 복원 |
| `build_paper.js` | 초고 생성 스크립트 (`node output/paper/build_paper.js`) |
| `figures/fig1_accuracy_calibration.png` | macro F1 과 ECE |
| `figures/fig2_latency.png` | 구성별 이미지당 순전파 지연시간 |
| `figures/fig3_boundary.png` | BIG2015 경계 복원 오차와 가이드 판별력 |

실험 1의 수치는 `runs/malevis/aggregate-20260829/` 와 `runs/malevis/isolated-timing-20260829.json`
에서 가져온 것으로 새로 실행하지 않았다. 실험 2(BIG2015 경계 복원)는 당시 실행한 것이며
`scripts/big2015_p0a.py` 와 `scripts/big2015_boundary_experiment.py` 로 재현된다. 그 수치가 근거 데이터로부터 올바르게 도출됐는지는
`python scripts/audit_paper_numbers.py` 가 285건의 검사로 대조한다(근거 사본은 [docs/results/](docs/results/)).
논문을 고치면 감사 스크립트의 기대값 상수도 같이 고쳐야 하며, 그러지 않으면 검증이 실패한다. 저자·소속·투고 번호는 자리표시자이므로 투고 전에
채워야 한다. 기존 `output/documents/malevis-decode-transfer-paper-ko.docx` 는 별도 문서이며
이 초고가 대체하지 않는다.

</details>

## 데이터·연구 안전

- 원본 악성 샘플은 격리된 로컬 데이터 저장소에만 둡니다.
- 이 코드의 encoder는 입력을 읽을 뿐 실행·import·동적 분석하지 않습니다.
- `encode-behavior-report`는 기존 JSON을 변환할 뿐 sandbox를 시작·제어하거나 샘플을 실행하지 않으며 call arguments/payload를 렌더링하지 않습니다.
- `raw-rgb`와 sliding opcode RGB는 원본 스트림을 전부 또는 대부분 복원할 수 있습니다. 생성 PNG도 원본과 같은 보안 등급으로 취급하고 공개 저장소에 올리지 않습니다.
- 동적 분석이 필요하면 별도 sandbox에서 수행하고 여기에는 안전한 report/image만 전달합니다.
- SHA-256 중복과 `family_id`가 split을 가로지르면 preparation을 중단합니다.
- 체크포인트, raw samples, archives, `.env`, generated dataset은 `.gitignore`와 CI에서 차단합니다.
- Grad-CAM pseudo-box와 human-verified box의 지표를 분리해 보고합니다.

자세한 신고·처리 원칙은 [SECURITY.md](SECURITY.md)를 확인하십시오.

## 라이선스와 외부 프로젝트

프로젝트 코드의 라이선스는 [MIT](LICENSE)입니다. 외부 코드의 라이선스·사용 조건은 각 프로젝트에 따릅니다.

| 구성요소 | 고정 버전·참조 | 저장소 내 형태·조건 |
|---|---|---|
| SAHI | `0.12.2` | `external/sahi`에 포함된 소스 · MIT |
| Upsample Anything | `39251463a8bb352785c063c3c3f941f1dcdf4c51` | `external/upsample-anything` 소스. 이 저장소 반입 허가 기록은 [THIRD_PARTY](THIRD_PARTY.md) 참고 |
| Ultralytics | `8.4.67` | Python 의존성 · AGPL-3.0 또는 별도 enterprise license |
| DeepReflect | `4358a7e8ef7fc5951360094867dca852ed23712e` | 소스 미포함. [격리 baseline 안내](external/deepreflect/README.md)만 보존 · upstream GPL-3.0 |

UPA의 직접 허가는 이 저장소의 소스 반입에 대한 것이며, 일반적인 downstream 재배포·수정 라이선스로 해석하지 않습니다. 빌드된 wheel에는 UPA 소스가 포함되지 않으므로 `--upsampler upa`는 해당 소스가 있는 checkout에서 사용합니다. 로컬 JBU와 공식 UPA는 다른 알고리즘이며 결과를 합쳐 보고하지 않습니다.

자세한 출처·허가·버전 기록은 [THIRD_PARTY.md](THIRD_PARTY.md), 현재 논문의 출처는 [paper/references](paper/references/README.md)에 있습니다.
