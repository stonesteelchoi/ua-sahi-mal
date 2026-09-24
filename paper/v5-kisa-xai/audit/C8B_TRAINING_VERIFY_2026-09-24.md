# C8b 학습 검증 판정 — 2026-09-24 (부분 판정)

## 범위와 증거

- 이번 열람: `runs/psa-orchestration/c8_training_verify_20260924.json`, `protocol/PSA_XAI_V1_0_DRAFT.yaml`, `TRAINING_HANDOFF_KO.md`.
- 검증기는 2026-09-24T01:55:16Z에 validation split 결과를 기록했다. `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`.
- 사용자 진술: sanity gate 기준은 **검증기 출력 열람 전** 기록했지만, **학습 완료 후** 정했다. 따라서 이 gate를 학습 전 사전 등록 기준이라고 주장하지 않는다. PROGRESS.md의 C8 사전 등록은 검증 출력 이전의 판정 기준이다.

## YAML 및 등록 기록 대조

YAML의 모델 계획은 ResNet-18, seed 42·43·44, 최대 30 epoch, early stopping patience 5, batch 512, validation macro-F1 checkpoint 선택이다. 초기화는 validation 선택 후 고정하며, 인수인계 기록은 ImageNet 선택을 기록한다. PROGRESS.md의 C8 기준은 ImageNet, 세 seed, batch 512, validation sanity gate다.

| run | 검증기에서 직접 확인한 값 | YAML·등록과의 대조 | 아직 필요한 원자료 확인 |
|---|---|---|---|
| 42 | `initialization=imagenet`; 19 epoch 실행, 최적 epoch 13; 경로 `seed42_imagenet_bs512` | seed·초기화 일치; 경로의 batch 표기는 512 | summary/checkpoint 설정 필드에서 seed·init·batch·최대 30 epoch·patience 5 확인 |
| 43 | `initialization=imagenet`; 11 epoch 실행, 최적 epoch 5; 경로 `seed43_imagenet_bs512` | seed·초기화 일치; 경로의 batch 표기는 512 | 동일 |
| 44 | `initialization=imagenet`; 17 epoch 실행, 최적 epoch 11; 경로 `seed44_imagenet_bs512` | seed·초기화 일치; 경로의 batch 표기는 512 | 동일 |

검증기 기록의 최종 epoch와 최적 epoch 차이가 각 5로 patience 5와 부합한다. 다만 이것만으로 실제 run 설정을 증명하지는 않는다. 검증기 JSON은 각 run의 `epochs_max`, `early_stopping_patience`, batch 값 자체를 제공하지 않는다. run별 summary 원자료를 다음 하위 청크에서 확인하기 전에는 설정 일치 판정을 완료하지 않는다.

## Validation sanity gate

| seed | macro-F1 | majority 대비 여유 | balanced accuracy | 정상 recall | 악성 recall | gate |
|---|---:|---:|---:|---:|---:|---|
| 42 | 0.953395 | 0.588592 | 0.952678 | 0.940433 | 0.964924 | 통과 |
| 43 | 0.946615 | 0.581811 | 0.945863 | 0.932271 | 0.959456 | 통과 |
| 44 | 0.952926 | 0.588123 | 0.953281 | 0.948909 | 0.957652 | 통과 |

세 run 모두 validation 29,933건에서 macro-F1 > majority+0.10, balanced accuracy ≥0.70, 양 class recall ≥0.60을 충족한다. 검증기 출력의 방향 일치도 true다. 검증기는 각 summary와 checkpoint의 SHA-256을 기록했지만, 이번에는 D: 원자료를 직접 다시 열어 검증하지 않았다.

## 판정과 경계

- **C8b 부분 통과:** 검증기 출력상 세 seed의 sanity gate와 방향 일치는 확인했다. run별 batch·epoch 상한·early stopping 설정 원자료 확인이 남아 C8b 전체 완료 판정은 보류한다.
- Validation은 초기화 및 checkpoint 선택에 사용했다. 위 validation 수치를 최종 성능으로 보고하지 않는다. 성능 보고는 전체 프로토콜 동결 후 held-out test를 **1회** 평가해 작성한다.
- `test_evaluation_performed=false`이며 test payload를 열지 않았다. 전체 프로토콜 동결 승인은 하지 않는다(`protocol_freeze_authorized=false`).
