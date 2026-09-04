# 연구·구현 감사: 현재 논문화 가능성

- **감사일:** 2026-09-04
- **대상:** 실험 1–3, 원 집계 산출물, v2 구현, 공개 선행연구

> **범위 상태:** 이 감사는 보존된 v2 BIG2015 결과의 유효성을 판정한다. 현재
> v3 논문 설계 검토는
> [`../paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md`](../paper/reviews/PAPER_DRAFT_REVIEW_2026-09-04.md)를 따른다.

## 1. 냉정한 판정

현재 상태 그대로는 **실험 3을 주 결과로 논문에 제출하면 안 된다**. pytest 186개와
수치 감사 285개가 통과했다는 것은 코드 경로와 기록된 숫자의 일관성을 보여주지만,
실험 설계의 교란을 제거하지 못한다.

가장 큰 문제는 BIG2015 `.bytes` parser가 `??`와 주소 공백의 validity mask를
정상적으로 만들면서도 `SampleStore.get()`이 이를 버리고, 이후 A/B/C와 histogram
fill이 0으로 채워진 무효 위치를 실제 byte처럼 본다는 점이다. 첫 실행에 사용한
manifest를 감사했을 때:

- 45개 판정 subset의 `valid_fraction`: 최소 0.00758, 중앙값 0.89082, 평균 0.69937
- 45개 중 11개가 0.5 미만, 4개가 0.1 미만
- 계열별 평균도 약 0.146–0.995로 크게 달랐다.
- `valid_fraction` 한 값만 쓰는 nearest-class-centroid가 validation 0.406,
  test 0.419 정확도를 냈다(9-class chance 0.111).

이 결과는 신경망이 그 shortcut을 실제로 사용했다는 증명은 아니다. 그러나 그
shortcut이 충분히 강하게 **존재**한다는 증명이며, 마스크를 버린 모델 결과로
“전역 byte 통계”를 주장하기에는 치명적이다. 특히 C_text의 D3 통과는 실제 bigram
신호가 아니라 계열별 무효-0 비율의 영향일 수 있다.

따라서 현재 논문화 상태는 다음과 같다.

| 부분 | 판정 | 이유 |
|---|---|---|
| 실험 1 | 사용 가능 | 3 seed, paired CI, calibration·latency 범위가 명시됨 |
| 실험 2 | 제한적으로 사용 가능 | JBU 결과는 유효하나 실제 UPA를 측정하지 않았으므로 범위를 좁혀야 함 |
| 실험 3 | **보류** | validity shortcut, class-weight 무효, random-control overlap을 고쳐 재실행해야 함 |
| 세 실험 통합 5쪽 원고 | 비권장 | 질문·데이터·모델이 달라 실패 사례 목록처럼 보이며 각 위협을 방어할 공간이 없음 |

## 2. 구현 감사에서 발견한 사항

### P0 — validity mask가 버려진다

`corpus.load_entry_bytes()`는 `(data, valid)`를 반환하지만 `training.SampleStore.get()`은
`data, _`로 mask를 버린다. `features.text_features()`와
`occlusion.make_fill_plan()`은 mask를 받을 수 있도록 작성돼 있으나 호출자가 주지
않는다. 문서의 “valid bytes만 사용” 설명과 실행이 다르다.

**필수 조치**: 기존 산출물을 수정된 코드의 결과로 가장하지 말고
`protocol/results format`을 v2로 올린 뒤 아래 두 표현을 함께 재실행한다.

1. `compact-valid`: 무효 위치를 제거한 byte sequence. 실제 관측 byte 통계에는 가장
   충실하지만 VA 좌표가 달라지므로 원 VA 매핑표를 별도 유지한다.
2. `mask-aware/inpaint`: 좌표를 보존하되 무효 위치를 sample의 valid-byte histogram
   또는 별도 mask channel로 처리한다. mask channel 자체가 family shortcut이 될 수
   있으므로 valid_fraction-matched 평가를 병행한다.

두 방식에서 결론이 같을 때만 “분산된 근거”라고 써야 한다.

### P0 — A의 class weight가 실제로 상쇄됐다

