# KISA-XAI v5 실험 프로토콜

**Protocol:** `KISA-XAI-V5.0-DRAFT`
**Task:** static Windows PE binary malware detection
**Primary candidate:** `KISA_CISC2017_datachallenge_Malwares.01`
**External candidate:** labeled PE subset of `KISA-datachallenge2018-Malwares.03`
**Primary model:** ResNet-18
**Primary XAI:** Grad-CAM
**Primary budget:** 10% of unique source bytes
**Status:** access-gated pre-results design

## 1. 동결 전 P0 게이트

- [ ] 데이터 이용조건과 논문 보고 가능 범위 기록
- [ ] source archive 및 label file SHA-256 기록
- [ ] archive 파일 수와 공식 설명의 차이 설명
- [ ] file-label join rate 99% 이상
- [ ] 정상·악성별 file type과 PE32/PE32+ 수 집계
- [ ] parser failure와 제외 사유 저장
- [ ] 2018/2019 suffix 및 dataset marker 전수 감사
- [ ] exact duplicate와 near-duplicate group 생성
- [ ] metadata-only shortcut baseline 실행
- [ ] split manifest와 split hash 생성
- [ ] image representation과 pixel-offset map 왕복 검사
- [ ] 모델, target layer, seed, fill, budget, 지표, 검정 동결

P0를 통과한 커밋에만 `KISA-XAI-V5.1-FROZEN` 태그를 부여한다.

## 2. 데이터 revision과 manifest

revision 이름은 다음 형식을 사용한다.

```text
kisa-<challenge-year>-pe-<suffix-policy>-<split-version>
예: kisa-2017-pe-native-split01
예: kisa-2018-pe-strip-kisa4-split01
```

최소 manifest 필드는 다음과 같다.

```text
dataset_revision, sample_id, original_filename
source_archive_hash, source_sha256, processed_sha256
label, label_source, label_join_status
magic_type, pe_kind, machine, parser_status, parser_disagreement
file_size, section_count, executable_section_bytes
overlay_bytes, certificate_bytes, signed, packer_hint, compiler_hint
suffix_present, suffix_policy
exact_duplicate_group, near_duplicate_group, split
representation_version, raster_hash, map_hash
```

공개 결과에서는 원본 filename과 source hash를 가명화하며, 내부 ledger에서만 archive
검증에 사용한다.

## 3. eligibility와 분할

주 분석 eligibility는 다음을 모두 만족한 파일이다.

1. label이 `0` 또는 `1`로 확정됨
2. PE32 또는 PE32+로 파싱됨
3. source bytes와 PE 구조 map이 일치함
4. suffix policy가 dataset revision과 일치함
5. exact duplicate 대표 sample임

near-duplicate group을 train/val/test 단위로 분리한다. 기본 비율은 70/15/15이며 label과
PE32/PE32+를 층화 변수로 사용한다. test ID 목록과 외부 archive는 protocol freeze 전
hash만 기록하고 분석 코드에서 잠근다.

## 4. 입력 표현

`interval-binned-v1`은 파일 전체를 224×224 grayscale로 변환한다. 각 pixel은 원본의
half-open file-offset interval과 연결된다. 긴 파일은 연속 interval mean pooling, 짧은
파일은 nearest repetition을 사용한다. 다음 불변식을 검사한다.

- 모든 source offset이 하나 이상의 image pixel과 연결됨
- 모든 image pixel이 유효 source interval과 연결됨
- 전체 pixel interval의 합집합이 `[0, file_size)`와 일치함
- CAM 선택 interval의 합집합 길이가 요청 예산을 초과할 때 마지막 interval을 기록함
- raster와 map의 SHA-256이 manifest에 존재함

## 5. 누수와 confounder 감사

다음 단변량·다변량 기준선을 train/val에서 실행한다.

- file size only
- file type/PE kind only
- normalized header, overlay, certificate size
- parser success와 section count
- signed, packer hint, compiler hint
- 위 변수를 합친 logistic regression
- 256-bin byte histogram logistic regression

metadata-only AUROC가 0.90 이상이면 label-source 관계를 분석한다. matching이나
stratification 후에도 효과가 유지되면 주 결론을 `malicious semantics`가 아니라
`dataset-specific static discrimination`으로 제한한다.

## 6. 모델 학습

```yaml
model: resnet18
input: 1x224x224
initialization: imagenet-adapted-or-random-selected-on-validation
loss: frozen_before_test
optimizer: adamw
epochs_max: 30
early_stopping_patience: 5
seeds: [42, 43, 44]
amp: true
batch_size: measured_on_rtx5070_8gb
selection_metric: validation_macro_f1
```

