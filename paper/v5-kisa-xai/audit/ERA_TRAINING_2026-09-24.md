# Era 학습·검증 판정 (2026-09-24)

## 범위와 근거

- Run: `D:\secure-malware-data\psa\runs\era_20260924`. `run_provenance.txt`와 `training_verify.json`을 확인하고, 세 체크포인트와 두 스크립트의 SHA-256을 직접 재계산했다. 학습 로그·seed별 `summary.json`의 내용은 이 판정에서 별도로 열어 대조하지 않았다.
- 검증 JSON 저장소 복사본: `runs/psa-orchestration/era_training_verify_20260924.json`, SHA-256 `9b8e23b87a7beca2d8942cf4fd9dfd4cfba5827dac2c07423d5f6110c6b6c66b`.
- Provenance: `era_code_head=8323ab7501ad4763fb0436121a9466bf50720016` (현재 HEAD와 일치), main 재학습 커밋 `62a15542f14b94b16271dbac8defbe99ee57b3ca`. `psa_train.py` SHA-256 `629566656893b7f9e2aa0b8a0d4fce5c252b27318a27b2bea8c95c15340611fa`; `psa_verify_training.py` SHA-256 `7ed639f3673fd16c4cf2f7c7eeeb5547fe73466813a694a35536ea994190add9`. 기록값과 직접 계산값이 일치한다. Era manifest 기록 SHA-256은 `fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a`이며 이 판정에서 재계산하지 않았다.
- 기록된 설정: ResNet-18, ImageNet 초기화, batch 512, epoch 상한 30, patience 5, seed 42·43·44, validation macro-F1 checkpoint 선택, workers 4. 검증 JSON은 `split=validation`, `test_evaluation_performed=false`이다.

## 유효 건수와 sanity gate

Era 분할 원 건수는 train 49,622 / validation 10,662 / test 10,654, 합계 70,938이다. 검증 JSON의 raster 중복 제외 후 유효 건수는 각각 **49,593 / 10,660 / 10,652**, 합계 70,905이며 제외는 **33건**(29/2/2)이다. Test 건수는 검증기의 목록 계수로만 사용했고 test payload나 test 성능에 접근하지 않았다.

| Seed | 최적 epoch (0 기준) | Val macro-F1 | Val balanced accuracy | 양 class recall (benign / malicious) | Val AUROC | Majority 대비 F1 margin | 체크포인트 SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---|
| 42 | 7 | 0.912082 | 0.912081 | 0.925628 / 0.898534 | 0.961095 | 0.578415 | `a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6` |
| 43 | 3 | 0.910693 | 0.910690 | 0.913451 / 0.907929 | 0.957995 | 0.577026 | `f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf` |
| 44 | 6 | 0.903259 | 0.903432 | 0.867179 / 0.939684 | 0.958046 | 0.569593 | `da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1` |

검증기 판정은 `all_seeds_passed=true`, `direction_agreement=true`이다. 세 seed 모두 사전 등록 기준인 majority macro-F1 +0.10, balanced accuracy ≥0.70, 양 class recall ≥0.60을 충족한다. 체크포인트 SHA-256 세 값은 각 `seed{42,43,44}_imagenet_bs512/best.pt` 파일의 직접 재계산값과 검증 JSON의 기록값이 일치한다. 이 세 체크포인트를 **전체 프로토콜 동결 후 era test 1회 평가용 모델**로 지정한다.

## 비교의 해석 범위

Era metadata-only 기준선은 **AUROC 0.90–0.91**이다. 검증기 JSON의 `metadata_baseline_auroc=0.95`는 main용 고정값이며 era 기준선으로 해석하지 않는다. Era CNN validation AUROC는 0.9580–0.9611이고 metadata 기준선보다 수치상 높지만, 평가 분할과 절차가 다르므로 통제된 성능 차이나 우월성의 근거가 아니다. Macro-F1과 AUROC도 직접 비교하지 않는다.

Main 재학습 validation AUROC 0.986835/0.987373/0.987116에 비해 era validation AUROC는 같은 seed 순서로 0.961095/0.957995/0.958046이다. seed별 수치 차이(era − main)는 −0.025740/−0.029379/−0.029070이다. 서로 다른 데이터 분할에서 얻은 **기술 통계**이며, 통제된 성능 하락이나 일반화 차이로 추론하지 않는다.

전체 프로토콜 동결은 승인하지 않았고 era test 평가도 수행하지 않았다. C9b-a의 합성 CLI 회귀 테스트 출력 확인은 별도 미해결 항목이다.
