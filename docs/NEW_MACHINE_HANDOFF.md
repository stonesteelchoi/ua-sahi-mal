# 새 GPU 컴퓨터 이전 및 LLM 인수인계

점검일: 2026-09-07. 점검 기준은 GitHub `main`의 `f81e6c6cb4b552955d5306baab6a4fac42c53924`이다. 새 장비에서 실행을 검증한 보고서가 아니라, 해당 커밋의 문서·코드·자산 목록을 대조한 이전 안내다.

## 1. 판정

**코드와 과거 연구 자산은 GitHub + Google Drive로 복원할 수 있다. 하지만 현재 v3 논문 작업을 설치 직후 완성된 GPU 학습 명령으로 이어갈 수는 없다.**

| 목적 | 현재 가능한 범위 | 추가 작업 |
|---|---|---|
| 환경·합성 smoke | Git clone과 설치로 가능, 데이터/GPU 불필요 | 새 장비에서 실제 실행 확인 |
| MaleVis 분류 | CUDA 사용 가능 시 `cuda:0` 선택 | 해당 해상도 데이터 복원, GPU 계산 확인, 새 결과 경로 |
| v1 YOLO | CLI에 장치 지정 경로 존재 | 실제 실험의 이미지·ROI·split·검증된 malware checkpoint 필요 |
| v2 BIG2015 A/B/C | 파생 코퍼스 복원 가능 | A/B 학습·추론은 CPU 전용. GPU 이식과 validity-mask 감사 조치가 먼저 |
| v3 현재 논문 | 계획·초안·계약 보존 | PEAtlas, gold corpus, 비교군 adapter, 평가 구현과 G0–G6 gate |
| DeepReflect | 연결 안내만 존재, 상태 `NOT_RUN` | 별도 checkout·환경·도구 접근·데이터·adapter 필요 |

v2의 [`training.py`](../src/ua_sahi_mal/evidence/training.py)는 CPU 실행을 명시하며, 모델과 입력을 CUDA로 이동하지 않는다. [`classifiers.py`](../src/ua_sahi_mal/evidence/classifiers.py)의 checkpoint 로딩도 CPU이며, [`cli.py`](../src/ua_sahi_mal/evidence/cli.py)에 `train/run --device`는 없다. GPU 설치만으로 이 경로가 빨라진다고 보고하면 안 된다.

## 2. 새 장비 설치

아래 주 경로는 **Windows x64 + NVIDIA GPU**를 전제로 한다. OS/GPU가 다르면 아래 명령을 그대로 실행하지 말고 해당 환경의 설치 경로를 먼저 결정한다. 장비 구매 기준이나 검증된 최소 VRAM 요구량은 아직 없다.

Git, Python 3.10–3.12 중 하나(예: 3.12), GPU를 지원하는 NVIDIA 드라이버를 준비한다. 기존 `.venv`는 복사하지 않는다. 드라이브 문자는 예시이며 여유 공간이 있는 로컬 디스크를 선택한다.

```powershell
nvidia-smi
python --version
git clone https://github.com/stonesteelchoi/ua-sahi-mal.git D:\research\ua-sahi-mal-yolo
Set-Location D:\research\ua-sahi-mal-yolo
git rev-parse HEAD
git status --short --branch
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -TorchIndex cu128
if ($LASTEXITCODE -ne 0) { throw "설치 실패: 위 오류부터 해결" }
```

`python`이 다른 버전을 가리키면 `setup.ps1 -PythonExecutable '실제 Python 3.12의 python.exe 절대 경로'`를 추가한다. CPU setup을 먼저 실행할 필요가 없다. 이미 CPU 환경을 만들었다면 설치 후 아래 CUDA 검사를 반드시 수행하고, CPU wheel이 남았다면 올바른 인덱스에서 torch/torchvision을 명시적으로 재설치한다.

