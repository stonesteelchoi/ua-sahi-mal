# XAI-v4 실험 프로토콜

**Protocol:** `XAI-V4.0-DRAFT`

**Primary dataset:** BIG2015-derived, validity-aware revision

**Primary model:** ResNet-18

**Primary XAI:** Grad-CAM

**Primary area budget:** 10% of valid input positions
**Test access:** protocol freeze 이후 1회 평가

## 1. 동결 전 체크리스트

다음 항목을 채운 커밋부터 `XAI-V4.1-FROZEN`으로 태그한다.

- [ ] 데이터 revision ID
- [ ] source archive 및 파생 manifest SHA-256
- [ ] class 이름과 sample 수
- [ ] exact/near-duplicate group 생성 방법
- [ ] train/val/test sample ID hash
- [ ] 입력 표현과 validity 처리
- [ ] raster width, resize, padding, normalization
- [ ] 모델 initialization과 target layer
- [ ] seed 3개
- [ ] optimizer, scheduler, epoch, early stopping
- [ ] area budget과 tie-breaking
- [ ] deletion fill 두 종류
- [ ] random control 반복 수
- [ ] primary metric과 통계 검정
- [ ] GPU, CUDA, PyTorch, torchvision version

## 2. 데이터 준비

### 2.1 Revision 이름

주 데이터 revision은 다음 형식을 쓴다.

```text
big2015-xai-<representation>-<split-version>
예: big2015-xai-maskaware-split01
```

manifest에는 적어도 다음 필드를 둔다.

```text
sample_id
family_label
source_group
source_hash
raster_hash
split
address_base
address_to_pixel_map_version
valid_fraction
byte_count
raster_width
representation_version
```

### 2.2 누수 검사

1. 같은 source/raster SHA-256은 한 sample만 남긴다.
2. 동일 family 안의 near duplicate 후보를 perceptual hash 또는 byte similarity로 묶는다.
3. 한 group은 하나의 split에만 들어간다.
4. class별 train/val/test 개수와 제외 이유를 기록한다.
5. valid_fraction만으로 예측하는 단변량 기준선을 다시 측정한다.
6. 단변량 기준선이 비정상적으로 높으면 valid-fraction matched subset을 별도 생성한다.

### 2.3 입력 표현

두 후보를 소규모 train/val pilot에서 비교한다.

| 표현 | 장점 | 위험 |
|---|---|---|
| compact-valid | 무효 0 shortcut 제거 | 원주소가 비연속이므로 lookup 필수 |
| mask-aware | 주소와 2D 위치 유지 | mask/validity 자체가 family shortcut이 될 수 있음 |

validation에서 shortcut과 분류 가능성을 함께 보고 하나를 primary로 동결한다. test 결과를
본 뒤 표현을 바꾸지 않는다.

## 3. 모델 학습

### 3.1 고정 후보

```yaml
primary_model: resnet18
reference_model: resnet50
initialization: imagenet_or_random_frozen_on_validation
loss: cross_entropy
optimizer: adamw
epochs_max: 30
early_stopping_patience: 5
seeds: [42, 43, 44]
amp: true
batch_size: measured_on_device
```

ImageNet initialization과 random initialization 중 하나를 validation에서 고르면 그 선택과
근거를 기록한다. 둘의 좋은 결과만 섞어 보고하지 않는다.

### 3.2 분류 sanity gate

- majority-class baseline보다 macro-F1이 0.10 이상 높아야 한다.
- 모든 test class의 support와 recall을 보고한다.
- accuracy만으로 모델을 선택하지 않고 validation macro-F1을 사용한다.
- test sample을 보고 epoch, augmentation, class weight를 바꾸지 않는다.

## 4. Grad-CAM 생성

각 모델과 seed에 대해 다음을 기록한다.

```text
checkpoint_sha256
target_layer
target_class: predicted / ground-truth
cam_upsampling
cam_normalization
positive_activation_policy
tie_breaking
```

주 분석은 ground-truth class score에 대한 CAM을 사용한다. predicted-class CAM은 분석가가
실제 추론에서 보게 되는 설명이므로 secondary로 보고한다. 오분류 sample을 제외하지 않는다.

## 5. 예산 mask

예산은 `{0.05, 0.10, 0.20, 0.40}`이다. CAM score가 높은 valid position부터 선택하며,
동점은 row-major index로 결정해 재현성을 보장한다.

비교 mask:

- Grad-CAM top-k
- random valid-position mask, sample당 20회
- entropy top-k
- front valid-position top-k

모든 방법은 정확히 같은 valid area를 사용한다. 연결요소 후처리로 면적이 달라지면 원 mask
평가와 박스 시각화를 분리한다.

## 6. 실제 재추론 평가

### 6.1 Deletion

선택 영역을 누적 제거하고 매 budget에서 다시 forward한다. 보고 값은 다음과 같다.

