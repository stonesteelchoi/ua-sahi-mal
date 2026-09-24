# C9 동결 준비 기록 (2026-09-24)

상태: 준비만 수행했다. 전체 프로토콜 동결 승인, V1.1 문서 생성, summary JSON 수정, held-out test 평가는 하지 않았다.

## YAML 정리 근거

- `split.counts`는 원본 분할 139,192 / 29,953 / 30,171로 유지하고, 래스터 중복 제외 후 학습 검증기 모집단 139,087 / 29,933 / 30,146을 별도 병기했다. 제외 150건의 분할별 수는 105 / 20 / 25이며, test 25건은 악성 24건과 정상 1건이다. 따라서 test 악성 17,431 → 17,407, 정상 12,740 → 12,739. 근거: `C8R_RETRAIN_ADJUDICATION_2026-09-24.md` C8r-c 및 `runs/psa-orchestration/c8_training_verify_retrain_20260924.json`.
- ImageNet 초기화 선택은 2026-09-20 인수인계 문서에 validation macro-F1 기준으로 기록돼 있다. 2026-09-24 C8 재학습도 이 초기화를 사용했다.
- 재학습 validation AUROC는 seed 42/43/44 순서로 0.9868352431 / 0.9873733953 / 0.9871156021이며 metadata-only group-disjoint AUROC 0.95보다 각각 높다. 평가 분할이 다르므로 이 차이는 통제된 우월성 증거가 아니다.
- `classification_sanity`의 네 기준은 첫 YAML 커밋 `c1262f094c3eac1bb94cda7166295fcf8fc16939` (2026-09-15 22:07:22 +09:00)에 이미 있었다. 이는 2026-09-24 재학습 전이다. 기존 9월 학습의 시작 전 등록 여부는 이 커밋만으로 확정하지 않는다.

## 사용자 `.venv` PowerShell 창 실행 명령

기존 split 및 원본 파일은 덮어쓰지 않는다. era 결과 경로가 이미 있으면 새 경로를 지정한다. 아래 명령의 출력과 해시를 후속 판정에 기록한다.

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
$hashPaths | Get-FileHash -Algorithm SHA256 | Select-Object Path, Hash | Format-List
.\.venv\Scripts\python.exe scripts\psa_verify_freeze_prereqs.py --runs-dir (Join-Path $psaRoot 'runs') --out runs\psa-orchestration\freeze_prereqs_recheck_20260924.json
Get-Content -Encoding utf8 runs\psa-orchestration\freeze_prereqs_recheck_20260924.json
```

해시 대조 기준: main split `843bcb8033205a5b37b420b93cdf940ed69dce58d73e5f3eaf942d7cc318099b`, raster index `94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785`, rasters meta `c1398d0c74bc4bb1308ecdf91eb6426a4c558fb1de715df8749ae8fd3512a9e8`, stage2 manifest `3dc0bd7fb42935692462013f716bbd8ccd339b20bb436289aa93e78852b17414`. Era split은 새 해시를 보고서 `split_sha256`과 대조한다.

주의: 현재 `psa_verify_freeze_prereqs.py`는 기존 `runs`의 체크포인트 세 해시를 고정해 검증한다. C8 재학습 체크포인트는 C8r 검증 JSON과 판정 문서의 해시가 별도 근거다. 이 명령의 성공을 재학습 체크포인트 직접 검증으로 해석하지 않는다.
