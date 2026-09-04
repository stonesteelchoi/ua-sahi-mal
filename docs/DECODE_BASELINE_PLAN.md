# DECODE를 baseline으로 사용하는 범위와 실행 계획

- **작성일:** 2026-09-04
- **대상:** v2 BIG2015 정적 바이트 근거구간 실험
- **상태:** v2 기록으로 보존. v3 직접 baseline 결정은 [`../paper/decisions/ADR-001-deepreflect-baseline.md`](../paper/decisions/ADR-001-deepreflect-baseline.md)가 대체한다.

> v3 논문에서는 DECODE를 수치 baseline으로 사용하지 않는다. 이 문서의
> `DECODE-inspired Grad-CAM` 계획도 v2 family-decision evidence 연구선에만
> 적용되며, v3 malicious-component retrieval의 DeepReflect baseline을 대신하지 않는다.

## 1. 한 줄 판정

DECODE 전체를 BIG2015 v2의 직접 성능 baseline으로 두면 **비교가 성립하지 않는다**.
DECODE는 CAPE에서 얻은 동적 API-call sequence를 이미지로 만들고, Bayesian
Grad-CAM pseudo-region으로 객체 검출 데이터셋을 생성해 EfficientDet로 여러 행위
category를 찾는 시스템이다. 현재 v2는 정적 `.bytes`의 malware-family 분류 근거를
찾는다. 입력, label, task, ground truth가 모두 다르다.

사용 가능한 비교는 두 층으로 나눠야 한다.

1. **관련 시스템 비교**: DECODE 전체 파이프라인을 표로 설명하되 수치를 직접
   우열 비교하지 않는다.
2. **동일 조건 attribution baseline**: DECODE가 사용하는 Grad-CAM 계열의 순위를
   현재 A/B 모델과 BIG2015에 적용하고, 본 프로토콜의 동일 perturbation 평가로
   비교한다. 논문에서는 “DECODE-inspired Grad-CAM baseline”이라고 부른다.