프로젝트는 torch 2.8.0 / torchvision 0.23.0 / cu128을 사용한다. 이 조합은 [PyTorch 공식 이전 버전 안내](https://pytorch.org/get-started/previous-versions/)에 있다. 드라이버 호환성은 실제 GPU와 [NVIDIA CUDA 12.8 릴리스 안내](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html)를 함께 확인한다. `nvidia-smi`의 CUDA 표시는 현재 Python 환경의 torch CUDA 버전과 같은 의미가 아니다.

### GPU를 실제로 계산에 쓰는지 확인

`doctor --strict`는 CPU 환경에서도 통과할 수 있다. 따라서 다음 CUDA 계산 검사를 별도로 통과해야 GPU 설치 완료다.

```powershell
$RunTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$CheckDir = "runs/migration-$RunTag"
New-Item -ItemType Directory -Path $CheckDir -Force | Out-Null
nvidia-smi | Out-File "$CheckDir/nvidia-smi.txt" -Encoding utf8
.\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw "의존성 충돌" }
.\.venv\Scripts\python.exe -m ua_sahi_mal doctor --strict
if ($LASTEXITCODE -ne 0) { throw "doctor 실패" }
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); x=torch.randn(256,256,device='cuda'); y=x@x; torch.cuda.synchronize(); assert torch.isfinite(y).all().item(); print('CUDA computation OK', y.device)"
if ($LASTEXITCODE -ne 0) { throw "GPU 계산 실패: 장기 학습을 시작하지 마세요" }
.\.venv\Scripts\python.exe -m ua_sahi_mal smoke
if ($LASTEXITCODE -ne 0) { throw "기존 파이프라인 smoke 실패" }
.\.venv\Scripts\python.exe -m ua_sahi_mal.evidence smoke --out "$CheckDir/evidence-smoke"
if ($LASTEXITCODE -ne 0) { throw "evidence smoke 실패" }
.\.venv\Scripts\python.exe -m pip freeze | Out-File "$CheckDir/pip-freeze.txt" -Encoding utf8
```

그 뒤 README의 ruff, pytest, 저장소 안전 검사, 논문 수치 감사, build를 한 번 실행하고 결과를 기록한다. 합성 smoke나 GPU 행렬 연산 통과는 실제 학습 성능 검증이 아니다. 선택한 연구선에서 작은 실제 학습·추론 실행도 확인해야 한다.

Linux에서는 Python 가상환경 안에서 같은 torch/torchvision cu128 조합과 `requirements.txt`를 설치하고 검증한다. OpenCV 시스템 라이브러리는 [`docker/Dockerfile`](../docker/Dockerfile)을 참고한다. 현재 Docker 기본값은 CPU다. GPU 컨테이너는 호스트 드라이버·GPU 런타임 설정과 컨테이너 내 CUDA 계산 확인이 추가로 필요하다. 과거 Docker 안내의 `cu124` 예시를 torch 2.8.0 설정에 그대로 적용하지 않는다.

## 3. 저장 공간을 아끼는 다운로드 순서

[파일별 다운로드](artifacts/FILES.md)와 [manifest](artifacts/manifest.json)를 기준으로 **선택한 연구선에 필요한 파일만** 받는다. Google Drive는 제한된 공유 상태이므로 새 브라우저에서 접근 가능한 계정으로 로그인한다. 디렉터리 전체 다운로드는 필요하지 않다.

| 목적 | 먼저 받을 파일 | 다운로드/복원 데이터 크기 |
|---|---|---|
| 코드 검증·v3 계약 구현 시작 | 없음 | 코드·가상환경·출력 공간만 필요 |
| 기존 BIG2015 v2 코퍼스 | `ua-sahi-mal-big2015-20260905-part01-of10.zip`부터 10개 전부 | ZIP 합계 889,513,688 B, 원래 파일 합계 893,571,411 B |
| 기존 실행 결과·MaleVis checkpoint 확인 | `ua-sahi-mal-runs-20260905.zip` | ZIP 25,132,810 B, 원래 파일 합계 79,430,272 B |
| MaleVis 재학습 | 사용할 해상도의 MaleVis ZIP | 224: 약 1.74GB / 300: 약 3.14GB. 해제 크기는 다운로드 후 ZIP 목록으로 확인 |
| 기존 캐시까지 복원 | uasahi-cache 독립 ZIP 18개 | ZIP 약 0.75GB, 원래 파일 합계 약 1.72GB. 필요할 때만 복원 |
| 코퍼스 재생성·원본 대조 | `malware-classification.zip` | 37,885,110,014 B. 초기 이전에는 생략 가능 |

위 크기는 자산 manifest의 기록이다. GB는 10진 단위이며 파일시스템 할당량·가상환경·패키지 다운로드·새 체크포인트는 별도다. 모든 필요한 ZIP의 압축 크기와 해제 크기를 더한 값에 실행 여유 공간을 확보한다. 새 장비의 정확한 필요 공간은 선택한 작업과 아카이브 목록을 보고 결정한다.

새로 만든 독립 ZIP 31개는 내부에 `datasets/`, `runs/` 등의 경로가 있으므로 **각 ZIP을 저장소 루트에** 푼다. `partNN-ofNN.zip`을 이어 붙이지 않는다. MaleVis의 기존 ZIP은 내부 최상위 폴더를 먼저 확인해서 `datasets/malevis_train_val_224x224/` 또는 `datasets/malevis_train_val_300x300/` 아래 중복 폴더가 생기지 않게 복원한다.

각 다운로드는 파일 크기와 `Get-FileHash -Algorithm SHA256`을 manifest와 비교한다. MaleVis 기존 ZIP은 기준 SHA가 제공되지 않았으므로 ZIP 무결성·파일 수·라벨 구조를 별도 확인하고 동일성 미검증 범위를 남긴다. 새 보관본도 업로드 당시에는 원격 크기까지만 확인했으므로 **새 장비의 다운로드 후 해시 대조가 중요하다**.

### BIG2015를 원본에서 다시 만들 때만

원본 ZIP 안의 `train.7z`는 18,810,691,091 B다. ZIP과 train.7z를 동시에 보관하면 약 56.7GB가 필요하며, 그 위에 scratch·래스터·환경·출력 공간이 더 필요하다. `train.7z` 전체를 풀면 문서상 약 198GB다. 초기 이전에 전체 압축 해제를 하지 않는다.

재생성이 필요하면 원본 ZIP에서 `train.7z`와 `trainLabels.csv`만 선택 추출하고 [`big2015_prepare_corpus.py`](../scripts/big2015_prepare_corpus.py)의 folder 단위 재개 경로를 사용한다. `--scratch`는 전용 빈 디렉터리로 지정한다. 이 스크립트는 해당 하위 scratch를 지운다. `--state`, `--rasters`, `--manifest`를 동일한 새 코퍼스에 맞추고, 실제 최대 scratch 사용량을 측정한다. 이전 코퍼스의 완료 state만 복사해 새 출력을 건너뛰게 만들지 않는다.

복원한 v2 코퍼스는 `datasets/big2015/manifest.json`과 `datasets/big2015/rasters/`가 기준이다. manifest의 각 `samples[].raster_path`가 존재하고 PNG의 LA 채널(validity alpha)과 내장 `uasm_*` 메타데이터를 읽을 수 있는지 확인한다. `data/big2015/`와 혼용하지 않는다. 복원된 PNG·메타데이터로 충분한 작업에 원본을 다시 내려받지 않는다.

## 4. 현재 남은 연구 작업

기본 목표는 [`RESEARCH_PLAN_v3.md`](../paper/plan/RESEARCH_PLAN_v3.md)의 v3다. BIG2015/MaleVis 보관본은 v3의 raw PE gold corpus나 검증된 v3 checkpoint를 대신하지 않는다.

1. **P0/G0:** 데이터·도구·분석가 접근 가능성 및 DeepReflect 실행 조건을 기록한다. 외부 접근이 없어도 합성 좌표 계약 작업은 진행할 수 있다.
2. **P1/G1:** PEAtlas의 file offset/RVA/VA 매핑, half-open interval union, 유효 mask, 실패 상태와 round-trip 테스트부터 구현한다. 아직 존재하지 않는 v3 CLI 명령을 만들어서 실행 안내로 쓰지 않는다.
3. **P2A/P2B:** source-grounded gold feasibility와 별도 환경의 DeepReflect 재현을 진행한다. Binary Ninja 등은 현재 setup에 설치되지 않는다. 자세한 고정 버전·출력 계약은 [`external/deepreflect/README.md`](../external/deepreflect/README.md)에 있다.
4. **P3 이후:** split·지표·예산을 동결하고 최소 비교군, 학습기, selector, 검증 Pareto, 최종 test 순으로 진행한다. v1/v2 수치와 v3 gold 결과를 합치지 않는다.

사용자가 v2 재실험을 명시적으로 선택하면 먼저 [`RESEARCH_AUDIT_2026-09-04.md`](RESEARCH_AUDIT_2026-09-04.md)를 읽는다. 점검 커밋에서 `SampleStore.get()`은 아직 `data, _ = corpus.load_entry_bytes(...)`로 validity mask를 버린다. class-weight sum과 안전한 checkpoint 로딩 수정이 존재한다고 해서 감사 항목 전체가 해결된 것은 아니다. mask-aware 표현·대조군·실제 누적 deletion 등을 검토하고 protocol 버전을 구분한 뒤 새 checkpoint로 재학습한다.

v2에 GPU 지원을 추가할 때는 모델뿐 아니라 입력·target·class weight·추론·캐시·checkpoint 로딩 경로를 함께 처리한다. CPU fallback과 기존 checkpoint 호환성, CPU/GPU 결과 허용 오차, GPU synchronization을 포함한 timing을 검증한다. AMP나 batch 변경으로 실험 조건이 바뀌면 별도 기록한다. C_text는 NumPy 경로이므로 같은 방식의 CUDA 이동 대상이 아니다.

## 5. 다른 LLM에 전달할 프롬프트

아래 전체를 새 장비에서 저장소에 접근할 수 있는 LLM 에이전트에게 전달한다.

```text
너는 UA-SAHI-MAL 연구 프로젝트를 새 GPU 컴퓨터에서 이어받는 담당자다.
저장소: https://github.com/stonesteelchoi/ua-sahi-mal
이전 점검 기준: f81e6c6cb4b552955d5306baab6a4fac42c53924 (2026-09-07).
최신 main의 실제 커밋과 차이를 먼저 확인하라. 이 프롬프트보다 최신 코드가 있으면
검증한 변경을 반영하되, 이전 결과를 새 실행 결과로 간주하지 마라.

목적: 기존 데스크톱의 디스크 부족을 피해 새 장비에서 환경과 필요한 자산을 복원하고,
현재 v3 논문 작업을 이어간다. 사용자가 v2/MaleVis 재실험을 따로 선택하지 않으면
v3가 기본 목표다. 계획만 답하지 말고 가능한 설치·검증·구현을 진행하라.

먼저 읽을 문서:
- README.md, docs/NEW_MACHINE_HANDOFF.md
- docs/artifacts/README.md, FILES.md, manifest.json
- paper/README.md, paper/plan/RESEARCH_PLAN_v3.md
- paper/decisions/ADR-001-deepreflect-baseline.md
- paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md
- external/deepreflect/README.md
- docs/RESEARCH_AUDIT_2026-09-04.md
- SECURITY.md, THIRD_PARTY.md
저장소의 AGENTS.md가 있으면 해당 범위 지시도 확인하라.

1. OS, GPU 모델/VRAM, 드라이버, RAM, 작업 디스크 여유 공간, Python, Git,
   Drive 접근을 확인하고 환경 보고서를 작성하라. 도구로 확인할 수 없는 정보만
   사용자에게 물어라. 기존 .venv와 개인 인증 정보를 복사하지 마라.
2. Windows NVIDIA면 setup.ps1 -TorchIndex cu128을 사용하라.
   Python 3.10–3.12, torch 2.8.0, torchvision 0.23.0이 기준이다.
   다른 OS/GPU라면 실제 지원 경로를 검증하라. doctor --strict 통과만으로
   GPU 성공이라 하지 말고 CUDA에서 tensor 연산을 실행해 synchronize까지 확인하라.
   ruff/pytest/두 smoke/안전 검사/수치 감사/build 결과를 기록하라.
3. 용량을 아끼기 위해 첫 환경 검증에는 데이터를 받지 마라.
   v2 코퍼스가 필요한 경우 BIG2015 파생 ZIP 10개(총 약 0.89GB)를 먼저 복원하라.
   과거 결과에는 runs ZIP을, MaleVis에는 해당 해상도 ZIP만 추가하라.
   37.9GB 원본, 캐시 18개, 검증용 가중치는 필요성을 확인한 경우에만 받는다.
   Drive 파일 목록과 manifest가 권위 있는 다운로드 목록이다.
   독립 ZIP은 저장소 루트에 각각 풀고 결합하지 마라. 해시·크기와 실제 입력 경로를
   검사하라. 다운로드 후 검증/새 장비 검증 전 기존 장비 원본을 삭제하지 마라.
4. 중요한 미완료 상태:
   - v3는 pre-results다. PEAtlas, gold corpus, adapter/평가를 완성해야 한다.
   - DeepReflect는 별도 legacy 환경/도구 접근이 필요하며 현재 NOT_RUN이다.
   - v2 A/B는 현재 CPU 전용이고 train/run --device 옵션이 없다.
     CUDA 설치만으로 v2가 GPU를 사용한다고 주장하지 마라.
   - v2 SampleStore의 validity mask 누락이 남아 있다. 감사 수정과 protocol 구분,
     재학습 전 기존 결과를 최종 논문 근거로 사용하지 마라.
   - MaleVis는 CUDA 자동 선택, YOLO는 장치 지정 경로가 있다.
   - yolo11n.pt는 일반 초기 가중치, 검증용 ZIP은 합성 실험용이며 v3 모델이 아니다.
5. v3 계획의 P0/P1부터 진행하라. 승인된 데이터·라이선스·분석가 접근이 필요하면
   정확히 어떤 입력이 필요한지 기록하고, 독립적으로 가능한 합성 mapper/계약 구현을
   계속하라. 실제 악성 샘플 실행이나 일반 개발 환경의 동적 분석은 하지 않는다.
   test gold로 튜닝하지 말고 silver·gold·합성·과거 결과를 구분하라.
6. 장기 실험은 실제 코드에 있는 CLI와 옵션을 --help로 확인하고 짧은 pilot 후 시작하라.
   새 GPU의 VRAM·시간·디스크 증가량을 측정해 batch와 예산을 결정하라.
   새 실행 디렉터리에 commit, seed, split/hash, config, 환경, 로그, checkpoint,
   중단/재개 가능 여부를 기록하라. resume 구현이 없으면 가능하다고 말하지 마라.
7. 사용량 도구가 있으면 시작 시와 큰 단계 전후에 계정 한도를 확인·보고하라.
   정확한 토큰을 모르면 추정치를 정확한 값처럼 말하지 마라. 한도에 접근하기 전에
   완료/미완료/현재 명령/출력 위치/다음 실행 명령을 인수인계 파일에 저장하라.
8. 완료 보고에는 실제로 확인한 환경, 받은 자산/생략한 자산, 실행 결과,
   GPU 사용 경로, 수정 사항, 남은 연구 gate, 다음 명령을 구분해서 적어라.
```

## 6. 이전 완료 판정

- 새 장비 clone 커밋과 작업 트리 상태를 기록했다.
- 선택한 환경 설치, CUDA 계산(해당 장비), 코드 검증을 통과했다.
- 선택한 연구선의 필수 자산을 검증하고 경로를 연결했다.
- 짧은 실제 실행 또는 v3 합성 계약 테스트를 실행해 로그를 남겼다.
- 남은 연구 gate와 다음 명령을 새 장비에 저장했다.

이 조건이 충족되기 전에는 기존 데스크톱 자료의 삭제를 이전 완료의 일부로 수행하지 않는다. 새 장비 설치·실험은 이 문서 작성 시점에 아직 실행하지 않았다.
