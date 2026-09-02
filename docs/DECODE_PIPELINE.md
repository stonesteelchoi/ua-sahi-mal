# Static DECODE → YOLO11 → UA/JBU → selective SAHI runbook

이 문서는 **이미 승인된 정적 PNG/JPEG와 JSON만** 사용해 DECODE 계열 ROI를 UA-SAHI-MAL 데이터 계약으로 가져오고, YOLO11을 학습한 뒤, dense coarse map과 예산 제한 selective SAHI를 실행하는 절차를 설명합니다.

이 runbook의 범위에는 악성코드 검색·다운로드·압축 해제·실행·디스어셈블·샌드박스 제어·동적 분석 API 호출이 포함되지 않습니다. 그런 작업을 이 저장소나 일반 개발 PC에서 수행하지 마십시오. 별도 승인 환경이 만든 **PNG/JPEG 시각화, ROI JSON, split JSON**만 단방향으로 반입하고, 반입 전에 조직의 검역·해시·접근 통제를 적용해야 합니다.

## 1. What this pipeline does

```text
approved static PNG/JPEG + ROI JSON + explicit group-aware split JSON
                                │
                                ▼
                     import-decode (manifest v1)
                                │
              hash / bbox / basename / split-leakage checks
                                │
                                ▼
                    prepare-data (YOLO + COCO)
                                │
                                ▼
                     YOLO11 train / evaluate
                                │
               local malware-class checkpoint validation
                                │
                                ▼
        one full-image pass: pre-NMS P3/P4/P5 scores + predictions
                                │
                max-class probability + binary entropy
                                │
                                ▼
                  bilinear / anisotropic JBU / UPA
                                │
                                ▼
               guard + coverage + fixed-budget tile routing
                                │
                                ▼
                    selected-tile SAHI + GreedyNMM
```

`import-decode`는 입력 이미지를 열어 형식을 확인하고 SHA-256을 계산하지만, 어떤 입력도 실행하거나 import하지 않습니다. PNG/JPEG 외 확장자는 거부하며, ROI JSON의 절대 경로는 basename으로 축소한 다음 `--images-root` 아래의 유일한 파일과만 연결합니다. 같은 basename이 두 개 이상이면 모호한 연결을 피하기 위해 중단합니다.

## 2. Label semantics: choose before importing

기본 정책은 `class-agnostic`입니다.

| Policy | Detector class | Appropriate use | What it does **not** mean |
|---|---|---|---|
| `class-agnostic` | `malicious_evidence` 하나 | UA routing과 미세 근거의 위치 탐지에 대한 주 실험 | malware family 분류나 행동 의미 분류 |
| `roi-family` | ROI JSON의 `category_name` | 초기 Bayesian Grad-CAM family-box baseline | DECODE 최종 feature-cluster detector의 정확한 재현 |

DECODE의 초기 ROI segmentation 단계는 family/class target으로 Grad-CAM 영역을 만들 수 있습니다. 그러나 DECODE의 후속 feature-grouping 단계는 한 family 안의 시각적으로 유사한 ROI들을 다시 여러 feature-region `category_id`로 묶고 family를 supercategory로 유지합니다. 따라서 다음을 구분해야 합니다.

- 이 저장소의 주 지역화 정책: class-agnostic `malicious_evidence`.
- 간단한 비교 기준: `roi-family`.
- **Strict DECODE reproduction**: 원 논문의 grouping 설정으로 만든 feature-cluster ID와 family supercategory를 보존하는 별도 COCO adapter가 필요합니다. 현재 `import-decode`는 이를 구현하지 않으며 `roi-family` 결과를 strict reproduction이라고 부르면 안 됩니다.
- `process`, `registry`, `network`, `file` 같은 행동 evidence class는 ROI family JSON만으로 자동 추론할 수 없습니다. quadrant-aware 또는 사람이 검증한 별도 라벨이 필요합니다.

주 실험은 detector가 “어느 family인가”까지 동시에 학습하도록 요구하지 않고, **어디에 위험 근거가 있는가**를 먼저 측정합니다. Family prediction이 필요하면 image-level classifier를 별도 head/모델로 평가하는 것이 label semantics를 가장 명확하게 유지합니다.

