# C10 판정 문서 틀

상태: 미실행·미판정. 아래 대괄호는 실제 결과로 채운다. 동결 규칙: main/era test 각 1회 접근, 모델·정책·가설·통계 단위 변경 없음. H1/H2 주 검정은 main 모집단의 seed 평균, imphash 그룹 재표집, 2,000회 쌍체 bootstrap, 단측 우월성 p와 두 가설 Holm 보정 p로 판정한다. 유의수준 [동결 YAML 확인 후 기입]. Era는 재현성 결과이며 주 가설 family에 더하지 않는다.

## 표 1. Held-out test 성능

| 모집단 | Seed | 유효 N (정상/악성) | AUROC | Macro-F1 | Balanced accuracy | 정상 recall | 악성 recall | 혼동행렬 [[TN,FP],[FN,TP]] | 평가 JSON SHA-256 |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| main | 42 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| main | 43 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| main | 44 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| era | 42 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| era | 43 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| era | 44 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

예상 유효 N은 main 30,146, era 10,652. 실제 JSON의 split counts 및 혼동행렬 합계로 확인한다. Test 성능은 validation 선택 성능과 분리해 서술한다.

## 표 2. Main H1/H2 주 검정

| 가설 | Seed 평균 효과 | 95% CI | 단측 p | Holm p | 적격 파일 N | imphash 그룹 N | 판정 |
|---|---:|---|---:|---:|---:|---:|---|
| H1: top-10% deletion ΔNLL > 구조 매칭 무작위 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| H2: top-10% keep-only 악성 점수 > 구조 매칭 무작위 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

출처: `psa_xai_stats.json` → `populations.main.seed_average.primary.h1/h2`. Primary fill은 structure-conditioned resampling, 대조군은 구조 매칭 무작위 20회. 양의 효과가 우월성 방향이다. Seed별 방향·효과·CI·p도 본문에 기록: [ ].

## 표 3. Era 재현

| 가설 | Seed 평균 효과 | 95% CI | 단측 p | Holm p | 적격 파일 N | 그룹 N | Main 대비 방향·해석 |
|---|---:|---|---:|---:|---:|---:|---|
| H1 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| H2 | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

출처: `populations.era.seed_average.primary`. Era는 독립 재현·robustness로 효과 방향과 CI를 보고한다. Main 검정의 family 크기 또는 판정을 소급 변경하지 않는다. Era seed별 방향: [ ].

## 표 4. Sensitivity·하위집단

| 모집단/범위 | 가설 | 효과 | 95% CI | p (있는 경우) | 적격 파일 N | 해석 |
|---|---|---:|---|---:|---:|---|
| main/era 파일 단위 bootstrap sensitivity | H1/H2 | [ ] | [ ] | [ ] | [ ] | [ ] |
| main/era 정탐 악성 subset | H1/H2 | [ ] | [ ] | [ ] | [ ] | [ ] |
| main/era mean-pool 표현 | H1/H2 | [ ] | [ ] | [ ] | [ ] | [ ] |
| main/era nearest-repetition 표현 | H1/H2 | [ ] | [ ] | [ ] | [ ] | [ ] |

출처: 각 `seed_average.primary.*.sensitivity_file`, `correctly_detected_malicious`, `repr_policy`. Seed별 결과도 확인한다. 하위집단은 탐색·민감도 해석으로 보고하며 주 검정 판정을 대체하지 않는다.

## 표 5. 기술 통계

| 모집단 | Budget | Fill | Control | H1/H2 | 쌍체 평균 | 대조군 평균 | 적격 파일 N |
|---|---:|---|---|---|---:|---:|---:|
| [main/era] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

출처: `seed_average.descriptive` 전 조합을 채우거나 별표로 첨부한다. 주 검정 외 budget/fill/control은 기술 통계로만 해석한다.

## 구조 CAM mass

| 모집단 | 구조 영역 | 평균 CAM mass | N |
|---|---|---:|---:|
| [main/era] | [ ] | [ ] | [ ] |

출처: `seed_average.structure_cam_mass` 전체 영역. Fallback은 구조 귀속 불가로 별도 집계한다.

## 적격성 집계

| 모집단·seed/평균 | CAM 표본 N | 빈 CAM 제외 N | 구조 비적격 N | 주 검정 적격 N | 그룹 N | census fallback N |
|---|---:|---:|---:|---:|---:|---:|
| main 42/43/44/평균 | [ ] | [ ] | [ ] | [ ] | [ ] | 42 |
| era 42/43/44/평균 | [ ] | [ ] | [ ] | [ ] | [ ] | 1 |

출처: `counts`와 `primary.*.group_n`. 예상 악성 적격 상한은 main 17,365, era 5,331이며 빈 CAM 등의 추가 제외가 있으면 실제 N이 낮아진다. 비적격 표본은 ledger에서 보존된다.

## Ledger SHA-256

| 모집단 | Seed | Perturb ledger SHA-256 | Grad-CAM ledger SHA-256 | 원본 요약과 일치 여부 |
|---|---:|---|---|---|
| main | 42 | [ ] | [ ] | [ ] |
| main | 43 | [ ] | [ ] | [ ] |
| main | 44 | [ ] | [ ] | [ ] |
| era | 42 | [ ] | [ ] | [ ] |
| era | 43 | [ ] | [ ] | [ ] |
| era | 44 | [ ] | [ ] | [ ] |

출처: 통계 JSON `ledger_sha256`; 여섯 쌍의 두 SHA-256을 원본 run summary와 대조한다.

## 실행 provenance

- 동결 protocol 경로·SHA-256: [ ] / `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709`; 실제 통계 JSON과 확인: [ ].
- 사용 명령·시작/종료 시각·호스트·GPU·Python/torch/numpy 버전·Git HEAD/dirty 상태: [ ].
- Main/era split manifest 경로·SHA-256, raster index/array/duplicate groups SHA-256: [ ]; 평가 JSON의 `input_sha256`과 대조: [ ].
- 여섯 checkpoint 경로·기대/재계산 SHA-256, epoch, seed, 모델 provenance: [ ]; 평가 JSON 및 freeze 문서와 대조: [ ].
- 여섯 test 평가 JSON 경로·SHA-256, 통계 JSON/MD 경로·SHA-256, 원본 ledger·summary·로그 경로: [ ].
- 단일 test 접근 및 재실행 부재, 실패/부분 실행/예외와 처리: [ ].

## 판정 문안

- **H1·H2 모두 기각:** Main seed 평균의 양의 효과와 Holm p가 동결 기준을 각각 충족했다. 두 주 가설의 구조 매칭 무작위 대비 우월성을 지지한다. Era 방향·CI 및 sensitivity의 일치/불일치를 별도로 기술한다: [ ].
- **한 가설만 기각:** [H1/H2]는 기준을 충족했고 [다른 가설]은 충족하지 못했다. 지지되는 지표에 한정해 결론을 쓰고, 다른 지표의 효과·CI를 함께 보고한다. Era·sensitivity의 패턴: [ ].
- **둘 다 기각하지 못함:** 두 주 가설 모두 동결 기준을 충족하지 못했다. 우월성 증거가 부족하며 영가설이 참임을 입증한 것으로 표현하지 않는다. 추정 효과·CI·적격 N과 era 재현을 기술한다: [ ].

어느 경우에도 단측 p와 Holm 보정 p, CI, 모든 seed의 방향, test 성능, 제외 건수를 함께 보고한다. 새 분석은 V1.2 exploratory로 구분한다.