A는 sample 하나씩 forward하고 기본 `CrossEntropyLoss(reduction="mean")`을 썼다.
한 원소 batch에서는 target class weight가 weighted sum의 분자와 mean의 분모에서
상쇄된다. 이 감사에서 `reduction="sum"`으로 수정했지만 기존 checkpoint는 다시
학습해야 한다. B는 여러 sample batch라 기존 mean weighting이 작동한다.

### P0 — 무작위 대조가 evidence와 겹칠 수 있었다

기존 `random_control_ranges()`는 control끼리만 겹치지 않게 했고 원 evidence 구간은
제외하지 않았다. 이 겹침은 treatment-control 차이를 0 쪽으로 편향시킨다. 수정된
코드는 disjoint placement를 강제하고, 불가능하면 오류를 낸다. 보존율 70%처럼
동일 길이의 disjoint control이 수학적으로 불가능한 조건에서는 control을 `null`로
보고해야 한다.

### P1 — `deletion_curve()`는 실제 누적 deletion이 아니다

현재 함수는 서로 독립적으로 한 block씩 가린 `ΔNLL`을 누적 합산한다. 신경망은
비선형이므로 이것은 상위 k개를 동시에 가리고 재추론한 deletion curve와 같지 않다.
이 함수의 값은 논문에 사용하지 말고, 매 budget마다 누적 mask를 실제 적용해
재추론하는 새 실험을 구현해야 한다.

### P1 — checkpoint 역직렬화

v2 A/B loader가 CLI 경로를 `weights_only=False`로 읽었다. 조작된 checkpoint가
Python object를 실행할 수 있어 `weights_only=True`로 수정했다. 결과 수치에는
영향이 없지만 공개 연구 코드의 안전성에는 필요하다.

## 3. Q2 — 5쪽 논문의 가장 방어 가능한 각도

### 추천: (c)를 수정한 단일 주제

> **악성코드 바이트 이미지에서 perturbation 기반 근거 지역화가 성립하기 위한
> 검출 하한과 실패 조건**

실험 3을 주로 하되, 실험 2는 “왜 자연영상의 edge prior가 byte boundary에 그대로
맞지 않는가”를 설명하는 짧은 ablation으로만 넣는다. 실험 1은 본문에서 빼거나
관련 연구/부록 한 문장으로 처리한다. MC-dropout calibration은 좋은 부정 결과지만
근거 지역화 논문의 논리 사슬에 필수적이지 않다.

기여는 성능 향상이 아니라 다음 세 가지로 고정한다.

1. matched random·fill·cross-model·cross-representation을 포함한 검증 프로토콜,
2. 합성 신호 크기에 따른 **detectability floor**와 control 불가능 영역,
3. mask-aware 재실행에서 확인된 범위 안의 negative result.

### 후보별 위험

| 후보 | 판정 | 핵심 위험 |
|---|---|---|
| (a) 자연영상 부품의 실패 목록 | 높음 | MC dropout, upsampling, attribution이 서로 다른 질문이라 5쪽에서 “우연한 실패 세 개”로 보임. 2025/2026 선행연구가 이미 비슷한 domain-transfer 서사를 가짐 |
| (b) 판정 근거는 국소화되지 않는다 | 중간–높음 | 현재 데이터·모델 범위를 넘어 일반화하기 쉽고 MalConv header attribution이 반례. mask-aware 재실행 없이는 제출 불가 |
| (c) 오클루전 검출 하한 | **가장 낮음** | D1 실패 때문에 프로토콜 자체가 무능하다는 공격. 그러나 바로 그 실패를 신호 크기·통제 가능성의 함수로 정량화하면 방법론 결과가 됨 |
| (d) negative-result audit | 중간 | 재현성과 사전 기준은 장점이나 KIIT 리뷰어가 “새 알고리즘/성능 향상 없음”을 약점으로 볼 수 있음. 제목과 초록에서 적용 범위를 정확히 좁혀야 함 |

### 5쪽 구성

1. 서론·관련연구 0.8쪽
2. 필요성/충분성·matched control·교차 검증 정의 0.9쪽
3. 데이터·mask-aware 모델·실험 조건 0.7쪽
4. D1 감도/누적 deletion/교차 모델 결과 1.5쪽
5. 실패 조건·한계·결론 0.8쪽
6. 참고문헌 0.3쪽

실험 1과 상세 routing 표를 넣으면 핵심 그림과 위협 논의가 밀려난다.