## 3. Approved static input contract

### 3.1 ROI JSON

각 `--annotation` 파일은 JSON array이거나 `annotations` array를 가진 object여야 합니다. 한 record의 최소 형식은 다음과 같습니다.

```json
[
  {
    "image_name": "sample-0001.png",
    "category_name": "dropper",
    "bbox": [120, 80, 34, 28],
    "source_score": 0.87
  }
]
```

`bbox`는 `[x, y, width, height]`이며 좌상단은 음수가 아니고 크기는 양수여야 합니다. 박스가 이미지 경계를 벗어나면 import가 실패합니다. `source_score`는 선택 사항이며 `[0, 1]` 범위입니다. 모든 imported ROI는 다음 provenance를 갖습니다.

- `annotation_source: bayesian_gradcam`
- 명시한 `annotation_version`
- 명시한 `teacher_model` 식별자/해시
- `verified: false`

즉 imported ROI는 자동으로 human-verified ground truth가 되지 않습니다.

### 3.2 Split map

Split은 파생 이미지 생성 후 무작위로 나누지 말고 원본 source group 수준에서 먼저 고정합니다.

```json
{
  "sample-0001.png": {
    "split": "train",
    "family_id": "source-group-0001"
  },
  "sample-0201.png": {
    "split": "val",
    "family_id": "source-group-0201"
  },
  "sample-0301.png": {
    "split": "test",
    "family_id": "source-group-0301"
  }
}
```

`family_id` 대신 `source_group` 키를 사용할 수 있습니다. 어느 이름을 쓰든 같은 값은 둘 이상의 split에 나타날 수 없습니다. 동일·근접 변종을 하나의 group으로 묶을 수 없는 경우 split 누수를 배제했다고 주장하지 마십시오. DECODE 공개 소스는 이 저장소가 요구하는 독립 test/group-aware split map을 대신 제공하지 않으므로, 연구자가 명시적으로 생성·동결·해시해야 합니다.

### 3.3 Optional static behavior converter

이미 승인 환경이 CAPE-shaped JSON만 제공하고 PNG는 제공하지 않는 경우, optional static converter로 API 이름 영상을 만들 수 있습니다. 이 명령은 sandbox를 실행·제어하지 않고 이미 존재하는 JSON만 읽습니다.

```powershell
$Python = "C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe"
& $Python -m ua_sahi_mal encode-behavior-report `
  --source "$StaticRoot\reports\sample-0001.json" `
  --output "$StaticRoot\images\sample-0001.png" `
  --allow-sensitive-output
```

입력 계약은 `behavior.processes[].calls[]`이며 `process`, `registry`, `network`, `filesystem` category와 ASCII `api` 이름만 픽셀에 반영합니다. 인수·payload·buffer·경로는 렌더링하지 않습니다. 출력 순서는 `process | registry / network | filesystem`이고, image와 metadata는 기존 경로를 덮어쓰지 않습니다.

이 `decode-static-behavior-v1` 변환기는 공개 DECODE 알고리즘에서 영감을 받은 고정된 **DECODE-like variant**입니다. DECODE 원 코드의 dataset-specific duplicate reduction, padding, tiling을 완전히 재현한다고 주장하지 마십시오. 정확 재현 실험은 원 revision의 전처리 코드·설정·출력 해시를 별도 동결해야 합니다. 변환만으로 ROI가 생기지는 않으므로 독립적으로 생성·검토된 ROI JSON이 계속 필요합니다.

### 3.4 Static-input checklist

- `import-decode` 입력은 승인된 `.png`, `.jpg`, `.jpeg`, ROI `.json`, split `.json`뿐입니다.
- Optional converter 입력은 승인된 static behavior `.json`뿐이며 생성 PNG도 민감 파생물입니다.
- 원본 executable, archive, memory dump, PCAP, API credential을 workspace에 복사하지 않습니다.
- 이미지도 원래 byte/API sequence를 드러낼 수 있는 민감한 파생물로 취급합니다.
- annotation JSON, split JSON, teacher ID/checkpoint hash, dataset revision을 변경 불가능한 실험 입력으로 기록합니다.
- `test`에는 사람 또는 독립 도구가 검증한 localization subset을 별도로 유지합니다. Teacher가 만든 pseudo-box만으로 최종 성능을 평가하면 순환 평가입니다.

## 4. PowerShell: import and prepare

아래 예시는 user-managed Python environment와 승인 데이터 디렉터리를 명시적으로 사용합니다. 경로는 환경에 맞게 바꾸십시오.

```powershell
$Python = "C:\tool\anaconda5\envs\ua-sahi-yolo\python.exe"
$StaticRoot = "C:\secure-research\decode-static-v1"
$RunRoot = "C:\secure-research\runs\decode-v1"

