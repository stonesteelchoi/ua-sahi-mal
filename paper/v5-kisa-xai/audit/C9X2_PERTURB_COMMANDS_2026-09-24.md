# C9x-2 정적 perturb 실행 명령 (미실행)

`psa_gradcam.py`를 수정했으므로 C9x-1에 적은 명령으로 여섯 Grad-CAM ledger를 **새로 생성한 뒤** 이 명령을 실행한다. 원본 PE는 읽기 전용으로 열며 메모리에서 바이트를 바꾼다. 입력 해시와 래스터 재구성 검증을 통과한 파일에 한해 `psa_build_rasters.py`와 같은 `encode_interval_binned`로 다시 래스터화한다. 동결 YAML은 수정하지 않았다.

```powershell
$py = '.\.venv\Scripts\python.exe'
$root = 'D:\secure-malware-data\psa'
$rasters = Join-Path $root 'rasters'
$runs = Join-Path $root 'runs'
$audit = Join-Path $root 'audit'
$stage2 = Join-Path $root 'manifest_stage2.csv'
$samples = Join-Path $root 'pe-machine-learning-dataset\samples'
$mainLedger = Join-Path $audit 'main_test_structure_census_20260924\structure_ledger.jsonl'
$eraLedger = Join-Path $audit 'era_test_structure_census_20260924\structure_ledger.jsonl'
$mainLedgerSha = '53bc25ecf7b144cb5d1599fba9052b0eb9d52ef973947672fdbc720ecbd85c7b'
$eraLedgerSha = 'bf538e933bfd87a19a0e5ed47bdf2a40344e3bbd602215b61586d00072473b16'
$mainHashes = @{42='291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f';43='4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56';44='62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c'}
$eraHashes = @{42='a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6';43='f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf';44='da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1'}
foreach ($seed in 42,43,44) {
    foreach ($population in @('main','era')) {
        $ledger = if ($population -eq 'main') { $mainLedger } else { $eraLedger }
        $ledgerSha = if ($population -eq 'main') { $mainLedgerSha } else { $eraLedgerSha }
        $modelDir = if ($population -eq 'main') { 'c8_retrain_20260924' } else { 'era_20260924' }
        $checkpoint = Join-Path $runs "$modelDir\seed${seed}_imagenet_bs512\best.pt"
        $checkpointSha = if ($population -eq 'main') { $mainHashes[$seed] } else { $eraHashes[$seed] }
        $camDir = Join-Path $runs "xai_v1_1\${population}_seed${seed}_gradcam"
        $cam = Join-Path $camDir 'gradcam_ledger.jsonl'
        $camSha = (Get-FileHash -LiteralPath $cam -Algorithm SHA256).Hash.ToLower()
        $out = Join-Path $runs "xai_v1_1\${population}_seed${seed}_perturb"
        & $py scripts\psa_perturb.py --checkpoint $checkpoint --checkpoint-sha256 $checkpointSha --gradcam-ledger $cam --gradcam-ledger-sha256 $camSha --structure-ledger $ledger --structure-ledger-sha256 $ledgerSha --stage2-manifest $stage2 --samples-dir $samples --rasters-dir $rasters --outdir $out
        if ($LASTEXITCODE -ne 0) { throw "$population seed $seed perturb failed" }
    }
}
```

## 계산량

파일당 budget 4개, fill 3개, 대조군 repeat는 20+1+1+20=42개다. 각 조합에서 Grad-CAM 선택과 대조군 선택의 deletion·keep-only를 각각 평가하므로 agreement 표본당 **2,016 forward pass**, fallback 표본당 구조 대조군 20회를 제외한 **1,056 forward pass**다. 원래 Grad-CAM 생성에는 파일당 별도 forward/backward 1회가 추가된다.

| 모집단 | agreement / fallback | perturb forward / seed | 3 seed |
|---|---:|---:|---:|
| main | 17,365 / 42 | 35,052,192 | 105,156,576 |
| era | 5,331 / 1 | 10,748,352 | 32,245,056 |
| 합계 | 22,696 / 43 | 45,800,544 | **137,401,632** |

