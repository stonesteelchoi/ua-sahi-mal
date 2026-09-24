# C8r 재학습 최종 판정

상태: C8r 종결. 재학습 validation sanity gate 통과. 전체 프로토콜 동결은 승인하지 않는다.

## 직접 확인한 증거

- 기존 검증: `runs/psa-orchestration/c8_training_verify_20260924.json` (`verified_at` 2026-09-24T01:55:16Z).
- 재학습 검증: `runs/psa-orchestration/c8_training_verify_retrain_20260924.json` (`verified_at` 2026-09-24T06:54:18Z).
- 재학습 provenance: `D:\secure-malware-data\psa\runs\c8_retrain_20260924\run_provenance.txt`에 `HEAD=62a15542f14b94b16271dbac8defbe99ee57b3ca`, `psa_train.py train --batch-size 512 --init imagenet --epochs-max 30 --patience 5 --seed {42,43,44}`가 기록돼 있다. 현재 저장소 HEAD는 `541ac584c8ec2f18ed80b614ef56dcc60b001bf4`이므로 provenance의 커밋을 재학습 시점 코드로 인용한다. seed별 로그 직접 대조 결과는 아래에 기록했다.

## 두 검증 결과 비교

두 JSON의 `counts`, `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`, 각 seed의 initialization, epochs, best epoch, validation macro-F1, balanced accuracy, 양 class recall, validation n, majority 대비 margin, sanity gate 및 네 가지 mean은 정확히 일치한다. seed별 수치는 다음과 같다.

| seed | best epoch / epochs ran | macro-F1 | balanced accuracy | benign recall | malicious recall | margin |
| --- | --- | --- | --- | --- | --- | --- |
| 42 | 13 / 19 | 0.9533953478763282 | 0.952678359741171 | 0.9404332129963899 | 0.9649235064859519 | 0.5885918507198898 |
| 43 | 5 / 11 | 0.946614595516273 | 0.9458633790311683 | 0.9322712290064354 | 0.9594555290559014 | 0.5818110983598347 |
| 44 | 11 / 17 | 0.952926201081972 | 0.9532806896754671 | 0.9489091194474965 | 0.9576522599034378 | 0.5881227039255337 |

두 JSON 자체는 동일하지 않다. 새 JSON에는 AUROC가 추가되고 `verified_at`, 학습·검증 시간, run 경로, summary 및 checkpoint SHA-256이 다르다. 따라서 위의 공통 validation 지표가 완전히 일치한다는 뜻으로 한정한다.

## Gate 및 모델 지정

PROGRESS.md의 C8 gate는 **이번 재학습 전에 등록된 기준**이다. 이전 run에 소급하지 않는다. 재학습 검증 JSON에서 세 seed 모두 `sanity_gate_passed=true`, `all_seeds_passed=true`, `direction_agreement=true`이며 모든 수치가 C8 기준을 넘는다. 검증 결과상 C8 sanity gate 통과다.

C9 후보 모델은 기존 `D:\secure-malware-data\psa\runs\seed*_imagenet_bs512`의 best.pt를 대체하는 아래 재학습 체크포인트 세 개다. 파일 존재를 확인했으며 SHA-256은 재학습 검증 JSON이 보고한 값이다.

| seed | 재학습 best.pt | SHA-256 |
| --- | --- | --- |
| 42 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed42_imagenet_bs512\best.pt` | `291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f` |
| 43 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed43_imagenet_bs512\best.pt` | `4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56` |
| 44 | `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed44_imagenet_bs512\best.pt` | `62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c` |

## 학습 로그와 provenance 대조