$env:ULTRALYTICS_SAFE_LOAD = "true"
$env:YOLO_OFFLINE = "true"
$env:YOLO_AUTOINSTALL = "false"
$env:PIP_NO_INDEX = "1"
```

`train`, `evaluate`, `predict`, restricted checkpoint load는 이 플래그 외에도 현재 Python 프로세스의 non-loopback socket 연결을 차단합니다. Ultralytics plot 생성은 일부 환경에서 font asset을 가져오려 하므로 학습·평가 adapter가 `plots=False`를 강제합니다. 로컬 loopback만 허용하며 외부 fetch 시도는 실패로 종료됩니다.

여러 ROI JSON을 가져올 때 `--annotation`을 반복합니다. 기본·권장 policy는 class-agnostic입니다.

```powershell
& $Python -m ua_sahi_mal import-decode `
  --annotation "$StaticRoot\roi\dropper.json" `
  --annotation "$StaticRoot\roi\ransomware.json" `
  --images-root "$StaticRoot\images" `
  --split-map "$StaticRoot\splits.v1.json" `
  --output "$StaticRoot\manifest.class-agnostic.v1.json" `
  --dataset-name "decode-static-class-agnostic-v1" `
  --annotation-version "decode-bgcam-roi-v1" `
  --teacher-model "sha256:<teacher-checkpoint-sha256>" `
  --class-policy class-agnostic
```

ROI-family baseline은 새 output/dataset revision으로 별도 생성하십시오.

```powershell
& $Python -m ua_sahi_mal import-decode `
  --annotation "$StaticRoot\roi\dropper.json" `
  --annotation "$StaticRoot\roi\ransomware.json" `
  --images-root "$StaticRoot\images" `
  --split-map "$StaticRoot\splits.v1.json" `
  --output "$StaticRoot\manifest.roi-family.v1.json" `
  --dataset-name "decode-static-roi-family-v1" `
  --annotation-version "decode-bgcam-roi-v1" `
  --teacher-model "sha256:<teacher-checkpoint-sha256>" `
  --class-policy roi-family
```

Importer와 preparer는 기존 output을 덮어쓰지 않습니다. 변경한 입력은 새 revision 경로에 기록하십시오.

```powershell
& $Python -m ua_sahi_mal validate-data `
  --manifest "$StaticRoot\manifest.class-agnostic.v1.json"

& $Python -m ua_sahi_mal prepare-data `
  --manifest "$StaticRoot\manifest.class-agnostic.v1.json" `
  --output-dir "$StaticRoot\prepared\class-agnostic-v1" `
  --allow-sensitive-output
```

`--allow-sensitive-output`은 파생 이미지의 보안 등급을 이해했다는 명시적 확인이지 재배포 권한이 아닙니다.

## 5. Train, validate the checkpoint, and evaluate

Base checkpoint를 미리 승인된 로컬 경로로 지정하십시오. 이 runbook은 모델 파일을 자동 다운로드하지 않습니다.

```powershell
$DataYaml = "$StaticRoot\prepared\class-agnostic-v1\dataset.yaml"
$BaseModel = "C:\secure-research\models\yolo11n.pt"

& $Python -m ua_sahi_mal train `
  --data $DataYaml `
  --model $BaseModel `
  --epochs 100 `
  --image-size 640 `
  --batch-size 16 `
  --device cuda:0 `
  --seed 42 `
  --project "$RunRoot\train" `
  --name "class-agnostic-seed42"
```