GPU 1개에서 순차 실행 시 forward 1회가 10/50 ms라면 모델 forward만 약 **15.9/79.5일**이다. PE 읽기, fill, 재래스터화, JSONL 쓰기 및 Grad-CAM backward 시간은 별도다. C9x-2b 사용자 20건 smoke 실측은 521초, 표본당 약 26초, 초당 약 77 forward pass였고 GPU 사용률은 매우 낮았다. 전체 환산 약 20.5일은 이 작은 표본의 단순 외삽이며 새 구현의 실측값이 아니다.

가정: YAML에는 entropy 구간 크기와 local median의 좌표계가 수치로 지정되지 않았다. 구현은 entropy를 원본 256바이트 고정 구간의 Shannon entropy로 순위화하고, local median 5×5는 원본 바이트를 raster side 폭의 행 우선 격자로 놓아 해석했다. 구조 fallback에서는 structure-matched 행을 eligible=false로 유지하고, 구조 조건 resampling에는 파일 전체를 pool로 쓴다. 이는 동결 정책의 추가 해석이므로 분석 시 명시한다.

## C9x-2b 20건 smoke 계측 (미실행)

위 코드 블록의 변수 설정을 실행하고, 갱신된 Grad-CAM ledger가 있는 main seed 42에 대해 아래 명령을 실행한다. 처음 실행에는 빈 outdir를 쓰고, 중단 후 같은 outdir에 `--resume`을 붙여 재개한다. `--limit-samples 20`은 ledger 순서의 앞 20개 sample_id를 택한다.

```powershell
$seed = 42
$checkpoint = Join-Path $runs 'c8_retrain_20260924\seed42_imagenet_bs512\best.pt'
$cam = Join-Path $runs 'xai_v1_1\main_seed42_gradcam\gradcam_ledger.jsonl'
$camSha = (Get-FileHash -LiteralPath $cam -Algorithm SHA256).Hash.ToLower()
$out = Join-Path $runs 'xai_v1_1\main_seed42_perturb_smoke20'
$elapsed = Measure-Command {
    & $py scripts\psa_perturb.py --checkpoint $checkpoint --checkpoint-sha256 $mainHashes[$seed] --gradcam-ledger $cam --gradcam-ledger-sha256 $camSha --structure-ledger $mainLedger --structure-ledger-sha256 $mainLedgerSha --stage2-manifest $stage2 --samples-dir $samples --rasters-dir $rasters --outdir $out --limit-samples 20 --workers 2
    if ($LASTEXITCODE -ne 0) { throw 'perturb smoke failed' }
}
"smoke20 elapsed seconds: $([math]::Round($elapsed.TotalSeconds, 2))"
```

재개에는 같은 명령에 `--resume`을 추가한다. 파일당 ledger를 flush하며 마지막 불완전 sample_id의 행은 재개 시 제거하고 다시 계산한다. CPU 워커가 바이트 수정과 재래스터화를 준비하고 주 프로세스가 512개씩 GPU 추론한다. 학습과 동일하게 CUDA autocast를 사용한다. 합성 회귀 테스트는 코드에 추가했으며 이 세션에서는 실행하지 않았다.

## C9x-2c 구현 결정 (미실행)

