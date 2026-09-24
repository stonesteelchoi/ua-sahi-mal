# C8r 재학습 재판정 — 진행 기록

상태: C8r-a 완료. C8r 전체 판정은 로그 인자 직접 대조와 YAML count 원인 확인 후 확정한다. 전체 프로토콜 동결은 승인하지 않는다.

## 직접 확인한 증거

- 기존 검증: `runs/psa-orchestration/c8_training_verify_20260924.json` (`verified_at` 2026-09-24T01:55:16Z).
- 재학습 검증: `runs/psa-orchestration/c8_training_verify_retrain_20260924.json` (`verified_at` 2026-09-24T06:54:18Z).
- 재학습 provenance: `D:\secure-malware-data\psa\runs\c8_retrain_20260924\run_provenance.txt`에 `HEAD=62a15542f14b94b16271dbac8defbe99ee57b3ca`, `psa_train.py train --batch-size 512 --init imagenet --epochs-max 30 --patience 5 --seed {42,43,44}`가 기록돼 있다. 현재 저장소 HEAD는 `541ac584c8ec2f18ed80b614ef56dcc60b001bf4`이므로 provenance의 커밋을 재학습 시점 코드로 인용한다. seed별 `train_seed*.log`는 다음 하위 청크에서 직접 확인한다.

## 두 검증 결과 비교

두 JSON의 `counts`, `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`, 각 seed의 initialization, epochs, best epoch, validation macro-F1, balanced accuracy, 양 class recall, validation n, majority 대비 margin, sanity gate 및 네 가지 mean은 정확히 일치한다. seed별 수치는 다음과 같다.

| seed | best epoch / epochs ran | macro-F1 | balanced accuracy | benign recall | malicious recall | margin |
| --- | --- | --- | --- | --- | --- | --- |
| 42 | 13 / 19 | 0.9533953478763282 | 0.952678359741171 | 0.9404332129963899 | 0.9649235064859519 | 0.5885918507198898 |
| 43 | 5 / 11 | 0.946614595516273 | 0.9458633790311683 | 0.9322712290064354 | 0.9594555290559014 | 0.5818110983598347 |
| 44 | 11 / 17 | 0.952926201081972 | 0.9532806896754671 | 0.9489091194474965 | 0.9576522599034378 | 0.5881227039255337 |

두 JSON 자체는 동일하지 않다. 새 JSON에는 AUROC가 추가되고 `verified_at`, 학습·검증 시간, run 경로, summary 및 checkpoint SHA-256이 다르다. 따라서 위의 공통 validation 지표가 완전히 일치한다는 뜻으로 한정한다.

## Gate 및 모델 지정

PROGRESS.md의 C8 gate는 **이번 재학습 전에 등록된 기준**이다. 이전 run에 소급하지 않는다. 재학습 검증 JSON에서 세 seed 모두 `sanity_gate_passed=true`, `all_seeds_passed=true`, `direction_agreement=true`이며 모든 수치가 C8 기준을 넘는다. 검증 결과상 C8 sanity gate 통과다. 다만 로그 인자 직접 확인까지 마친 뒤 C8r 최종 판정을 닫는다.

C9 후보 모델은 기존 `D:\secure-malware-data\psa\runs\seed*_imagenet_bs512`의 best.pt를 대체하는 아래 재학습 체크포인트 세 개다. 파일 존재를 확인했으며 SHA-256은 재학습 검증 JSON이 보고한 값이다.

| seed | 재학습 best.pt | SHA-256 |
| --- | --- | --- |
| 42 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed42_imagenet_bs512\best.pt` | `291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f` |
| 43 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed43_imagenet_bs512\best.pt` | `4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56` |
| 44 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed44_imagenet_bs512\best.pt` | `62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c` |

미해결: seed별 로그 인자 직접 대조, 두 체크포인트 가중치 텐서 동일성 비교용 사용자 명령, YAML `internal_test_malicious_n=17431`과 검증기 test malicious `17407`의 차이 원인. YAML은 수정하지 않는다.