학습이 끝난 `.pt`를 바로 추론에 사용하지 말고 dataset class contract와 대조합니다. 검증기는 local `.pt`만 restricted safe-load하고 SHA-256, class order, model/task, parameter count를 기록합니다. `person`, `car`, `airplane`, `truck` 등 COCO class를 가진 checkpoint는 최종 malware detector로 거부됩니다.

```powershell
$Best = "$RunRoot\train\class-agnostic-seed42\weights\best.pt"

& $Python -m ua_sahi_mal validate-checkpoint `
  --model $Best `
  --data $DataYaml `
  --dataset-revision "decode-static-class-agnostic-v1" `
  --output "$RunRoot\checkpoint.metadata.json"
```

필요하면 pin한 checkpoint digest를 `--expected-sha256 <64-hex-digest>`로 추가합니다.

```powershell
& $Python -m ua_sahi_mal evaluate `
  --data $DataYaml `
  --model $Best `
  --split test `
  --image-size 640 `
  --batch-size 16 `
  --device cuda:0 `
  --project "$RunRoot\val" `
  --name "class-agnostic-test-seed42" `
  --dataset-revision "decode-static-class-agnostic-v1" `
  --metrics-json "$RunRoot\detector-test.metrics.json" `
  --metrics-csv "$RunRoot\detector-test.metrics.csv"
```

이 `evaluate` 명령이 저장하는 기본 Ultralytics summary는 detector-only metric입니다. `mAP50`, `mAP50:95` 등이 기록될 수 있지만 다음 값은 여기서 측정되지 않습니다.

- COCO size-stratified `AP_S`
- selected-tile `Tile Recall`
- detector images/invocations
- full end-to-end p50/p95 latency
- peak VRAM

따라서 빈 값이나 “not measured”를 0으로 바꾸면 안 됩니다. 논문의 primary gate는 별도의 dataset-level strategy harness에서 Full SAHI-100과 같은 이미지·checkpoint·hardware로 측정해야 합니다.

## 6. Dense coarse routing and selective SAHI

권장 primary inference는 `--coarse-mode dense --upsampler jbu`입니다.

```powershell
$Image = "$StaticRoot\prepared\class-agnostic-v1\images\test\sample-0301.png"
$GroundTruth = "$StaticRoot\prepared\class-agnostic-v1\annotations\test.json"

& $Python -m ua_sahi_mal predict `
  --source $Image `
  --model $Best `
  --data $DataYaml `
  --dataset-revision "decode-static-class-agnostic-v1" `
  --output-dir "$RunRoot\predict" `
  --device cuda:0 `
  --coarse-mode dense `
  --upsampler jbu `
  --route-scale 16 `
  --slice-height 400 `
  --slice-width 400 `
  --overlap 0.2 `
  --budget 0.5 `
  --probability-weight 0.8 `
  --entropy-weight 0.2 `
  --guard-threshold 0.15 `
  --coverage-ratio 0.2 `
  --ground-truth $GroundTruth `
  --iou-threshold 0.5 `
  --tile-recall-coverage 0.5
