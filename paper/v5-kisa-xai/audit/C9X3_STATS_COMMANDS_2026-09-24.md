# C9x-3 통계 실행 준비

동결 YAML은 읽기 전용이다. 아래 여섯 쌍은 각 모집단·seed의 완전한 JSONL이어야 한다. 실제 ledger는 이 청크에서 열지 않았다.

```powershell
$stats = @(
  '--ledger','main','42','<main42_perturb.jsonl>','<main42_gradcam.jsonl>',
  '--ledger','main','43','<main43_perturb.jsonl>','<main43_gradcam.jsonl>',
  '--ledger','main','44','<main44_perturb.jsonl>','<main44_gradcam.jsonl>',
  '--ledger','era','42','<era42_perturb.jsonl>','<era42_gradcam.jsonl>',
  '--ledger','era','43','<era43_perturb.jsonl>','<era43_gradcam.jsonl>',
  '--ledger','era','44','<era44_perturb.jsonl>','<era44_gradcam.jsonl>'
)
& 'C:\TOOL\anaconda\python.exe' scripts\psa_xai_stats.py @stats --outdir '<new_stats_output_dir>'
```

출력은 `psa_xai_stats.json`과 `psa_xai_stats.md`이다. JSON에는 protocol 및 여섯 ledger의 SHA-256, seed별·3 seed 평균, group bootstrap의 H1/H2 효과·95% CI·단측 p·Holm p, 파일 단위 sensitivity, repr_policy, correctly detected subset, 기술 통계, 구조 CAM mass가 있다. 빈 CAM과 structure-matched 비적격 건수를 따로 기록한다. 3 seed 평균은 동일 sample의 파일별 차이를 seed 평균한 뒤 group 단위로 재표집한다. p는 우월성 가설의 bootstrap 분포에서 0 이하 비율에 plus-one 보정을 적용한다.

비용: JSONL 여섯 쌍을 순차로 읽고 각 파일의 repeat 묶음을 즉시 요약한다. 각 seed의 CAM budget 메타데이터와 primary 파일 차이는 메모리에 유지한다. 2,000회 group/file bootstrap은 최대 128회씩 나누어 수행한다. 실제 전체 ledger의 실행 시간·메모리는 미측정이다.

검증: `C:\TOOL\anaconda\python.exe -m pytest -q -o cache_dir=.pytest_cache_c9x3b --basetemp=.pytest_tmp_c9x3b tests/test_psa_xai_stats.py` → 3 passed. `py_compile` 및 `git diff --check` 통과. `.venv` Python은 base 경로 오류로 실행 불가.
