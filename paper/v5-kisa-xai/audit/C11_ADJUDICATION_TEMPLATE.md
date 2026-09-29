# C11 V1.2 사전 판정 틀

이 표는 V1.2 실행 전 판정 기준이다. 주 검정은 main 악성 test, budget 0.10, structure-conditioned resampling, shape_matched_random 20회이다. H1prime·H2prime 두 검정에 Holm 보정을 적용한다. V1.1 H1·H2 판정은 소급 변경하지 않는다. 아래 해석은 V1.2의 탐색적 결론으로만 쓴다.

| 사전 조건 | V1.2 판정 문구 |
|---|---|
| H1prime Holm p < 0.05 | V1.1 H1의 음수 방향은 바이트 분산에 의한 모양 교란과 부합하며, 모양 정합 대조에서 필요성이 회복된다. |
| H1prime Holm p >= 0.05 | 모양 정합 후에도 필요성은 지지되지 않는다. 필요성 부재를 실질적 설명으로 우선하되, 영가설의 증명으로 쓰지 않는다. |
| H2prime Holm p < 0.05 | 모양 정합 후에도 충분성이 지지되어, V1.1 H2는 모양 교란에 의존하지 않는다는 해석과 부합한다. |
| H2prime Holm p >= 0.05 이고 95% CI가 0 포함 | 충분성의 모양 독립성은 지지되지 않는다. V1.1 H2가 온전 블록 효과였다는 설명과 부합한다. |

H2prime 미지지이면서 CI가 0을 포함하지 않는 경우는 효과 방향과 CI를 그대로 보고하고 네 번째 문구를 적용하지 않는다. Era는 재현 방향·CI만 보고하고 main의 두 가설 family에 더하지 않는다.

## 정합 검증 및 예외

- 총 선택 고유 바이트 수와 region별 선택 바이트 수는 모든 행에서 정확 일치, run 길이 다중집합은 `run_split=false` 행에서만 정확 일치 여부를 파일·seed·budget·repeat별 확인: ____
- 두 팔의 `pixels_intact`, `pixels_touched`와 shape−Grad-CAM 차이 분포: ____
- 픽셀 수 정확 일치는 요구하지 않음. mean-pool·nearest-repetition의 픽셀당 바이트 수 변동을 함께 보고: ____
- 2D 세로 연속성·블록 뭉침은 정합 대상이 아님을 결과 해석에 명시: ____
- `n_runs=0`인 빈 CAM 수, placement_fallback 수, 미배치 바이트 수와 정합 불일치 필드: ____
- `run_split=true` 행 건수 및 primary 포함·split 제외 sensitivity 결과: ____
- `unplaced_byte_count>0` 행 건수 및 primary·sensitivity 통계 제외, 남은 repeat 평균과 전 repeat 제외 파일의 budget 적격성: ____
- placement 실패 행의 forward pass 계산 확인: ____
- 구조 fallback main 42건·era 1건의 행 보존·structure_ineligible 표시 및 forward pass 미계산 확인: ____
- budget 0.20 기술 통계와 V1.1 ledger 결합 `dispersion_effect`(H1/H2 각각, 파일 평균, 추론 p 없음): ____

## 실행 증거 기입란

| 항목 | main seed 42/43/44 | era seed 42/43/44 |
|---|---|---|
| V1.2 perturb ledger 경로·SHA-256 | ____ | ____ |
| V1.1 scatter ledger 경로·SHA-256 | ____ | ____ |
| Grad-CAM ledger 경로·SHA-256 | ____ | ____ |
| checkpoint 경로·SHA-256 | ____ | ____ |

- V1.1 parent YAML SHA-256: `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709`
- V1.2 addendum YAML SHA-256(C11-a2 보정): `9712217fc49db0fb1f495a901526e985c731bfe3650dacb1bb875fbe4fcb4162`; 실행 전 재계산: ____
- 실행 커밋 / 사용자 동결 태그 / 태그 대상 커밋: ____ / ____ / ____
- 통계 결과 경로·SHA-256 및 H1prime·H2prime 효과, 95% CI, 단측 p, Holm p, 적격 N: ____