원 논문: [Scientific Reports](https://www.nature.com/articles/s41598-025-21848-z)

공식 코드: [dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits](https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits)

## 2. 직접 비교가 안 되는 이유

| 축 | DECODE | 현재 v2 | 판정 |
|---|---|---|---|
| 원자료 | CAPE dynamic report의 process/network/registry/filesystem API calls | BIG2015 `.bytes` VA dump | 다름 |
| 이미지 | feature type당 128×128, 반복·중복 제거·길이 정제 | 폭 512의 원좌표 raster와 256×256 thumbnail | 다름 |
| label | benign 및 7개 malware behavior/type, multi-label composition | 9개 malware family, single-label | 다름 |
| ROI 정답 | Bayesian Grad-CAM에서 자동 생성한 pseudo annotation | 마스킹 후 재추론으로 정의한 necessity/sufficiency | 다름 |
| 최종 모델 | EfficientDet D1/D2/D3 object detector | tiled CNN A, thumbnail CNN B, histogram+bigram C | 다름 |
| 설명 검증 | Grad-CAM/LIME 정성 일치와 downstream detector/classification | matched random, cross-model, cross-representation, fill agreement | 다름 |

그러므로 DECODE의 accuracy 95.8%와 B의 family accuracy 87.7%를 같은 표에서
“성능 비교”하면 안 된다. task가 다르므로 숫자의 대소는 의미가 없다.

## 3. 구현할 baseline

### B0 random

현재 구현. 동일 개수·동일 길이의 구간을 evidence와 겹치지 않게 선택한다. 이
기준선은 코드 수정 이후의 재실행 결과만 사용한다. 기존 결과는 control이 evidence
구간과 겹칠 수 있어 paired difference가 0 쪽으로 희석됐을 가능성이 있다.

### B1 entropy

현재 구현. 4 KB block entropy로 순위를 정한다. 싸지만 class-conditional explanation은
아니다. “악성코드 도메인 휴리스틱” 기준선이다.

### B2 occlusion oracle/search

현재 전수 오클루전. 계산량은 크지만 상위 구간의 기준 순위를 만든다. 동일 모델의
자기 검증 결과를 최종 faithfulness라고 부르지 않고, routing recall의 denominator로만
사용한다.

### B3 Grad-CAM

DECODE와 malware-image XAI 문헌에 대응하는 핵심 baseline이다.

- 대상 모델: 우선 B(whole-image thumbnail CNN). A는 tile별 처리와 global pooling
  때문에 마지막 conv CAM을 전체 byte 좌표로 조립하는 별도 규칙이 필요하므로
  보조 분석으로 둔다.
- target: 정답 family logit. 오분류 검체는 정답 target과 predicted target을 모두
  기록하되 주 분석은 사전 고정한 한쪽만 사용한다.
- map: 마지막 convolution layer의 Grad-CAM을 256×256으로 만들고, 각 픽셀이
  대표하는 원 byte interval로 역투영한다.
- ranking: 4 KB block별 CAM 값을 **합이 아니라 평균**으로 집계한다. 끝의 짧은
  block이 길이 때문에 불리해지는 것을 막는다.
- budget: 기존과 동일한 상위 1/16 block.
- 평가: B가 만든 CAM 구간을 A와 C에서 가려 `ΔNLL_evidence − ΔNLL_random`,
  necessity, sufficiency, 세 fill 순위 안정성을 측정한다.
- leakage 방지: Grad-CAM threshold나 layer는 test 결과로 조정하지 않는다. validation
  split에서 고정하고 test 45개에 한 번 적용한다.

### B4 Bayesian Grad-CAM

DECODE에 가장 가까운 attribution baseline이지만 주 baseline으로 권하지 않는다.
실험 1에서 MC dropout이 보정을 악화시켰고 비용이 컸다. 그래도 비교한다면:

- B 모델에 dropout을 새로 삽입해 재학습하지 않는다. 현재 B의 기존 dropout만
  stochastic inference에 사용한다.
- pass 수는 실험 1과 동일하게 5로 고정한다.
- DECODE의 certainty weighting 식을 공식 코드 revision에 맞춰 구현한다.
- deterministic Grad-CAM 대비 정확도 향상이 아니라 cross-model perturbation
  advantage와 map stability만 비교한다.
- 비용을 별도 보고한다. 결과가 나빠도 삭제하지 않는다.

### B5 HiResCAM (선택)

Brosolo et al.과 2026년 Bhavikatti & Stamp가 직접 사용했으므로 문헌 대응력은
높다. 다만 5쪽 논문에는 B3/B5 둘을 동시에 자세히 넣을 공간이 없다. 구현 비용이
낮으면 부록 산출물로 남기고 본문에는 Grad-CAM 하나만 넣는다.

## 4. 공정한 평가표

모든 attribution/routing 방법에 같은 열을 사용한다.

| 방법 | 생성 모델 | 검증 모델 | budget | ΔNLL advantage와 95% CI | sufficiency NLL | fill τ | forward pass |
|---|---|---|---:|---:|---:|---:|---:|
| random | 없음 | A/B/C | 1/16 | 0 기준 | — | — | 0 |
| entropy | 없음 | A/B/C | 1/16 | 측정 | 측정 | 해당 없음 | 0 |
| coarse occlusion | A | B/C | 1/16 | 측정 | 측정 | 측정 | 측정 |
| Grad-CAM | B | A/C | 1/16 | 측정 | 측정 | 측정 | 1 forward + 1 backward |
| Bayesian Grad-CAM | B | A/C | 1/16 | 측정 | 측정 | 측정 | 5 forward/backward |

“Evidence Recall”은 전수 A 순위에 대한 회수율이라 A 기반 방법에 유리하다. Grad-CAM
비교의 주 지표는 독립 검증 모델의 paired ΔNLL advantage로 두고, Evidence Recall은
보조 지표로만 보고한다.

## 5. CPU 예산

45개 검체에서 Grad-CAM은 검체당 대략 1 forward+backward이고, 그 뒤 선택된 범위를
A/C/B에서 검증하는 횟수는 기존 cross-check와 같은 차수다. 10,521회 전수 A
forward가 약 3분이었다면 deterministic Grad-CAM baseline 자체는 연산 병목이
아니다. Bayesian 5-pass도 현실적인 범위다. 가장 비싼 것은 새 모델 학습이 아니라
validity-mask 교란을 제거한 A/B/C 재학습과 전체 프로토콜 재실행이다.

## 6. 실행 순서와 중단 조건

1. validity mask 처리 방식을 사전 고정한다.
2. A의 single-sample class weighting과 random-control overlap 수정 후 A/B/C를
   다시 학습한다.
3. mask-aware 모델 정확도와 family별 valid fraction shortcut 성능을 함께 기록한다.
4. 기존 D1–D5를 먼저 재실행한다.
5. D2 또는 D3가 다시 측정 가능하고 모델 정확도가 chance보다 충분히 높을 때만
   Grad-CAM baseline을 실행한다.
6. Grad-CAM과 coarse occlusion 모두 random 대비 advantage가 없으면 “어느 설명기가
   더 좋은가”가 아니라 “이 표현에서 1/16 국소 explanation이 검출되지 않았다”로
   결론 낸다.

## 7. 논문 문구

사용 가능:

> DECODE가 동적 행위 이미지에서 Bayesian Grad-CAM으로 pseudo-region을 생성한 것과
> 달리, 본 연구는 정적 byte image의 구간 중요도를 동일 예산의 perturbation 및
> 독립 표현에서 평가한다. 입력과 label이 달라 DECODE의 분류 성능은 직접 비교하지
> 않고, 그 attribution 구성요소인 Grad-CAM 계열을 동일 BIG2015 조건의 기준선으로
> 재구현한다.

사용 불가:

> 본 방법은 DECODE보다 정확하다.
>
> DECODE의 ROI가 틀렸음을 보였다.
>
> DECODE를 BIG2015에서 재현했다.

현재 저장소의 `encode-behavior-report`는 안전한 정적 변환 변형이며 DECODE 전체
cleaning·grouping·EfficientDet을 byte-for-byte 재현하지 않는다. 따라서 그것도
“strict DECODE reproduction”으로 부르면 안 된다.