## 4. Q3 — D1을 고쳐서 통과시킬 것인가

“20–30%에서 Y로 예측한 검체만 골라 D1 통과”로 원 D1을 교체하면 **안 된다**.
결과를 보고 검체를 선택해 사전등록 gate를 통과시키는 것이므로 selection bias다.

올바른 처리는 다음이다.

- 원 D1=0.000은 그대로 보존하고 “사전 calibration 실패”라고 보고한다.
- 별도 `D1b sensitivity`를 사후 분석으로 명시한다.
- D1b는 “Y로 예측한 것만”을 전체 평균에서 제외하지 않는다. 전체 생성물의
  recognizability rate와 조건부 localization을 두 행으로 나눠 보고한다.
- 20–30% 결과를 보고 선택했다면 confirmatory가 아니라 exploratory라고 표시한다.
- 새 seed/host 쌍에 fraction grid를 사전 고정해 재실행하면 그때부터 확인 실험이 된다.

리뷰어의 “교정 못 한 프로토콜을 왜 믿나”에는 기존 결과를 믿으라고 답하면 안 된다.
정확한 답은 다음이다.

> 원 D1은 0.7% 이식 신호가 분류기의 판정을 만들지 못해 localization 정답으로
> 기능하지 않았다. 따라서 D1 미통과 상태의 국소화 성능을 양의 근거 발견으로
> 해석하지 않는다. 대신 신호 크기를 독립변수로 한 D1b에서 (i) target family 판정이
> 언제 생기는지, (ii) 그 이후 attribution이 random보다 언제 우월한지, (iii) 동일
> 길이 disjoint control이 언제 불가능해지는지를 함께 측정한다. 이 연구의 결과는
> protocol 성공 주장이 아니라 유효한 calibration window의 존재 여부다.

즉 후자를 택할 수 있지만, 그러면 논문의 중심도 “근거를 찾았다”가 아니라
“어떤 조건에서는 근거 지역화 질문 자체를 검정할 수 없다”여야 한다.

## 5. Q4 — 분산 근거를 더 직접 검증하는 최소 실험

먼저 validity 교란을 고친 checkpoint에서만 실행한다.

### E4-1 실제 누적 deletion 대 random

- 한 번 계산한 block ranking을 사용한다.
- budget grid: 0, 1/64, 1/32, 1/16, 1/8, 1/4, 1/2.
- 각 점에서 상위 구간을 **동시에 가린 입력을 다시 추론**한다.
- 같은 coverage의 disjoint random ranking을 검체당 10회 반복한다. 1/2 이상에서는
  disjoint matched control이 불가능하므로 unrestricted random의 의미를 따로 쓰거나
  주 비교를 1/4에서 끝낸다.
- 지표: ΔNLL curve, predicted-class retention, AOPC(top−random), paired bootstrap CI.

집중 근거라면 낮은 budget에서 top curve가 random과 빠르게 벌어진다. 분산 근거라면
초기 기울기와 AOPC advantage가 작고 더 큰 coverage에서만 움직인다.

### E4-2 block-size × 고정 coverage sweep

- block: 4/16/64 KB와 파일 크기의 1%.
- 각 block 크기에서 총 가림 비율을 동일하게 1/16로 맞춘다.
- block 크기와 총 변조량을 동시에 바꾸지 않는다.
- top-vs-random paired advantage를 주 지표로 둔다.

큰 block에서만 효과가 생기면 “근거가 없다”가 아니라 interaction scale이 4 KB보다
크다는 뜻이다.

### E4-3 evidence concentration

전수 single-block ΔNLL의 양수 부분에 대해 다음을 보고한다.

- 상위 1%, 5%, 10% block의 positive evidence mass 비율
- positive mass의 Gini 또는 normalized HHI
- 전체 positive mass 50%에 도달하는 최소 파일 비율
- block 위치와 `valid_fraction`, zero-density, entropy의 상관

이 지표는 “상위 몇 개에 몰렸는가”를 직접 기술하지만 block interaction은 보지
못하므로 E4-1과 함께 해석한다.

### CPU 예상

45개 × 7 budgets × (top 1 + random 10) = 3,465회의 검증 모델 추론이다. 기존
10,521회 A forward가 약 3분이었다는 측정에 비추면 A의 cache를 재사용할 경우
현실적인 범위다. B thumbnail은 전체 재생성이 필요하므로 random 반복을 5회로 먼저
pilot하고 시간을 기록한 뒤 늘린다. 3 seed 전체 재학습보다 우선순위가 높다.

