# C9 동결 준비 기록 (2026-09-24)

상태: C9a 정책·era 분할·해시 판정까지 수행했다. 전체 프로토콜 동결 승인, V1.1 문서 생성, summary JSON 수정, held-out test 평가는 하지 않았다.

## YAML 정리 근거

- `split.counts`는 원본 분할 139,192 / 29,953 / 30,171로 유지하고, 래스터 중복 제외 후 학습 검증기 모집단 139,087 / 29,933 / 30,146을 별도 병기했다. 제외 150건의 분할별 수는 105 / 20 / 25이며, test 25건은 악성 24건과 정상 1건이다. 따라서 test 악성 17,431 → 17,407, 정상 12,740 → 12,739. 근거: `C8R_RETRAIN_ADJUDICATION_2026-09-24.md` C8r-c 및 `runs/psa-orchestration/c8_training_verify_retrain_20260924.json`.
- ImageNet 초기화 선택은 2026-09-20 인수인계 문서에 validation macro-F1 기준으로 기록돼 있다. 2026-09-24 C8 재학습도 이 초기화를 사용했다.
- 재학습 validation AUROC는 seed 42/43/44 순서로 0.9868352431 / 0.9873733953 / 0.9871156021이며 metadata-only group-disjoint AUROC 0.95보다 각각 높다. 평가 분할이 다르므로 이 차이는 통제된 우월성 증거가 아니다.
- `classification_sanity`의 네 기준은 첫 YAML 커밋 `c1262f094c3eac1bb94cda7166295fcf8fc16939` (2026-09-15 22:07:22 +09:00)에 이미 있었다. 이는 2026-09-24 재학습 전이다. 기존 9월 학습의 시작 전 등록 여부는 이 커밋만으로 확정하지 않는다.

## 사용자 `.venv` PowerShell 창 실행 명령

era 결과는 사용자 실행으로 이미 생성돼 C9a에서 보고서와 해시를 판정했다. 기존 split 및 원본 파일은 덮어쓰지 않는다. 재생성이 필요하면 아래 명령에서 새 경로를 지정한다.

```powershell
cd C:\research\ua-sahi-mal
$psaRoot = 'D:\secure-malware-data\psa'
$eraOut = Join-Path $psaRoot 'audit\era_stratified_freeze_20260924'
.\.venv\Scripts\python.exe scripts\psa_regenerate_era_split.py --main-split (Join-Path $psaRoot 'audit\split_manifest.csv') --matched-ids (Join-Path $psaRoot 'audit\matched_sample_ids_era.txt') --outdir $eraOut
Get-Content -Encoding utf8 (Join-Path $eraOut 'era_split_report.json')
$hashPaths = @(
  (Join-Path $psaRoot 'audit\split_manifest.csv'),
  (Join-Path $psaRoot 'rasters\raster_index.csv'),
  (Join-Path $psaRoot 'rasters\rasters_meta.json'),
  (Join-Path $psaRoot 'manifest_stage2.csv'),
  (Join-Path $eraOut 'split_manifest_era.csv')
)
foreach ($p in $hashPaths) { Get-FileHash -LiteralPath $p -Algorithm SHA256 | Select-Object Path, Hash | Format-List }
.\.venv\Scripts\python.exe scripts\psa_verify_freeze_prereqs.py --runs-dir (Join-Path $psaRoot 'runs\c8_retrain_20260924') --pilot-path (Join-Path $psaRoot 'runs\pilot_batch_size.json') --out runs\psa-orchestration\freeze_prereqs_recheck_20260924.json
Get-Content -Encoding utf8 runs\psa-orchestration\freeze_prereqs_recheck_20260924.json
```

해시 대조 기준 및 C9a 직접 재계산 결과는 아래 표와 같다. 다섯 값 모두 일치하므로 YAML의 `all_hashes_above_unchanged`에 대한 파일 해시 근거를 충족한다.

| 파일 | 직접 계산 SHA-256 | 기준 |
| --- | --- | --- |
| `audit/split_manifest.csv` | `843bcb8033205a5b37b420b93cdf940ed69dce58d73e5f3eaf942d7cc318099b` | YAML |
| `rasters/raster_index.csv` | `94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785` | YAML |
| `rasters/rasters_meta.json` | `c1398d0c74bc4bb1308ecdf91eb6426a4c558fb1de715df8749ae8fd3512a9e8` | YAML |
| `manifest_stage2.csv` | `3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414` | YAML |
| `audit/era_stratified_freeze_20260924/split_manifest_era.csv` | `fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a` | `era_split_report.json` |

## C9a 정책·era 판정

- 주 통계 단위는 `imphash_group`이다. 각 파일의 Grad-CAM 대 대조군 쌍체 차이를 같은 그룹 안에서 평균한 뒤 그룹을 재표집한다. `file` 단위 쌍체 부트스트랩은 사전 선언한 sensitivity analysis다.
- robustness fill은 `local_median`으로 고정했다. 현재 PSA XAI 구현에 창 크기 지정이 없으므로 창 크기는 미해결이며, 제안값은 홀수 크기 `5×5`다. 실제 구현 전에 이를 확정해야 한다.
- `D:\secure-malware-data\psa\audit\era_stratified_freeze_20260924\era_split_report.json`은 70,938건(train 49,622 / val 10,662 / test 10,654), 32,153그룹을 보고하고 split 해시는 위 재계산값과 일치한다. 작은 악성 PE32+ 층에서 70/15/15 목표 편차가 크다: mean_pool 434건은 train 67.97%, test 17.05%; nearest_repetition 32건은 train 62.5%, test 21.875%다.
- 보고서의 `existing_main_models_can_evaluate_full_era_test_as_unseen=false`를 유지한다. era test의 5,774건은 main 학습 그룹에, 3,212건은 main validation에 겹친다. 1,668건만 main test와 교차하므로 기존 main 모델의 전체 era test 미관측 성능 주장은 허용하지 않는다.
- YAML과 `TRAINING_HANDOFF_KO.md`에는 era 부분집합의 CNN/XAI 평가 계획이 선택·고정돼 있지 않다. 미해결 선택지는 (1) era 전용 3 seed 학습, (2) main∩era test 1,668건 평가, (3) V1.2 exploratory 지정이다. 선택 전 era 결과를 확증 성능으로 해석하지 않는다.

`psa_verify_freeze_prereqs.py`의 기대 해시는 C8 재학습 체크포인트 세 개로 갱신했다. 위 사용자 명령은 재학습 run과 별도 pilot 파일을 지정하고 새 JSON에 결과를 쓴다. 이 세션에서 `.venv` 검증기를 실행하지 않았으며 기존 summary JSON도 수정하지 않았다. 검증기의 `remaining_blocker`는 `P2_CENSUS_ADJUDICATION_2026-09-24.md`의 전체 프로토콜 동결 승인 대기를 인용한다.