```

### Dense mode

`dense`는 full-image standard prediction과 같은 YOLO forward pass에서 final Detect head를 관찰합니다. Ultralytics version에 맞는 raw output에서 P3/P4/P5 spatial score tensors를 분리하고, 각 level에서 class sigmoid probability의 max를 취한 뒤 low-resolution grid로 resize/max-aggregate합니다. Binary entropy를 계산하고 `probability_weight`와 `entropy_weight`로 결합한 map을 upsample합니다.

이 adapter는 version-specific입니다. 지원하지 않는 Ultralytics head 형식이면 오류로 중단하며 box mode로 조용히 바뀌지 않습니다. 호환성 baseline이 필요할 때만 명시적으로 `--coarse-mode boxes`를 사용하십시오. Box mode는 post-NMS coarse boxes와 texture prior를 사용하므로 dense-logit 실험과 같은 방법이 아닙니다.

### Upsampler choices

| CLI value | Meaning | Compute | Interpretation |
|---|---|---|---|
| `bilinear` | OpenCV bilinear resize | CPU, deterministic | interpolation baseline |
| `jbu` | guidance RGB의 edge를 따르는 anisotropic joint bilateral baseline | CPU, deterministic | 이 저장소의 JBU baseline; official UA가 아님 |
| `upa` | external Upsample Anything adapter | CUDA + per-image test-time optimization | 공식 upstream implementation adapter |
| `auto` | UPA source+CUDA가 모두 있으면 UPA, 아니면 bilinear | environment-dependent | JBU를 자동 선택하지 않음 |

JBU는 local Sobel normal/tangent 방향의 비등방성 spatial Gaussian과 RGB range kernel을 사용합니다. Official UPA와 알고리즘·비용·라이선스 조건이 다르므로 결과 표에서 둘을 합치지 마십시오. UPA는 TTO 시간을 포함한 end-to-end latency와 peak VRAM을 따로 측정해야 합니다.

### Budget semantics

`--budget 0.5`는 candidate tile 수의 약 50%를 선택하는 routing budget입니다. Guard와 coverage allocation, deterministic tie-breaking이 선택을 바꿀 수 있으므로 실제 `candidate_tiles`, `selected_tiles`, `selected_indices`와 각 candidate의 bbox/score/guard/selection을 `summary.json`에서 확인하십시오. 적은 tile 수가 곧 낮은 end-to-end latency를 보장하지 않습니다. Coarse forward, map upsampling, tile selection, selected-tile inference, merge를 모두 시간에 포함해야 합니다.

정답을 지정하면 `--tile-recall-coverage` 이상의 GT 면적을 하나 이상의 selected tile이 덮는지를 기준으로 routing Tile Recall을 기록합니다. `detector_images`와 `detector_invocations`에는 selected-tile work뿐 아니라 full-image coarse detector pass 1회도 포함됩니다. 이는 dataset-level AP나 hardware peak VRAM을 대신하지 않습니다.

각 predict run은 timestamped directory에 다음 파일을 만듭니다.

```text
annotated.png
predictions.json
routing_heatmap.png
selected_tiles.png
summary.json
localization_evaluation.json  # --ground-truth를 지정한 경우
localization_evaluation.csv   # --ground-truth를 지정한 경우
```

`predictions.json`과 별도 ground truth를 나중에 비교할 수도 있습니다.

```powershell
& $Python -m ua_sahi_mal evaluate-predictions `
  --predictions "$RunRoot\predict\<run-id>\predictions.json" `
  --ground-truth $GroundTruth `
  --image-name "sample-0301.png" `
  --iou-threshold 0.5 `
  --output-json "$RunRoot\localization.sample-0301.json" `
  --output-csv "$RunRoot\localization.sample-0301.csv"
```

이 결과는 confidence-ordered, class-aware greedy IoU matching의 TP/FP/FN, precision, recall, F1과 class mismatch diagnostic입니다. Dataset-level AP 또는 COCO evaluator를 대신하지 않습니다.

## 7. Provenance record

학습/평가 전후에는 base model, annotation files, split map, manifest, runtime, seed, dataset revision과 final checkpoint metadata를 함께 고정합니다.

```powershell
& $Python -m ua_sahi_mal record-run `
  --repo-root "C:\dev\ua-sahi-mal-yolo" `
  --base-model $BaseModel `
  --annotation "$StaticRoot\roi\dropper.json" `
  --annotation "$StaticRoot\roi\ransomware.json" `
  --split-map "$StaticRoot\splits.v1.json" `
  --manifest "$StaticRoot\manifest.class-agnostic.v1.json" `
  --data $DataYaml `
  --dataset-revision "decode-static-class-agnostic-v1" `
  --teacher-model "sha256:<teacher-checkpoint-sha256>" `
  --annotation-version "decode-bgcam-roi-v1" `
  --class-policy class-agnostic `
  --epochs 100 `
  --batch-size 16 `
  --image-size 640 `
  --device cuda:0 `
  --seed 42 `
  --best-checkpoint $Best `
  --output "$RunRoot\pipeline-inputs.json"