- `python scripts\psa_perturb.py` 직접 실행을 위해 같은 `scripts` 폴더의 `psa_gradcam`을 import한다.
- Entropy 정렬은 원본 파일당 한 번 캐시한다. 대조군 offset은 `(sample, budget, control, repeat)`별 한 번만 선택하고 fill 3종에 공유한다. offset 난수 seed에는 fill을 넣지 않는다. ledger의 `pair_seed`와 fill 난수 상태는 `(sample, budget, fill, control, repeat)`별로 분리한다. 출력 필드와 결과 정의는 유지한다.
- 원본 파일의 pixel별 정수 바이트 합·개수를 캐시하고 바뀐 바이트의 delta를 `np.bincount`로 pixel에 모아 float32 래스터를 만든다. nearest-byte 정책에는 같은 delta를 해당 pixel들에 직접 전파한다.
- C9x-2d Windows 긴급 수정: 워커는 래스터를 하나의 연속 float32 ndarray `(n, side, side)`로 쌓아 행·점수화 대상과 함께 반환한다. 주 프로세스는 배열을 512개씩 나눠 GPU 점수화한다. Windows에서 마지막 열린 핸들이 닫히면 세그먼트가 해제되는 문제 때문에 공유 메모리 전달은 제거했다. 최대 3개 준비 작업을 미리 제출해 CPU 준비와 GPU 소비를 겹친다. `--workers` 기본값은 `max(1, (os.cpu_count() or 1)-4)`다.
- 5×5 local median의 부분 마지막 행 주변을 `rows >= height-3`에서 직접 재계산한다. 매 표본 완료마다 stderr에 경과 시간, 표본당 초, 예상 잔여 시간을 출력한다. 예상 잔여 시간은 이 실행에서 완료한 표본의 평균에 근거한다.
- 합성 무작위 바이트, 비배수 길이, partial last row 테스트를 추가했다. 기존 테스트 4건은 유지했다. 기존 `.venv` Python 런처가 사라진 base Python을 가리켜 pytest 실행은 실패했다. 전체 perturb 실행과 새 smoke는 하지 않았다.

## C9x-2e 3차 성능 수정 (미실행)

- 사용자 기능 smoke 3건은 표본당 225초, 파이프라인 정상 완료(6,048 pass)로 보고되었다. 이 수정 뒤의 성능은 아직 측정하지 않았다.
- 각 eligible ledger 행은 `control_intervals`와 `gradcam_intervals` 대신 `control_offsets_sha256`과 `control_offsets_n`을 기록한다. SHA-256 입력은 선택한 byte offset을 오름차순 정렬한 little-endian signed int64 배열이다. Grad-CAM 위치의 원본은 입력 Grad-CAM ledger의 `budget.intervals`다.
- 대조군 위치는 같은 원본 바이트, Grad-CAM 위치, 구조 상태, entropy 순위와 `offset_seed(checkpoint_seed, sample_id, budget, control, repeat)`로 결정론적으로 재생성한다. 코드의 `verify_control_offsets`는 재생성한 위치의 건수와 SHA-256을 행과 대조한다. `pair_seed`는 기존대로 `(seed, sample, budget, fill, control, repeat)`에서 계산해 행에 유지한다.
- pass seed마다 파일 길이의 fill 배열 `R`을 공유한다. 구조 조건 resampling은 region마다 그 region 길이만큼 같은 region의 원본 바이트에서 복원 추출한다. local median은 파일당 캐시한 격자, zero는 0을 사용한다. Grad-CAM·control 양쪽의 deletion은 원본에서 선택 byte만 `R`로 바꾸고, keep-only는 `R`을 기본으로 선택 byte만 원본으로 복원한다. 두 모드 모두 선택 byte의 정수 합 차이만 증분 적용한다. 이는 동결 규칙 **동일 fill random state 공유**의 구현이다.
- 구조 조건 fill의 파일 전체 추출·기본 래스터 계산 횟수는 agreement 표본에서 4 budget × 42 control/repeat = 168회다. 이전 네 경우별 처리 4 × 42 × 3 fill × 4 = 2,016회 대비 예상 감소이며 실측값은 아니다. zero와 local median의 기본 래스터는 파일당 한 번만 계산한다.
- `deletion_delta_nll`, `keep_only_malicious_score`, `pair_seed`의 정의와 필드는 유지했다. `psa_xai_stats.py`는 두 intervals 필드를 읽지 않으므로 입력 계약은 바뀌지 않는다. 무작위 바이트 합성 데이터에서 공유 `R` 방식과 전체 재인코딩을 바이트 단위로 비교하는 테스트, 대조군 digest 재생성 검증을 추가했다. 요청대로 실행하지 않았다.