## 6. Q5 — 예상 리뷰어 공격 우선순위

### 보안 리뷰어

1. **`??`/VA gap/zero shortcut을 통제했는가?** 현재는 못 했다. 최우선 재실행.
2. family classification evidence가 실제 malicious behavior/code evidence인가? 아니다.
   “family decision evidence”로만 명명해야 한다.
3. mask가 PE 기능을 깨는 OOD 입력인데 인과라고 부를 수 있는가? 세 fill, valid-only,
   기능 보존 perturbation과의 차이, random control로 범위를 제한해 답한다.
4. BIG2015 한 개·2015년 데이터로 일반화 가능한가? 보편 명제를 버리고 dataset/model
   범위의 결론으로 쓴다. 새 데이터 추가보다 이 범위 제한이 5쪽에는 정직하다.
5. `.bytes`가 file offset이 아니라 VA인데 byte range를 analyst에게 어떻게 돌려주는가?
   compact-valid/VA mapping과 `.asm` 정렬 검증을 설명한다.
6. packer/compiler/family shortcut을 악성 행위로 오인한 것 아닌가? 맞을 수 있다.
   family attribution이지 semantic maliciousness가 아니며, 섹션/entropy/validity 상관을
   보고한다.
7. 원본 executable 없이 `.bytes`만으로 기능 보존을 어떻게 확인하는가? 확인 못 한다.
   그래서 adversarial-evasion 검증과 동일하다고 주장하지 않는다.

### XAI 리뷰어

1. **D1을 통과하지 못한 설명기를 왜 평가하는가?** protocol 성공이 아니라
   calibration/detectability floor 연구로 framing한다.
2. deletion mask가 OOD이고 fill에 민감하지 않은가? 세 fill만으로도 부족할 수 있다.
   mask-aware conditional fill 및 fill-ranking agreement를 사용한다.
3. random control이 evidence와 겹쳤는가? 기존에는 가능했다. 수정 후 재실행하고
   기존 D2/D3는 폐기한다.
4. `deletion_curve`가 independent delta 합인가 실제 재추론인가? 기존 helper는
   전자라 사용 불가. E4-1은 반드시 후자로 구현한다.
5. A가 찾고 A 전수 순위로 recall을 평가하는 순환성은? D5는 routing 효율 지표일
   뿐이고 faithfulness 주 지표는 B/C의 paired advantage라고 답한다.
6. attribution method baseline이 왜 random/entropy뿐인가? Grad-CAM 또는 HiResCAM을
   동일 budget으로 추가한다.
7. 충분성을 어떻게 정의하고 baseline input을 무엇으로 잡았는가? keep-only의 fill
   분포와 target recognizability를 명시하고 deletion/insertion 각각의 OOD 위험을 쓴다.
8. 45개·한 seed CI가 epistemic/model variability를 반영하는가? 검체 bootstrap은
   sample uncertainty만 반영한다고 명시한다. 가능하면 핵심 모델 두 seed만 추가한다.
9. 모델 B 0.877이면 오류 검체 설명이 결과를 흐리지 않는가? 정답 예측/오분류를
   사전 분리해 둘 다 보고하되 성공 검체만 사후 선택해 총 결과를 만들지 않는다.
10. “분산”과 “약한/없는 신호”를 구분했는가? E4-1/2와 recognizability curve로
    구분한다. 큰 coverage에서도 target이 회복되지 않으면 분산이 아니라 부재다.

## 7. 다음 실행의 우선순위

1. 기존 실험 3 산출물을 `provisional-invalid-mask`로 명시한다.
2. mask-aware representation 두 개를 구현하고 테스트한다.
3. A/B/C 재학습, shortcut audit, D1–D5 재실행.
4. 실제 cumulative deletion과 concentration 지표.
5. deterministic Grad-CAM baseline.
6. 결과가 유지될 때 5쪽 원고를 실험 3 중심으로 다시 작성.
7. 실제 UPA/GPU와 외부 corpus는 후속 연구로 남긴다. 둘을 기다리느라 현재의 핵심
   타당성 수정을 미루면 안 된다.
