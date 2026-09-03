# UA-SAHI-MAL

악성코드의 바이트·opcode·동적 행위 시각화에서 미세한 위험 근거를 객체탐지 바운딩 박스로 지역화하고, 고위험 슬라이스만 선택해 정밀 추론하는 연구용 저장소입니다.

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

## 요구 사항과 설치

- Python 3.10~3.12
- Git
- CPU smoke/data 준비: CUDA 불필요
- 실제 YOLO/UPA 실험: 호환 PyTorch와 NVIDIA CUDA GPU 권장

```powershell
git clone --recurse-submodules <repository-url>
Set-Location ua-sahi-mal-yolo
powershell -ExecutionPolicy Bypass -File scripts/setup_cpu.ps1
```

GPU 환경은 다음처럼 준비합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -TorchIndex cu128
```

설치 스크립트는 PyTorch `2.8.0`, torchvision `0.23.0`, SAHI 서브모듈, Ultralytics `8.4.67`, 프로젝트 개발 도구를 설치합니다. GPU/CUDA 조합은 사용하는 장비에서 다시 검증해야 합니다.

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

## 가장 먼저 실행할 smoke test

먼저 사전 등록된 예제 실험 계약이 바뀌지 않았는지 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal validate-config `
  --config configs/experiments/decode_primary.example.yaml
```

```powershell
.\.venv\Scripts\python.exe -m ua_sahi_mal smoke
```

이 명령은 임시 synthetic opcode 두 개를 생성하고 다음 전체 경로를 CPU에서 검사합니다.

```text
manifest → opcode RGB → source-range bbox → COCO/YOLO
         → fake detector → Full Image/Full SAHI/Budgeted SAHI
         → GreedyNMM → call reduction/Tile Recall summary
```

출력은 `runs/smoke/<timestamp>/`에 생기며 Git에서 제외됩니다. PowerShell wrapper도 사용할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_smoke.ps1
```

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

## Docker 재현 환경

장비 간 의존성 차이를 없애기 위한 컨테이너 정의가 `docker/` 에 있다.

```bash
make build      # 또는 docker compose -f docker/docker-compose.yml build
make verify     # ruff + pytest 107건 + 합성 스모크 + 논문 수치 감사 255건
make offline    # 네트워크를 끊고 같은 검증
```

Windows 는 `.\scripts\setup_docker.ps1` 하나로 빌드·검증·오프라인 재검증까지 끝내고,
결과를 `docs/verification/` 에 커밋 가능한 형태로 복사한다.

사내 프록시가 막힌 환경을 전제로 세 개의 손잡이를 뒀다 — `BASE_IMAGE`(레지스트리 미러),
`TORCH_INDEX_URL`(`pypi` 또는 CUDA 인덱스), `APT_MIRROR`. 자세한 사용법과 **현재 무엇이
검증되었고 무엇이 검증되지 않았는지**는 [docker/README.md](docker/README.md) 에 있다.

컨테이너 없이 같은 검증을 돌리려면 `bash scripts/verify_env.sh` 또는 `make check` 를 쓴다.

`.github/workflows/verify.yml` 은 push 마다 (1) Python 3.10·3.12 네이티브 검증,
(2) 컨테이너 이미지 빌드 후 컨테이너 안 검증과 `--network none` 오프라인 재검증,
(3) 저장소 안전 검사를 수행한다. 로컬에서 이미지 빌드가 막히는 환경이라도 이 워크플로가
빌드 가능성을 대신 증명한다.

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
에서 가져온 것으로 새로 실행하지 않았다. 실험 2(BIG2015 경계 복원)는 이번에 실행한 것이며
`scripts/big2015_p0a.py` 와 `scripts/big2015_boundary_experiment.py` 로 재현된다. 그 수치가 근거 데이터로부터 올바르게 도출됐는지는
`python scripts/audit_paper_numbers.py` 가 285건의 검사로 대조한다(근거 사본은 [docs/results/](docs/results/)).
논문을 고치면 감사 스크립트의 기대값 상수도 같이 고쳐야 하며, 그러지 않으면 검증이 실패한다. 저자·소속·투고 번호는 자리표시자이므로 투고 전에
채워야 한다. 기존 `output/documents/malevis-decode-transfer-paper-ko.docx` 는 별도 문서이며
이 초고가 대체하지 않는다.

## 대용량 산출물

다음은 `.gitignore` 대상이라 저장소에 포함되지 않는다.

| 대상 | 크기 | 배포 방법 |
|---|---|---|
| `datasets/malevis_train_val_224x224`, `..._300x300` | 약 4.6 GB | 원 저작자 공개 배포본을 내려받는다(아래) |
| `runs/malevis/full-20260829/**/best_model.pt` 등 체크포인트 | 약 76 MB | Google Drive |

MaleVis 는 공개 데이터셋이므로 원본을 직접 내려받는 것이 가장 확실한 재현 경로다. 무결성은
`runs/malevis/audit-20260829/*.audit-v2.json` 의 `dataset_fingerprint_sha256` 로 확인할 수 있다
(224×224: `17fef896940818d9d5a09dedb1345107d9080c35bd1035603a6f3ce54291be43`).

체크포인트 Google Drive 링크: `<업로드 후 URL 을 여기에 붙여넣으십시오>`

체크포인트 SHA-256 (seed 42):

| 해상도 | SHA-256 |
|---|---|
| 224×224 | `930a8c73fe270226c98dd5d5753ec80eeb02c2ad7bd72a7dd6cf290286a6b6e3` |
| 300×300 | `f8a6ce4665be895ca4fd95da93509aefd332830ec05fac2413c1b0d623a710da` |

## 품질 확인

```powershell
.\.venv\Scripts\python.exe scripts/check_repository_safety.py
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ua_sahi_mal doctor --strict
.\.venv\Scripts\python.exe -m build
```

CI는 Ubuntu/Python 3.10·3.11과 Windows/Python 3.12에서 repository safety, lint, tests, synthetic smoke, strict doctor, package build 및 wheel 설치 검증을 수행합니다.

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

## 제3자 출처와 라이선스

- SAHI `0.12.2`: MIT, `external/sahi` 서브모듈
- Upsample Anything: 고정 서브모듈. 확인 당시 명시적 라이선스가 없어 원 코드를 복사·수정하지 않음
- Ultralytics `8.4.67`: AGPL-3.0 또는 별도 enterprise license
- NotebookLM의 문헌과 링크는 요구사항 확인에만 사용했으며 코드를 복사하지 않음

세부 내용과 참고 URL은 [THIRD_PARTY.md](THIRD_PARTY.md), [연구 출처](docs/SOURCES.md)에 기록합니다. 기존 원격탐사 프로젝트 문맥은 이력 보존을 위해 [legacy 문서](docs/legacy_remote_sensing/)로 옮겼으며 새 실험의 사실 기준으로 사용하지 않습니다.

빌드된 wheel에는 라이선스가 불명확한 UPA 소스를 포함하지 않습니다. Wheel 설치는 데이터 준비·학습·평가와 bilinear fallback을 지원하며, `--upsampler upa`는 `--recurse-submodules`로 받은 소스 checkout에서만 사용할 수 있습니다.
