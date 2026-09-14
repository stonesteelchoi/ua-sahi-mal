# KISA-XAI-v5 독립형 LLM 인수인계 프롬프트

점검일: 2026-09-14
저장소: <https://github.com/stonesteelchoi/ua-sahi-mal>
활성 브랜치: `research/kisa-xai-v5`
반드시 포함되어야 하는 기준 커밋: `4b1f6ee` (`docs: define KISA XAI v5 research plan`)

아래 `인수인계 프롬프트` 전체를 새 LLM 작업에 전달한다. 새 LLM이 로컬 파일과
터미널을 사용할 수 있다면 설명만 작성하게 두지 말고, 검증 가능한 범위에서 환경 구축과
P0 데이터 접근 감사를 실제로 진행하게 한다.

---

## 인수인계 프롬프트

```text
당신은 보안 ML 연구 저장소 UA-SAHI-MAL의 KISA-XAI-v5 연구선을 인수받는다.
이 프롬프트만으로 작업을 시작하되, 저장소의 실제 파일과 Git 상태를 권위 있는 최신
근거로 사용하라. 계획만 제시하고 멈추지 말고, 현재 장비와 접근 권한으로 가능한 설치,
검증, 데이터 접근 감사, 구현을 순차적으로 수행하라. 도구로 확인할 수 없는 정보만
사용자에게 질문하라.

0. 연구 목표와 현재 상태

- 국문 제목: 정확도를 넘어 설명의 신뢰성으로: 정적 PE 악성코드 탐지기의 구조 정합
  XAI와 교차연도 외부 평가
- 영문 제목: Beyond Accuracy: Structure-Mapped XAI with Cross-Year External
  Evaluation for Static PE Malware Detection
- 과제는 Windows PE 정상/악성 이진 탐지다. malware-family 분류가 아니다.
- 입력은 원본 PE 바이트를 1×224×224로 변환한 interval-binned-v1 표현이다.
- 주 모델은 ResNet-18, 주 XAI는 Grad-CAM, 주 원본 바이트 예산은 10%다.
- 주 비교군은 동일 PE 구조와 동일 실제 바이트 예산을 맞춘 structure-matched random이다.
- 주 평가는 deletion ΔNLL과 keep-only malicious score다.
- 현재 상태는 데이터 접근 전 설계인 KISA-XAI-V5.0-DRAFT다. v5 데이터 준비, 모델 학습,
  Grad-CAM 결과는 아직 없다. 기존 v1-v4 결과를 v5 결과로 표현하거나 합치지 마라.
- Grad-CAM 영역은 '모델 귀속 영역' 또는 '악성 판정 근거 후보'라고 부른다. 위치 ground
  truth가 없으므로 '실제 악성 코드 구역', '악성 행위 위치', '분석 시간 단축 입증'이라고
  쓰지 마라.
- 결과가 부정적이어도 연구는 종료 가능하다. 높은 분류 정확도가 충실한 공간 설명을
  보장하지 않는다는 평가 결과도 유효하다.

1. GitHub에서 정확한 연구선 복원

Git과 Python 3.10-3.12를 준비하라. Windows PowerShell의 권장 예시는 다음과 같다.
경로는 장비의 여유 공간에 맞게 바꾸되, 악성코드 데이터는 저장소 밖의 별도 비동기화
경로를 사용하라.

$RepoRoot = 'D:\research\ua-sahi-mal'
git clone --branch research/kisa-xai-v5 --single-branch `
  https://github.com/stonesteelchoi/ua-sahi-mal.git $RepoRoot
Set-Location -LiteralPath $RepoRoot
git remote -v
git branch --show-current
git log -5 --oneline --decorate
git status --short --branch
git merge-base --is-ancestor 4b1f6ee HEAD
if ($LASTEXITCODE -ne 0) { throw 'KISA-XAI-v5 기준 커밋 4b1f6ee가 없음' }

브랜치가 원격에서 아직 보이지 않으면 임의로 main에서 v5를 재작성하지 마라. 먼저
`git fetch origin --prune` 후 `git branch -r`로 확인하고, 그래도 없으면 사용자에게
`research/kisa-xai-v5` 푸시 여부를 확인하라.

