# C8b 학습 검증 판정 — 2026-09-24 (C8b-b 보완)

## 범위와 증거

- C8b-a 열람: `runs/psa-orchestration/c8_training_verify_20260924.json`, `protocol/PSA_XAI_V1_0_DRAFT.yaml`, `TRAINING_HANDOFF_KO.md`. C8b-b에서 `D:\secure-malware-data\psa\runs\seed{42,43,44}_imagenet_bs512\summary.json` 3개를 직접 확인했다.
- 검증기는 2026-09-24T01:55:16Z에 validation split 결과를 기록했다. `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`.
- 사용자 진술: sanity gate 기준은 **검증기 출력 열람 전** 기록했지만, **학습 완료 후** 정했다. 따라서 이 gate를 학습 전 사전 등록 기준이라고 주장하지 않는다. PROGRESS.md의 C8 사전 등록은 검증 출력 이전의 판정 기준이다.

## YAML 및 등록 기록 대조

YAML의 모델 계획은 ResNet-18, seed 42·43·44, 최대 30 epoch, early stopping patience 5, batch 512, validation macro-F1 checkpoint 선택이다. 초기화는 validation 선택 후 고정하며, 인수인계 기록은 ImageNet 선택을 기록한다. PROGRESS.md의 C8 기준은 ImageNet, 세 seed, batch 512, validation sanity gate다.

| run | summary 원자료에서 확인한 값 | YAML·등록과의 대조 | summary에 없는 설정 |
|---|---|---|---|
| 42 | `seed=42`, `init=imagenet`, `batch_size=512`, `epochs_ran=19`, `best.epoch=13`; history 0~18 | seed·초기화·batch 일치 | `epochs_max`, `early_stopping_patience` |
| 43 | `seed=43`, `init=imagenet`, `batch_size=512`, `epochs_ran=11`, `best.epoch=5`; history 0~10 | seed·초기화·batch 일치 | 동일 |
| 44 | `seed=44`, `init=imagenet`, `batch_size=512`, `epochs_ran=17`, `best.epoch=11`; history 0~16 | seed·초기화·batch 일치 | 동일 |

세 summary의 `history.epoch`은 **0 기준**이며, `epochs_ran`은 마지막 epoch 번호가 아니라 실행 횟수다. 따라서 마지막 번호는 각각 `19-1=18`, `11-1=10`, `17-1=16`이다. `epochs_ran-best.epoch`은 각각 `19-13=6`, `11-5=6`, `17-11=6`으로, 최적 epoch 자체를 포함해 센 값이다. 최적 epoch **이후** 실행된 epoch 수는 `(19-1)-13=5`, `(11-1)-5=5`, `(17-1)-11=5`다. 각 history에서 최적 epoch 뒤의 5회(42: 14~18, 43: 6~10, 44: 12~16)는 validation macro-F1 최고값을 갱신하지 않았다. 그러므로 관측된 종료 시점은 개선 없는 epoch 5회 후 멈추는 patience 5 동작과 산술적으로 부합한다. C8b-a의 “차이가 각 5”는 실행 횟수와 0 기준 번호를 혼동한 오류로 정정한다.

다만 세 summary에는 `epochs_max`와 `early_stopping_patience` 설정 필드가 없다. 실행 횟수는 모두 30 미만이고 종료 양상은 patience 5와 일치하지만, 이 원자료만으로 실제 설정값 `epochs_max=30`, `early_stopping_patience=5`를 확증할 수는 없다.

## Validation sanity gate

| seed | macro-F1 | majority 대비 여유 | balanced accuracy | 정상 recall | 악성 recall | gate |
|---|---:|---:|---:|---:|---:|---|
| 42 | 0.953395 | 0.588592 | 0.952678 | 0.940433 | 0.964924 | 통과 |
| 43 | 0.946615 | 0.581811 | 0.945863 | 0.932271 | 0.959456 | 통과 |
| 44 | 0.952926 | 0.588123 | 0.953281 | 0.948909 | 0.957652 | 통과 |

세 run 모두 validation 29,933건에서 macro-F1 > majority+0.10, balanced accuracy ≥0.70, 양 class recall ≥0.60을 충족한다. 검증기 출력의 방향 일치도 true다. 검증기는 각 summary와 checkpoint의 SHA-256을 기록했지만, 이번에는 D: 원자료를 직접 다시 열어 검증하지 않았다.

## 판정과 경계

- **C8b 부분 통과:** 검증기 출력상 세 seed의 sanity gate와 방향 일치를 확인했고, run summary에서 seed·ImageNet 초기화·batch 512와 patience 5에 부합하는 종료 양상을 확인했다. `epochs_max=30`과 `early_stopping_patience=5`의 실제 설정 원자료가 summary에 없어 C8b 전체 설정 일치 판정은 보류한다.
- Validation은 초기화 및 checkpoint 선택에 사용했다. 위 validation 수치를 최종 성능으로 보고하지 않는다. 성능 보고는 전체 프로토콜 동결 후 held-out test를 **1회** 평가해 작성한다.
- `test_evaluation_performed=false`이며 test payload를 열지 않았다. 전체 프로토콜 동결 승인은 하지 않는다(`protocol_freeze_authorized=false`).