`D:\secure-malware-data\psa\runs\c8_retrain_20260924\train_seed{42,43,44}.log`를 각각 직접 열었다. 세 로그 모두 첫 줄에 동일 분할 집계(train 139,087 / val 29,933 / test 30,146)를 출력한다. 마지막 부분은 각각 `early stop at epoch 18/10/16 (patience 5)`, 최적 epoch 13/5/11, `seed42/43/44_imagenet_bs512\best.pt` 경로와 위 표의 SHA-256을 출력한다. 따라서 로그에서 직접 출력된 patience 5, seed별 출력 경로·해시, 종료 epoch은 provenance와 일치한다. 경로의 `imagenet_bs512`는 init·batch의 태그이며 실제 init·batch 값은 검증기가 각 `summary.json`의 `init=imagenet`, `batch_size=512`, `seed=42/43/44`와 체크포인트 해시를 대조해 확인했다. 로그에는 실행 명령이나 `--epochs-max 30` 및 초기화·batch 인자가 별도 줄로 출력되지 않는다. 따라서 로그만으로 그 인자의 직접 일치를 주장하지 않는다. epochs 30은 provenance의 실행 명령 및 검증기에서 허용한 상한이고, 세 run 모두 30 이전에 patience 5로 멈췄다. provenance 명령 자체의 진위는 셸 이력과 대조하지 못했다.

## 기존·재학습 best.pt 텐서 동일성 확인 명령

사용자 PowerShell의 정상 동작하는 `.venv`에서 아래 한 줄을 실행하면 seed마다 기존 run과 재학습 run의 `model` state_dict에 대해 key 집합과 모든 가중치 텐서의 정확한 값 동일성을 출력한다. 체크포인트 전체 바이트·메타데이터 동일성과는 다른 비교다. Codex 세션의 `.venv` 런처는 base Python 경로 문제로 동작하지 않아 이 명령의 결과를 확인하지 않았으며, 동일하다고 판정하지 않는다.

```powershell
42,43,44 | ForEach-Object { .\.venv\Scripts\python.exe -c 'import sys,torch,pathlib; s=sys.argv[1]; root=pathlib.Path(sys.argv[2]); old=torch.load(root/f"seed{s}_imagenet_bs512"/"best.pt",map_location="cpu",weights_only=True)["model"]; new=torch.load(root/"c8_retrain_20260924"/f"seed{s}_imagenet_bs512"/"best.pt",map_location="cpu",weights_only=True)["model"]; print(f"seed{s}: identical={old.keys()==new.keys() and all(torch.equal(old[k],new[k]) for k in old)}")' $_ 'D:\secure-malware-data\psa\runs' }
```

## YAML의 test 악성 수 차이

`protocol/PSA_XAI_V1_0_DRAFT.yaml`의 `internal_test_malicious_n: 17431`은 중복 제외 전 수다. `D:\secure-malware-data\psa\audit\split_manifest.csv`와 `D:\secure-malware-data\psa\rasters\raster_index.csv`를 각각 집계하면 두 파일 모두 test 악성 17,431건, test 정상 12,740건이다. 두 파일의 sample_id 차집합은 0건이다. 검증기 `scripts/psa_verify_training.py`의 `dataset_counts`는 `rasters/raster_duplicate_groups.csv`에서 같은 `raster_sha256`의 두 번째 이후 sample_id를 제외한다. 실제 중복 목록 266행에서 제외 ID 150개는 train 악성 105, val 악성 20, test 악성 24, test 정상 1개다. 따라서 test 악성 `17,431 - 24 = 17,407`, test 정상 `12,740 - 1 = 12,739`로 검증기 출력과 정확히 일치한다. YAML은 요청에 따라 수정하지 않았다. C9의 실제 평가 모집단을 기술할 때는 중복 제외 후 eligible n과 제외 규칙을 명시해야 한다.

## 최종 판정

C8r은 재학습 provenance, seed별 로그에서 확인 가능한 인자·출력, 검증기 gate, YAML 수 차이의 근거를 기록해 종결한다. 세 재학습 체크포인트를 C9 후보로 유지한다. 기존·재학습 모델의 가중치 텐서 동일 여부는 위 사용자 실행 명령의 결과 전에는 미확인이다. C8 validation sanity gate 통과는 held-out test 성능 판정이나 전체 프로토콜 동결 승인을 뜻하지 않는다. C9 및 test payload 접근 전 사용자 동결 승인이 필요하다.