clone 직후 다음 문서를 이 순서로 읽어라.

- paper/v5-kisa-xai/README.md
- paper/v5-kisa-xai/RESEARCH_PROPOSAL_KO.md
- paper/v5-kisa-xai/EXPERIMENT_PROTOCOL.md
- paper/v5-kisa-xai/protocol/KISA_XAI_V5_0_DRAFT.yaml
- paper/decisions/ADR-003-kisa-binary-xai.md
- SECURITY.md
- pyproject.toml
- scripts/setup.ps1
- docs/NEW_MACHINE_HANDOFF.md
- docs/artifacts/README.md, docs/artifacts/FILES.md, docs/artifacts/manifest.json

README.md 안에는 보존된 v1-v4 안내가 길게 남아 있다. v5 연구 판단에서는 위 v5 문서가
우선한다. 기존 자료는 역사·회귀검사 자산으로만 취급하라.

2. 로컬 Python/GPU 환경 구축

기준 개발 환경은 Python 3.10-3.12, torch 2.8.0, torchvision 0.23.0이다. NVIDIA
Windows 장비에서는 저장소 설치 스크립트를 먼저 사용하라.

nvidia-smi
python --version
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -TorchIndex cu128
if ($LASTEXITCODE -ne 0) { throw '환경 설치 실패' }

CPU 전용 장비에서는 다음을 사용한다.

powershell -ExecutionPolicy Bypass -File scripts/setup_cpu.ps1

설치 후 `doctor --strict`만으로 GPU 사용을 확정하지 말고 실제 CUDA 계산을 실행하라.

.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ua_sahi_mal doctor --strict
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); x=torch.randn(512,512,device='cuda'); y=x@x; torch.cuda.synchronize(); assert torch.isfinite(y).all(); print('CUDA OK', y.device)"

프로젝트의 현재 코드 회귀검사를 실행하고 결과를 새 로그 디렉터리에 기록하라.

$RunTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$CheckDir = "runs/kisa-xai-env-$RunTag"
New-Item -ItemType Directory -Path $CheckDir -Force | Out-Null
nvidia-smi | Out-File "$CheckDir/nvidia-smi.txt" -Encoding utf8
.\.venv\Scripts\python.exe -m pip freeze | Out-File "$CheckDir/pip-freeze.txt" -Encoding utf8
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ua_sahi_mal smoke
.\.venv\Scripts\python.exe -m ua_sahi_mal.evidence smoke --out "$CheckDir/evidence-smoke"
.\.venv\Scripts\python.exe scripts/check_repository_safety.py
.\.venv\Scripts\python.exe scripts/audit_paper_numbers.py
.\.venv\Scripts\python.exe -m build

합성 smoke와 기존 테스트 통과는 v5 실험 성공을 뜻하지 않는다. 이는 저장소 환경과 기존
코드가 연결된다는 회귀검사다.

현재 pyproject.toml에는 v5 전용 Grad-CAM과 통계 기준선 의존성이 아직 별도 그룹으로
동결되어 있지 않다. 구현 전에 공식 소스를 확인하고, `grad-cam`, `scikit-learn` 및 실제로
필요한 통계 패키지를 `xai` 선택 의존성으로 버전 범위를 정해 추가하라. 임의의 최신 버전을
설치한 뒤 버전을 기록하지 않은 채 본 실험을 시작하지 마라. 설치 후 import smoke, CUDA
Grad-CAM 1건, CPU fallback을 검사하고 `pip freeze`를 보존하라.

공식 설치 참고:
- PyTorch 이전 버전: https://pytorch.org/get-started/previous-versions/
- pytorch-grad-cam: https://github.com/jacobgil/pytorch-grad-cam
- scikit-learn 설치: https://scikit-learn.org/stable/install.html

3. KISA 주 데이터셋 접근

주 데이터 후보는 아래 KISA 공식 상세 페이지다.

