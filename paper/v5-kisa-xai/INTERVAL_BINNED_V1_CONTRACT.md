# `interval-binned-v1` 입력 표현 계약 (P1)

- 상태: 구현 완료·합성 검사 통과 (2026-09-14). 실제 KISA 데이터에는 아직 적용하지 않음.
- 모듈: `src/ua_sahi_mal/kisa_xai/representation.py`
- 테스트: `tests/test_kisa_xai_representation.py` (합성 바이트만 사용)
- 프로토콜 근거: `protocol/KISA_XAI_V5_0_DRAFT.yaml` → `representation`, `EXPERIMENT_PROTOCOL.md` §4·§8
- 의존: `ua_sahi_mal.peatlas.intervals`(`Interval`, `IntervalSet`), numpy. 파일을 실행·import·에뮬레이션하지 않으며 바이트만 읽는다.

## 1. 정의

`P = 224 × 224 = 50,176`, `L = 파일 길이(바이트)`, `p = row-major 픽셀 인덱스(0 ≤ p < P)`.

| 구간 | policy | 픽셀 `p`의 half-open 구간 | 픽셀값 |
|---|---|---|---|
| `L ≥ P` | `contiguous_interval_mean_pool` | `[⌊pL/P⌋, ⌊(p+1)L/P⌋)` | 구간 바이트의 산술평균(정수 합 ÷ 길이, float32) |
| `L < P` | `nearest_byte_repetition` | `[⌊pL/P⌋, ⌊pL/P⌋+1)` | 해당 바이트 값 |
| `L = 0` | — | 표현 불가 → `ValueError` | — |

두 regime의 시작점 공식은 같고(`⌊pL/P⌋`, 정수 연산만 사용), 끝점만 다르다. 반올림 방식은 floor로 고정하여 지도가 `(L, P)`의 순함수가 되게 했다. 따라서 `map_sha256`은 파일 길이만으로 재현되고, 같은 길이의 파일은 같은 지도를 공유한다.

이 표현은 원본 바이트를 손실 없이 복원하는 형식이 **아니다**. 논문에서는 `정확한 바이트 복원`이 아니라 `결정론적 file-offset interval 투영`으로 서술한다. 단, `L ≤ P`이면 raster가 파일 바이트를 그대로(반복하여) 담고 `L`이 `P`보다 조금 크면 거의 그대로 담으므로, raster는 `SECURITY.md`의 민감 파생 산출물로 취급하고 Git에 넣지 않는다.

## 2. 불변식 (`IntervalBinnedMap.check_invariants`)

1. 모든 source offset이 하나 이상의 픽셀 구간에 속한다.
2. 모든 픽셀 구간은 비어 있지 않고 `[0, L)` 안에 있다.
3. 전체 픽셀 구간의 합집합은 정확히 `[0, L)`이다.
4. 픽셀 순서에 따라 구간 시작점이 단조 비감소한다.

`L ≥ P`에서는 구간이 파일을 정확히 분할하고 길이 차이가 최대 1이다. `L < P`에서는 각 바이트가 `⌊P/L⌋` 또는 `⌈P/L⌉`번 반복된다. 테스트는 `L ∈ {1, 2, 7, 223, 224, 4096, P−1, P, P+1, P+13, 2P+3, 1,000,003}`에서 네 불변식을 확인한다.

## 3. 해시

- `map_sha256`: `starts`와 `ends`(int64 little-endian) 바이트열의 SHA-256.
- `raster_sha256`: shape JSON + float32 little-endian 바이트열의 SHA-256.
- 두 값은 manifest 필드 `map_hash`, `raster_hash`에 기록한다(`EXPERIMENT_PROTOCOL.md` §2).

## 4. 투영

- `pixels_to_bytes(pixels)`: 픽셀 인덱스(또는 픽셀 `IntervalSet`) → 파일 offset 합집합. 주 방향.
- `bytes_to_pixels(offsets)`: 파일 offset 합집합 → 해당 offset과 겹치는 픽셀 인덱스 합집합.
- 왕복 성질: `pixel → bytes → pixel ⊇ 원래 픽셀`, `bytes → pixel → bytes ⊇ 원래 바이트`. 전체 이미지는 전체 파일과 정확히 대응한다. 하위 픽셀 단위의 바이트 경계는 복원할 수 없으며 이는 표현의 고유 한계로 명시한다.

## 5. 예산 기반 선택 (`select_source_bytes_by_budget`)

- 입력: 224×224(또는 P 길이) 점수 지도(예: bilinear 업샘플된 Grad-CAM), 예산 비율 `b ∈ (0, 1]`.
- 요청 예산: `requested_bytes = ⌈b·L⌉` (소수 표기 그대로의 분수 연산; `0.1`은 정확히 1/10).
- 순위: 점수 내림차순, 동률은 row-major 인덱스 오름차순(안정 정렬). **양수 점수만** 선택 자격이 있다.
- 누적 단위는 **고유 source byte** 수이며 픽셀 수가 아니다(`L < P`에서는 여러 픽셀이 같은 바이트를 가리킨다).
- 종료: 고유 바이트가 요청 예산에 도달하면 즉시 중단. 한 픽셀이 여러 바이트를 대표하므로 마지막 구간에서 초과가 생길 수 있다. `requested_bytes`, `achieved_bytes`, `achieved_fraction`, `overshoot_bytes`, `overshoot_interval`을 모두 기록하며, 대조군은 `achieved_bytes`에 맞춘다.
- 양수 점수가 하나도 없으면 sample을 제외하지 않고 `cam_empty=True`, 빈 선택으로 반환한다.
- 양수 픽셀이 예산에 도달하기 전에 소진되면 `positive_pixels_exhausted=True`와 실제 달성량을 기록한다. 0점 픽셀로 예산을 채우지 않는다(row-major 순서로 채우면 파일 선두 편향이 생기기 때문). 이 규칙은 동결 전 확정 항목이다.

## 6. 성능 (합성, 클라우드 CPU 2 vCPU)

| 파일 길이 | encode | +invariants | +10% 예산 선택 |
|---|---|---|---|
| 50,000 B | ~15 ms | ~90 ms | ~110 ms |
| 1,000,000 B | ~10 ms | ~80 ms | ~100 ms |
| 64 MiB | ~160 ms(steady state; 첫 호출은 페이지 할당으로 ~2.5 s) | — | — |

## 7. 남은 결정 (동결 전)

- 입력 정규화(0–255 → 모델 입력 스케일)와 채널 구성은 validation pilot에서 정한다.
- `L < P` 파일의 raster 저장 형식(float32 npy vs uint8 PNG + 민감 marker)과 저장소 위치.
- structure-matched random 등 대조군은 P7에서 같은 `achieved_bytes`를 사용하도록 구현한다.