batch size는 고정 가정이 아니라 측정값으로 기록한다. 자연영상 flip, rotation, crop,
color jitter를 사용하지 않는다.

## 7. 분류 sanity gate

- validation macro-F1 > majority macro-F1 + 0.10
- validation balanced accuracy ≥ 0.70
- 두 class recall ≥ 0.60
- 모든 seed에서 학습 붕괴가 없음

실패하면 XAI를 주 결과로 실행하지 않고 label, representation, leakage를 먼저 감사한다.

## 8. CAM과 선택 예산

- target layer: ResNet-18 final convolution block, freeze 전 정확한 module path 기록
- primary target: malicious logit on all malicious test samples
- secondary target: predicted class 및 benign logit
- upsampling: bilinear, `align_corners=False`
- budgets: 0.05, 0.10, 0.20, 0.40 of unique source bytes
- tie-breaking: score descending, then row-major pixel index
- whole-interval overshoot: 요청값과 실제 선택 바이트 비율을 모두 기록하고 모든 대조군을
  Grad-CAM의 실제 선택 바이트 수에 맞춤
- empty positive CAM: sample을 제외하지 않고 `cam_empty=true`로 기록

대조군은 uniform random 20회, front, entropy, structure-matched random 20회이다.
structure-matched random을 primary comparator로 둔다.

## 9. perturbation과 재추론

두 fill의 효과 방향 합의를 요구한다.

1. primary: structure-conditioned resampling fill
2. robustness: local median/blur fill
3. diagnostic: zero fill

Grad-CAM과 random 대조군은 같은 sample·budget·fill random state를 공유한다.

```text
deletion_delta_nll = nll_deleted - nll_original
deletion_delta_p = p_mal_original - p_mal_deleted
keep_retained_p = p_mal_keep / max(p_mal_original, epsilon)
keep_retained_label = prediction_keep == malicious
```

## 10. primary hypotheses와 통계

- H1: Grad-CAM 10% deletion ΔNLL > structure-matched random 10%
- H2: Grad-CAM 10% keep-only malicious score > structure-matched random 10%

파일 또는 near-duplicate group paired bootstrap 2,000회를 사용한다. H1/H2에 Holm 보정을
적용하고 effect, 95% CI, adjusted p, eligible n을 보고한다. 세 seed 결과를 각각 제시한다.

5/20/40%, uniform/front/entropy, subgroup, correctly detected subset은 secondary이다.

## 11. explanation sanity와 구조 분석

- trained checkpoint
- label-shuffled checkpoint
- random-weight checkpoint

각 조건에서 CAM 유사도뿐 아니라 deletion/keep-only effect를 비교한다. 구조별 positive
CAM mass와 area-normalized enrichment를 header, executable, non-executable, certificate,
overlay, unknown으로 집계한다.

## 12. 외부 평가

KISA 2018 labeled PE에는 내부에서 동결한 model, threshold, representation, CAM, budget,
fill과 통계를 그대로 적용한다. 외부 데이터로 조정하지 않는다. challenge year를 sample
수집일로 간주하지 않는다.

외부 replication 기준은 다음과 같다.

- internal H1/H2 효과 방향 유지
- seed별 방향 보고
- 95% CI와 effect attenuation 보고
- AUROC, AUPRC, balanced accuracy, ECE의 internal 대비 변화 보고

## 13. 결과 레코드

```text
protocol_id, git_commit, dirty, dataset_revision, split_hash
sample_id, near_duplicate_group, label, pe_kind, file_size
model, seed, checkpoint_sha256, target_layer
original_logit, original_probability, original_nll, prediction
method, budget, fill, control_repeat
selected_source_bytes, selected_intervals, selected_components
deleted_probability, deleted_nll, keep_probability, keep_nll
cam_runtime_ms, perturbation_runtime_ms, peak_vram_mib
header_mass, executable_mass, non_executable_mass
certificate_mass, overlay_mass, unknown_mass
```

## 14. 종료 규칙

| 결과 | 허용 결론 |
|---|---|
| H1·H2·sanity 통과 | 충실한 악성 판정 근거 후보 |
| H1만 통과 | 필요성만 확인 |
| H2만 통과 | 충분성만 확인 |
| 모두 실패 | Grad-CAM 충실성 한계 |
| metadata shortcut 지배 | KISA 데이터셋 편향 평가 |
| 외부 실패 | 교차연도 일반화 한계 |
| P0 실패 | empirical paper 중단, 설계만 보존 |

test 이후 바꾼 분석은 `KISA-XAI-V5.2-EXPLORATORY`로 기록한다.