A. 내부 학습/검증/시험 후보
- KISA 2017 대용량 정상/악성파일 I (training set)
- Dataset ID: KISA_CISC2017_datachallenge_Malwares.01
- 공식 페이지: https://www.ksecurity.or.kr/kisis/subIndex/374.do
- 공식 설명: 7,500개씩 2세트, 총 15,000개, 약 6.733GB, 정상/악성 원본 파일,
  MD5 형태 filename과 class 0/1 정답지

B. 동결 외부 평가 후보
- KISA 2018 대용량 정상/악성파일 III
- Dataset ID: KISA-datachallenge2018-Malwares.03
- 공식 페이지: https://www.ksecurity.or.kr/kisis/subIndex/376.do
- 공식 설명: 10,000개씩 5세트, 총 50,000개, 약 14.3GB, 32-bit Windows,
  1-3번 세트 라벨 있음, 4-5번 본선 세트 라벨 없음, 확장자 .vir, 파일 끝에
  KISA 4바이트 padding 추가

C. 대체 외부 평가 후보
- KISA 2019 대용량 정상/악성파일 IV
- Dataset ID: KISA-datachallenge2019-Malwares.04
- 공식 페이지: https://www.ksecurity.or.kr/kisis/subIndex/461.do
- 공식 설명: 10,000개씩 4세트, 총 40,000개, 약 18.6GB, 32/64-bit Windows와
  HTML/HWP 등 스크립트·문서 형식 혼합, 확장자 .vir, KISA 4바이트 padding 추가

중요: 2026-09-14 확인 시 위 공개 HTML에는 실제 ZIP/7z 직접 다운로드 URL이 노출되지
않았다. 따라서 URL 패턴을 추측하거나 로그인·승인 절차를 우회하지 마라. 브라우저에서
공식 페이지를 열어 현재 다운로드 버튼, 회원 로그인, 이용 신청, 약관, 연구·논문 사용
조건을 확인하라. 사용자가 보유한 계정이나 승인 파일이 필요하면 그 사실과 필요한 행동을
정확히 보고하라. 접근 권한이 없는 상태에서 다운로드에 성공했다고 쓰지 마라.

데이터를 받을 수 있으면 저장소 밖에 보관한다. 예시:

$KisaRoot = 'D:\secure-malware-data\kisa'
New-Item -ItemType Directory -Path "$KisaRoot\archives" -Force | Out-Null
New-Item -ItemType Directory -Path "$KisaRoot\2017" -Force | Out-Null
New-Item -ItemType Directory -Path "$KisaRoot\2018" -Force | Out-Null

이 경로는 OneDrive, Google Drive Desktop, Dropbox, Git 작업트리와 동기화하지 마라.
원본 검체를 실행·import·동적 분석하지 말고, 관리자 권한이 아닌 전용 계정과 격리 저장소를
사용하라. 압축 해제 전에 아카이브 이름, 바이트 크기, SHA-256, 다운로드 시각, 페이지 URL,
약관과 접근 방법을 `data_access_audit.json`에 기록하라. 원본이나 복원 가능한 PNG를 Git에
추가하지 마라.

4. 데이터 접근 후 P0 Go/No-Go 감사

전체 학습을 시작하기 전에 아래를 구현·측정하고 보고서를 남겨라.

- 파일-라벨 결합률 >= 0.99
- class 값이 0/1 외 값을 포함하는지 검사
- SHA-256 완전 중복 제거
- 근접 중복/동일 계열이 분할을 넘지 않도록 group key 구성
- PE32/PE32+ 파싱 가능 수와 클래스별 수
- 정상·악성 각 1,000개 이상의 구조 매핑 가능 PE 확보
- KISA 4바이트 suffix의 실제 값·적용률·제거 전후 해시 기록
- 확장자 `.vir`를 PE 여부로 간주하지 말고 MZ/PE 서명과 독립 parser로 판정
- 파일 크기, suffix, 파일명 형식, 섹션 수, timestamp, overlay 비율 등 메타데이터만으로
  라벨을 예측하는 shortcut baseline
- KISA 2017/2018 간 exact/near duplicate와 수집시점 확인
- 라이선스·논문 발표·파생 집계 공개 가능 범위 확인

