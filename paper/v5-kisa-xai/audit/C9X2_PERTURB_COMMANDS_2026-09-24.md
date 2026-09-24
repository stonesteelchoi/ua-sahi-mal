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

GPU 1개에서 순차 실행 시 forward 1회가 실제로 10/50 ms라면 모델 forward만 약 **15.9/79.5일**이다. PE 읽기, fill, 재래스터화, JSONL 쓰기 및 Grad-CAM backward 시간은 별도라 실제 시간은 더 길다. 실제 환경의 계측값은 없으며 이는 시나리오다. 이 비용은 실행 전 재검토가 필요하다.

가정: YAML에는 entropy 구간 크기와 local median의 좌표계가 수치로 지정되지 않았다. 구현은 entropy를 원본 256바이트 고정 구간의 Shannon entropy로 순위화하고, local median 5×5는 원본 바이트를 raster side 폭의 행 우선 격자로 놓아 해석했다. 구조 fallback에서는 structure-matched 행을 eligible=false로 유지하고, 구조 조건 resampling에는 파일 전체를 pool로 쓴다. 이는 동결 정책의 추가 해석이므로 분석 시 명시한다.