```text
delta_nll = NLL(masked) - NLL(original)
delta_p_y = p_y(original) - p_y(masked)
label_flip = argmax(original) != argmax(masked)
```

### 6.2 Keep-only

선택 영역 외부를 같은 fill policy로 대체하고 다시 forward한다.

```text
retained_p_y = p_y(keep_only) / max(p_y(original), epsilon)
retained_prediction = argmax(keep_only) == y
```

### 6.3 Fill

- primary: sample의 valid-byte histogram을 보존하는 stochastic fill
- robustness: local blur 또는 neighborhood-conditioned fill
- diagnostic only: zero fill

fill마다 동일 random seed schedule을 사용한다. Grad-CAM과 random 비교가 서로 다른 fill
draw를 보지 않도록 paired random state를 기록한다.

## 7. Sanity와 안정성

### 7.1 모델 randomization

- 정상 학습 checkpoint
- label을 shuffle해 학습한 checkpoint
- random weight checkpoint

각 조건에서 동일 sample의 CAM과 faithfulness 지표를 계산한다. 히트맵 유사도만 보지 않고
deletion/keep-only 효과 차이를 비교한다.

### 7.2 Seed 안정성

- CAM rank Spearman correlation
- top-10% IoU
- structure-region mass difference
- G1/G2 effect의 seed별 방향

세 seed 중 일부에서 효과가 반대면 평균 통과만으로 안정적 설명이라고 하지 않는다.

## 8. 구조 분석

구조 map이 복원되는 sample과 실패 sample을 모두 집계한다.

```text
structure_mapping_status
mapped_valid_bytes
unmapped_valid_bytes
region_name
region_start_address
region_end_address
cam_mass
selected_bytes_at_each_budget
```

구조별 enrichment는 다음처럼 계산한다.

```text
enrichment(region) =
  (CAM mass in region / total positive CAM mass)
  / (valid area in region / total valid area)
```

enrichment가 높아도 악성 의미를 뜻하지 않는다. family, packer, compiler, resource 크기의
shortcut일 수 있으므로 entropy, normalized position, valid_fraction과 함께 해석한다.

## 9. 통계 프로토콜

Primary hypotheses:

- H1: Grad-CAM top-10% deletion ΔNLL > matched random top-10%
- H2: Grad-CAM top-10% keep-only score > matched random top-10%

분석 단위는 파일이고 paired bootstrap 2,000회를 사용한다. H1/H2의 p-value에는 Holm
보정을 적용한다. effect size, 95% CI, eligible n을 모두 보고한다.

Secondary 분석:

- 다른 budget
- entropy/front 비교
- family별 결과
- correctly classified subset
- target class 선택 방식
- ResNet-50 및 MaleVis

Secondary 결과는 primary 실패를 대체하지 않는다.

## 10. 결과 레코드

per-sample 결과의 최소 필드는 다음과 같다.

```text
protocol_id, git_commit, dirty
dataset_revision, split_hash, sample_id, source_group
model, seed, checkpoint_sha256, target_layer
true_label, predicted_label, original_probability, original_nll
method, budget, fill, control_repeat
deleted_probability, deleted_nll
keep_only_probability, keep_only_nll
selected_valid_positions, selected_components
cam_runtime_ms, perturbation_runtime_ms, peak_vram_mib
structure_mapping_status
```

집계 표는 이 레코드에서 자동 생성한다. 논문 문장에 수치를 직접 입력했다면 감사 스크립트가
원자료와 대조할 수 있어야 한다.

## 11. 결과별 종료 규칙

| 결과 | 최종 논문 프레이밍 |
|---|---|
| H1·H2 통과 | 예산 제한 패밀리 판정 근거 후보 추출 |
| H1만 통과 | 필요한 영역은 찾지만 충분한 요약은 아님 |
| H2만 통과 | 작은 영역이 정보를 보존하지만 제거 효과는 약함 |
| 둘 다 실패 | 시각적 Grad-CAM의 충실성 한계 평가 |
| sanity 실패 | Grad-CAM을 설명으로 해석하지 않고 실패 원인 보고 |
| 구조 정합만 높음 | 구조 shortcut 가능성 분석 |

어떤 결과에서도 test 이후 threshold를 이동해 “성공”으로 만들지 않는다.

## 12. 실행 산출물 구조

```text
runs/xai-v4/XAI-V4.1-FROZEN/
├─ environment.json
├─ dataset/
│  ├─ manifest.json
│  ├─ split.json
│  └─ audit.json
├─ resnet18/
│  ├─ seed-42/
│  ├─ seed-43/
│  └─ seed-44/
├─ explanations/
├─ per_sample.parquet
├─ aggregate.json
├─ tables/
└─ figures/
```

`runs/`는 Git에서 제외한다. 논문에 사용한 작은 비민감 집계표와 figure만
`paper/v4-xai/results/`에 복사하며, 원본 바이트를 복원할 수 있는 이미지는 커밋하지 않는다.