하나라도 핵심 gate를 충족하지 못하면 empirical test를 실행하거나 결과처럼 보고하지 마라.
실패 사유와 대체안만 기록한다. 2017 접근이 불가능하면 2018의 라벨 보유 세트를 내부
데이터로 전환하고 2019에서 PE만 엄격히 선별하는 대안을 검토하되, protocol revision을
새로 부여하라.

5. 기존 Google Drive 자산 링크와 사용 제한

기존 자산 전체 보관 폴더:
https://drive.google.com/drive/folders/1nQWy27-OQmfamBgIvc2822QDXn2_iL4C

clone 후 모든 직접 링크와 크기·SHA-256은 다음 파일을 사용하라.
- docs/artifacts/FILES.md
- docs/artifacts/manifest.json
- docs/artifacts/README.md

주요 직접 링크:
- MaleVis 224×224:
  https://drive.google.com/file/d/1K-AfcaQjoV808AtPZiV7ELPlVpTfmKZo/view?usp=drivesdk
- MaleVis 300×300:
  https://drive.google.com/file/d/1oz0I2X-jCPUc78m0d8sgzMEPEiOW8Nc2/view?usp=drivesdk
- 기존 runs와 MaleVis checkpoint:
  https://drive.google.com/file/d/1M-LRKgEcpZl3124dcjR4yVNQloNrDLko/view?usp=drivesdk
- BIG2015 정적 소표본:
  https://drive.google.com/file/d/1PAN6ta6oiK6lW295MQ3HMBlDMeZhN50f/view?usp=drivesdk
- BIG2015 원본 보관 ZIP:
  https://drive.google.com/file/d/1MgoxMX2OHh3Y6L8Mi4VP40xNL5p496Cy/view?usp=drivesdk

이 Drive 자산은 KISA-XAI-v5의 주 학습·시험 데이터가 아니다. SOREL disarmed pilot은
PEAtlas 좌표 회귀검사에만, BIG2015는 코드 회귀검사에만 사용한다. MaleVis는 v5에 사용하지
않는다. KISA 데이터 접근 실패를 기존 자산으로 몰래 대체하지 마라. Drive 권한이 제한되어
있으면 사용자에게 접근 권한을 요청하고, 파일을 받았다고 가정하지 마라.

6. v5 구현 순서

P0. 데이터 접근·약관·구조·shortcut 감사와 Go/No-Go 보고서
P1. 원본 파일 offset half-open interval을 224×224 픽셀에 대응시키는
    interval-binned-v1 변환기와 역매핑 metadata 구현
P2. PE 구조 구간(headers, executable/non-executable sections, resources,
    certificate, overlay, unknown) 매핑과 pefile 독립 교차검사
P3. group-stratified 70/15/15 split, split hash, dataset manifest 구현
P4. majority, metadata logistic, byte-histogram logistic 기준선 구현
P5. ResNet-18 학습, seed 42/43/44, validation macro-F1 선택, sanity gate
P6. Grad-CAM target layer 동결, all-malicious-test population 평가
P7. 5/10/20/40% 예산의 deletion·keep-only, random/front/entropy/
    structure-matched-random 20회 대조군 구현
P8. 파일 또는 near-duplicate group 단위 paired bootstrap 2,000회와 Holm 보정
P9. KISA 2018 외부 평가. 재학습·임계값 튜닝 금지
P10. 표·그림·비용·실패율을 채우고 결과에 맞는 제목과 결론 선택

P1-P8의 코드와 작은 합성 검사를 완성할 수는 있지만, 실제 데이터 감사와 split hash 없이
전체 학습을 시작하지 마라. test set은 protocol freeze 후 한 번만 열어라. 외부 데이터에
맞춰 표현, threshold, fill, target layer를 수정하지 마라.

7. 프로토콜 핵심 고정값

- split: group-stratified 70/15/15
- seeds: 42, 43, 44
- primary model: ResNet-18
- primary target: 모든 악성 test 파일의 malicious logit
- primary budget: unique source bytes 10%
- budgets: 5%, 10%, 20%, 40%
- primary fill: structure-conditioned resampling
- primary comparator: structure-matched random, 파일별 20회
- primary tests: deletion ΔNLL, keep-only malicious score
- bootstrap: 2,000회, 95% CI
- familywise tests: 2, Holm correction
- CAM이 양수값을 하나도 갖지 않아도 제외하지 말고 empty CAM으로 보존·보고
- 한 픽셀이 여러 source byte를 대표해 예산을 초과하면 요청 예산과 실제 unique byte
  예산을 모두 기록하고 대조군을 실제 예산에 맞춤