```

Output files are immutable by default: 같은 경로가 있으면 명령이 덮어쓰지 않고 실패합니다. 변경이 생기면 새 dataset/run revision을 사용하십시오.

## 8. Required experiment matrix

동일한 test images, detector checkpoint, confidence, slice geometry, merge 설정, hardware에서 최소 다음 행을 비교합니다.

| Strategy | Coarse source | Upsampler | Budget | Required reporting |
|---|---|---|---:|---|
| Full Image | none | none | n/a | AP, latency |
| Full SAHI-100 | all tiles | none | 1.0 | AP_S, AP50, calls, p95, VRAM |
| Uniform/Random-50 | non-learned | none | 0.5 | same metrics, fixed seeds |
| Boxes+Bilinear-50 | post-NMS boxes + texture | bilinear | 0.5 | compatibility baseline |
| Dense+Bilinear-50 | P3/P4/P5 probability+entropy | bilinear | 0.5 | routing ablation |
| Dense+JBU-50 | P3/P4/P5 probability+entropy | anisotropic JBU | 0.5 | primary non-UA baseline |
| Dense+UPA-50 | P3/P4/P5 probability+entropy | official UPA | 0.5 | TTO steps/time/VRAM |

Primary claim의 최소 보고 항목은 `AP_S`, `AP50`, `mAP50:95`, Tile Recall, detector images/invocations, end-to-end p50/p95 latency, peak VRAM입니다. 세 성공 gate—Full SAHI 대비 `AP_S` 손실 1.5 point 이하, detector work 40% 이상 감소, p95 latency 25% 이상 감소—를 **모두** 만족해야 성공입니다. 현재 저장소에는 실제 DECODE 결과가 포함되어 있지 않으며, synthetic smoke 결과를 논문 성능으로 사용하면 안 됩니다.

표 스키마를 먼저 동결하려면 `paper-table-template`을 실행합니다. 각 metric은 `value`, `status`, `unit`을 가지며 초기 값은 `null/not_measured`입니다. 실제 측정 셀만 `status: measured`와 수치로 바꾼 뒤 `compile-paper-table`을 실행하면 JSON/CSV가 생성됩니다. Full SAHI와 후보의 `AP_S`, `detector_images`, `latency_p95_ms`가 모두 측정된 경우에만 3중 gate가 계산됩니다.

```powershell
& $Python -m ua_sahi_mal paper-table-template `
  --experiment-id "decode-yolo11-primary-v1" `
  --dataset-revision "decode-static-class-agnostic-v1" `
  --checkpoint-sha256 "<best.pt-sha256>" `
  --output "$RunRoot\paper-table.input.json"

& $Python -m ua_sahi_mal compile-paper-table `
  --input "$RunRoot\paper-table.input.json" `
  --output-json "$RunRoot\paper-table.compiled.json" `
  --output-csv "$RunRoot\paper-table.compiled.csv"
```

## 9. Troubleshooting without weakening the contract

- `ambiguous image basename`: `--images-root` 아래 중복 basename을 제거하거나 dataset revision별 root를 분리합니다. 임의로 첫 파일을 고르지 마십시오.
- `family/source group ... crosses ...`: split map을 원본 group 기준으로 다시 만듭니다. validation을 우회하지 마십시오.
- `checkpoint exposes COCO object classes`: 학습 산출물의 `best.pt` 경로와 dataset classes를 확인합니다. repository의 generic COCO checkpoint를 malware 결과로 사용하지 마십시오.
- `unsupported Ultralytics detection-head output`: pin된 supported Ultralytics version을 복원하거나 별도의 `boxes` baseline을 실행합니다. Dense 실험이라고 표기한 채 silent fallback하지 마십시오.
- UPA CUDA/source error: `jbu` 또는 `bilinear` baseline으로 실행하고 UPA 행을 “not run”으로 남깁니다. 서로 다른 방법의 값을 대체하지 마십시오.
- Empty/partial metrics: 해당 metric을 실제 측정하는 harness를 추가합니다. 미측정 값을 0 또는 다른 metric으로 대체하지 마십시오.