- augmentation에서 flip, rotation, random crop, color jitter 금지
- external adaptation, threshold tuning, retraining 금지

실제 데이터 감사로 값을 변경해야 한다면 KISA-XAI-V5.0-DRAFT를 덮어쓰지 말고 이유와
변경점을 기록한 새 protocol ID를 만든다. 데이터 감사·split·representation·모델·통계가
동결된 버전은 KISA-XAI-V5.1-FROZEN을 사용한다. 사후 탐색은 V5.2-EXPLORATORY로 분리한다.

8. 보안과 데이터 관리

- 바이너리를 실행, import, 에뮬레이션, 동적 분석하지 마라.
- 일반 개발 PC를 malware sandbox로 취급하지 마라.
- 원본, `.vir`, 추출 PE, 복원 가능한 raw-byte PNG, checkpoint를 Git에 커밋하지 마라.
- 저장소의 `scripts/check_repository_safety.py`를 매 커밋·푸시 전에 실행하라.
- 해시, 비가역 집계, 합성 fixture, 코드, 설정, 논문 문서만 공개 저장소에 넣어라.
- checkpoint는 신뢰한 출처와 해시를 기록하고 역직렬화 위험을 고려하라.
- 데이터 제공자의 약관과 조직 보안정책이 이 프롬프트보다 우선한다.

9. 작업 방식과 인수인계 보고

- 먼저 현재 사실을 읽고, 구현·검증 가능한 작업을 계속 진행하라.
- 긴 학습 전에 100-500개 비실행 정적 pilot으로 시간, VRAM, 디스크 증가량, 실패율을
  측정하라. pilot 결과를 본 결과와 분리하라.
- 결과 디렉터리에 Git commit, protocol ID, 환경, package freeze, dataset/archive hash,
  split hash, seed, config, stdout/stderr, 시작·종료 시각을 저장하라.
- 논문 수치는 집계 파일에서 자동 생성하고 수기로 복사한 값과 대조하라.
- 한도가 부족해지면 새 분석을 벌이지 말고 현재 변경을 검증·커밋한 뒤 다음을 문서화하라:
  완료 항목, 실패 항목, 마지막 성공 명령, 마지막 오류, 출력 경로, 다음 한 명령.
- 사용량 도구가 정확한 값을 제공하지 않으면 추정치를 정확한 남은 토큰처럼 쓰지 마라.

첫 응답에는 다음을 포함하라.

1. clone한 branch와 HEAD, 4b1f6ee 포함 여부
2. OS/Python/GPU/VRAM/디스크와 설치 성공 여부
3. 실행한 검증과 실패한 검증
4. KISA 세 공식 페이지의 현재 다운로드·로그인·약관 상태
5. 받은 데이터의 파일명·크기·SHA-256 또는 아직 받지 못한 정확한 이유
6. P0 Go/No-Go 상태
7. 다음에 실제로 실행할 한 단계

사실을 확인하기 전에는 데이터 확보, 모델 학습, 정확도, Grad-CAM 성능을 완료된 것으로
쓰지 마라.
```

---

## 링크 판정 메모

- GitHub clone URL과 브랜치는 공개 저장소의 실제 `origin`을 기준으로 기록했다.
- KISA 링크는 데이터셋 공식 상세 페이지다. 2026-09-14 현재 공개 HTML에서 직접
  아카이브 URL은 확인되지 않았다.
- Google Drive 링크는 저장소의 기존 자산 카탈로그에서 가져왔다. 공유 권한이 제한될 수
  있으며, KISA-XAI-v5 주 실험 데이터로 사용하지 않는다.
- 새 LLM은 다운로드 성공을 가정하지 말고 접근·약관·해시 감사를 먼저 수행해야 한다.
