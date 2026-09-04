# UA-SAHI-Mal 최상위 학회 투고 가능성 검토 및 수정 설계안

> **보존 상태:** 사용자가 제공한 pre-results 설계 검토 원문이다. 현재 baseline 결정과 실행 순서는 [`../decisions/ADR-001-deepreflect-baseline.md`](../decisions/ADR-001-deepreflect-baseline.md) 및 [`../plan/RESEARCH_PLAN_v3.md`](../plan/RESEARCH_PLAN_v3.md)에서 통제하며, 이 문서는 배경·거절 위험·설계 아이디어를 보존하는 참고 자료로 사용한다.

- 문헌 검토 기준일: 2026-09-04
- 목표: USENIX Security, ACM CCS, IEEE S&P, NDSS 및 IEEE TIFS/TDSC 수준
- 상태: 실험 전 설계 검토(pre-results design review)

---

## 0. 결론

이 연구는 **최상위 보안 학회에서 다룰 만한 문제**를 선택했다. 정적 PE 분류기가 파일을 악성으로 판정하더라도, 분석가가 실제로 확인해야 할 함수·basic block·바이트 구간을 신뢰성 있게 좁혀 주지 못한다는 문제는 실무적 가치가 높다. 또한 공개 데이터의 파일 단위 라벨과 실제 악성 component 위치 정답 사이에 큰 간극이 있다는 문제 설정도 타당하다.

그러나 제시된 현재 설계 그대로는 최상위 학회 투고 수준에 미치지 못한다. 가장 큰 이유는 다음과 같다.

1. `CAM/MIL + top-K tile + SAHI`의 조합만으로는 방법론적 신규성이 약하다.
2. 합성 삽입 위치는 **삽입 위치 정답**이지 곧바로 **악성 행위 위치 정답**이 아니다.
3. YARA와 capa는 독립적인 gold ground truth가 아니라, 전문가가 작성한 규칙에 의존하는 silver oracle이다.
4. PDB가 제공하는 함수 정보는 최적화·인라이닝·함수 병합 때문에 항상 하나의 연속 bbox가 아니다.
5. PE의 의미 공간은 본질적으로 1차원 file-offset/RVA/함수 구간이고, 2차원 bbox는 시각화를 위한 파생 표현이다.
6. SAHI는 원래 이미 학습된 객체 검출기를 슬라이스에 적용하는 추론 프레임워크다. MIL patch 재평가만 수행한다면 정확한 명칭은 `budget-aware hierarchical slicing`에 가깝다.
7. DeepReflect가 이미 “대규모 component 라벨의 비용 때문에 지도 지역화가 어렵다”는 문제를 제기하고 함수 수준 악성 component 지역화를 수행했다. 따라서 ground-truth gap의 발견 자체를 최초 기여로 주장할 수 없다.

따라서 논문의 중심은 다음과 같이 재구성해야 한다.

> **파일 단위 라벨로 학습한 약지도 모델이 정적 PE에서 분석가가 검증할 수 있는 바이트 증거를 제한된 분석 예산으로 검색하며, 그 결과를 독립적으로 구축한 다계층 byte-interval benchmark와 실제 분석가 평가로 검증한다.**

이 방향으로 수정하면 최상위 **보안** 학회는 조건부로 현실적인 목표가 된다. 반면 NeurIPS·ICML·ICLR의 일반 ML 트랙을 목표로 한다면, malware 전용 시스템을 넘어 일반적인 고해상도 약지도·예산 제한 지역화 문제로 확장하고, 새로운 학습 목적함수나 선택 최적화에 더 강한 알고리즘적 기여가 필요하다.

### 정성 평가

| 평가 항목 | 현재 설계 | 수정 설계가 성공한 경우 |
|---|---:|---:|
| 문제 중요성 | 9/10 | 9/10 |
| 데이터·평가 기여 가능성 | 6/10 | 9/10 |
| 방법론 신규성 | 4/10 | 7/10 |
| 실험 준비도 | 2/10 | 8/10 |
| 보안 실무 타당성 | 6/10 | 9/10 |
| 최상위 보안학회 적합성 | 낮음 | 조건부 유망 |
| 최상위 일반 ML 적합성 | 매우 낮음 | 여전히 제한적 |

위 점수는 합격 확률이 아니라 설계 성숙도에 대한 전문가적 정성 판단이다.

---

## 1. 제시된 설계에서 유지할 부분

### 1.1 파일 분류를 넘어 증거 검색으로 이동한 문제 설정

`malware/benign` 판정만으로는 분석가가 어떤 함수부터 역공학해야 하는지 알 수 없다. 따라서 목표를 파일 분류 정확도 하나가 아니라 다음으로 확장하는 것은 적절하다.

- 관련 함수 또는 바이트 구간의 상위 순위 검색
- 제한된 검토 예산에서의 악성 component recall
- 최초 관련 증거까지 도달하는 시간
- 전체 파일 대비 분석가가 확인한 바이트·함수의 비율

### 1.2 공개 benchmark의 위치 정답 부족을 연구 설계의 출발점으로 삼는 것

EMBER·BODMAS 같은 대표 데이터는 대규모 파일 수준 탐지에 유용하지만, 독립적으로 검증된 악성 함수·바이트 구간 정답을 기본 제공하지 않는다. 이 간극은 실제로 존재한다. 다만 논문에는 다음처럼 한정적으로 써야 한다.

> “본 연구의 체계적 문헌·데이터셋 감사 범위에서, 원본 PE 바이트 보존, 악성·정상 표본, 독립 검증된 악성 component 위치, file-offset와 이미지 좌표의 가역 대응, 누수 통제 분할을 모두 충족하는 널리 채택된 공개 benchmark를 확인하지 못했다.”

`전무하다`, `존재하지 않는다`, `약지도만이 유일한 정식화다`와 같은 절대 표현은 사용하지 않는다. 비공개 기업 데이터, 수작업 주석, 능동학습, 반지도학습 등 다른 정식화가 가능하기 때문이다.

### 1.3 다계층 평가라는 방향

한 종류의 pseudo-ground-truth에만 의존하지 않고, 통제된 합성·규칙 기반 evidence·소스 기반 gold·분석가 평가를 분리하는 방향은 좋다. 다만 각 계층이 측정하는 대상과 신뢰도를 엄격히 구분해야 한다.

### 1.4 예산 제한 관점

모든 슬라이스를 검사하는 방식보다 일부 영역을 선택해 정밀 분석하는 접근은 실제 보안 분석 비용과 연결하기 쉽다. 논문의 주 결과는 단일 정확도보다 **evidence recall–cost Pareto frontier**가 되어야 한다.

---

## 2. 현재 설계에서 치명적인 문제와 수정 원칙

## 2.1 “Ground-truth gap 최초 규명”은 단독 기여가 될 수 없다

DeepReflect는 이미 대규모 악성 component 라벨을 얻기 어렵기 때문에 완전 지도 접근이 비실용적이라고 지적하고, 정상 함수에서 학습한 autoencoder를 이용해 악성 PE의 함수·basic block을 우선순위화했다. 5명의 분석가와 26,000개 이상의 malware를 대상으로 분석 함수 수를 평균 85% 줄이고, 알려진 malware component의 80%를 식별했다고 보고했다.

따라서 기여는 단순한 공백 주장보다 다음이어야 한다.

1. 재현 가능한 검색 프로토콜과 포함·제외 기준을 갖춘 **benchmark audit**
2. byte interval을 canonical ground truth로 삼는 **새 평가 corpus**
3. 기존 DeepReflect, capa, MIL, attribution 방법과 동일 조건에서의 비교
4. analyst-facing retrieval task와 비용 지표

## 2.2 CAM/MIL + top-K는 이미 강하게 선행되어 있다

고해상도 malware image를 patch로 나누고 attention MIL로 상위 patch를 선택하는 Peters–Farhat 계열 연구가 존재한다. 2026년의 PE-MILCon 역시 PE를 byte segment bag으로 처리하고 attention으로 의심 segment를 강조한다. 일반 약지도 분야에는 ABMIL, CLAM, DSMIL, TransMIL 등 강한 baseline이 있다.

따라서 다음 정도만으로는 신규성이 부족하다.

```text
file label -> MIL attention/CAM -> top-K patches -> classification
```

방법 기여는 최소한 다음을 포함해야 한다.

- PE 구조를 보존하는 가역 atlas와 valid-byte mask
- positive-bag의 불완전한 supervision을 다루는 positive-unlabeled 또는 relation-aware objective
- 선택된 증거의 충분성(sufficiency)과 삭제 시 민감도(comprehensiveness)를 강제하는 counterfactual loss
- row width·layout·compiler 변화에서 동일 증거를 찾게 하는 consistency loss
- 예산 제약을 명시한 선택 최적화
- 불확실성 및 공간·section coverage를 이용한 recall guard
- coarse tile에서 byte interval까지 내려가는 계층형 refinement

## 2.3 Tier 1: 합성 삽입은 “악성성”이 아니라 “출처가 알려진 구간”을 검증한다

`secml_malware`는 padding, slack, content shifting 등을 포함한 adversarial malware manipulation 라이브러리다. EICAR 문자열이나 shellcode bytes를 정상 PE의 slack에 넣는 것만으로 해당 PE가 실제로 그 코드를 실행하거나 악성 행위를 수행하는 것은 아니다.

따라서 Tier 1의 이름과 주장을 바꿔야 한다.

**권장 명칭:** Controlled-Provenance Benchmark

측정 가능한 것:

- offset↔pixel 매핑 정확도
- 알려진 marker/compiled module 위치 회수율
- 삽입 길이·위치·section·row width 변화에 대한 민감도
- 모델이 단순한 고엔트로피·희귀 byte를 탐지하는지 여부

측정할 수 없는 것:

- 실제 in-the-wild 악성 함수 지역화 정확도
- 악성 행위 의미 이해

더 강한 Tier 1을 만들려면 단순 marker 대신 안전한 capability 모듈과 matched inert control을 컴파일한다. 예를 들어 네트워크·파일·프로세스 API 호출 형태를 갖되 외부 피해를 일으키지 않는 모듈을 만들고, 동일한 크기·엔트로피·section 특성을 가진 비기능성 control을 함께 삽입한다.

## 2.4 Tier 2: YARA/capa는 silver evidence다

YARA는 byte/string match의 offset과 길이를 제공할 수 있다. 그러나 match 구간은 대개 전체 악성 함수가 아니라 signature fragment다. capa는 전문가가 작성한 규칙을 instruction, basic block, function, file scope에서 매칭하며 capability를 반환한다. capability는 `파일 접근`, `프로세스 생성`, `암호화`처럼 정상 소프트웨어에도 나타날 수 있다.

따라서:

- YARA match는 `signature evidence interval`
- capa match는 `capability-bearing function`
- 둘 모두 `malicious gold`가 아니라 `silver evidence`

로 정의해야 한다.

학습과 평가에 동일 rule set을 쓰면 oracle leakage가 생긴다. 최소한 rule-family holdout, capability holdout, malware-family holdout을 두고, gold 결과와 별도 표에서 보고한다.

또한 “human-free”라는 표현은 부정확하다. 규칙과 소스 라벨은 사람의 지식으로 만들어진다. 권장 표현은 다음이다.

> annotation-light, programmatically derived, and analyst-audited

## 2.5 Tier 3: PDB는 항상 하나의 정확한 연속 bbox를 제공하지 않는다

최적화된 native code에서는 dead-code elimination, inlining, function merging, identical COMDAT folding이 발생할 수 있다. 인라인 함수는 호출자 여러 곳의 code chunk로 분산될 수 있다. 따라서 `PDB function = 하나의 [start,end) bbox`라는 가정은 틀릴 수 있다.

Tier 3은 두 종류의 build로 나눈다.

### Gold build

- optimization disabled 또는 O0
- inlining disabled
- link-time code generation disabled
- `/OPT:NOREF`, `/OPT:NOICF`
- deterministic build configuration 기록
- PDB/DWARF line table과 map file 보존

### Domain-shift build

- O1/O2
- inlining/LTO/ICF 활성화
- packing·obfuscation은 별도 하위 실험

정답 표현은 함수별 하나의 bbox가 아니라 다음이어야 한다.

```text
component_id -> union of file-offset intervals
```

그리고 소스에 있는 모든 함수가 악성 함수인 것은 아니다. 초기화·로깅·메모리 관리·공용 라이브러리는 정상 기능일 수 있으므로, 2명 이상의 보안 분석가가 capability와 공격 목표에 비추어 component를 판정해야 한다.

## 2.6 PE 위치 대응은 단순 RVA 계산보다 복잡하다

PE section은 `VirtualAddress`, `VirtualSize`, `PointerToRawData`, `SizeOfRawData`를 가진다. disk bytes와 memory-mapped bytes의 길이가 다를 수 있고, 가상 zero-filled 영역이나 loader가 매핑하지 않는 certificate/debug data가 존재한다.

따라서 다음 공간을 명시적으로 구분한다.

- file offset space
- RVA space
- VA space
- disassembler instruction/basic-block space
- image pixel space

모든 변환은 한 함수로 뭉개지 말고 타입과 실패 상태를 가진다.

```text
file_offset_to_pixel(o) -> (x,y) or INVALID
rva_to_file_offset(r) -> o or UNMAPPED
file_offset_to_rva(o) -> r or NON_LOADED
```

## 2.7 bbox를 canonical ground truth로 사용하면 정보가 훼손된다

이미지 폭을 W라고 하면 file offset o의 일반적 raster 좌표는 다음과 같다.

```text
x = o mod W
y = floor(o / W)
```

연속 byte interval이 행 경계를 넘으면 2차원에서는 두 개 이상의 segment가 된다. 이를 하나의 bbox로 감싸면 관련 없는 byte가 다량 포함된다. 한 함수가 여러 basic block이나 cold code fragment로 분산되면 문제는 더 커진다.

따라서 canonical output은 다음 순서가 적절하다.

1. ranked byte intervals
2. function/basic-block IDs
3. pixel mask 또는 RLE
4. 시각화와 기존 detector 비교를 위한 derived bbox

AP50은 보조 지표일 뿐이며, 주 지표는 byte recall, function recall@budget, reviewed-byte fraction이어야 한다.

## 2.8 SAHI 명칭을 정확히 사용해야 한다

원래 SAHI는 학습된 객체 검출기를 overlapping slices에 적용하고 결과를 병합하는 detector-agnostic inference framework다. 단순히 tile embedding을 다시 계산하거나 MIL attention으로 타일을 선택하는 것만으로는 SAHI라고 부르기 어렵다.

두 선택지가 있다.

### 선택 A: SAHI를 실제로 유지

선택된 slice에서 pseudo-label 또는 gold/silver annotation으로 학습한 detector/segmenter를 실행하고, slice 결과를 전체 PE atlas에 병합한다.

### 선택 B: 명칭을 수정

`UA-BHSL: Upsampling-Assisted Budgeted Hierarchical Security Localization`처럼, SAHI가 아니라 `SAHI-inspired hierarchical slicing`으로 정의한다.

최상위 학회에서는 명칭의 정확성이 중요하므로, 현재 데이터가 detector training을 지지하지 않는다면 선택 B가 더 정직하다.

## 2.9 raw byte edge는 semantic boundary가 아니다

Upsample Anything은 입력 영상의 고해상도 edge 정보를 이용해 저해상도 feature/probability map을 복원한다. 하지만 byte intensity의 급격한 변화가 함수 경계나 악성 component 경계와 항상 일치하지는 않는다.

따라서 guidance를 단일 grayscale byte image로 제한하지 않는다.

- byte value channel
- local entropy channel
- section ID embedding
- R/W/X permission channels
- valid/raw/virtual byte mask
- optional instruction-boundary density

그리고 nearest, bilinear, bicubic, guided/JBU, UA를 모두 비교하며 UA의 per-image test-time optimization 비용을 end-to-end latency에 포함한다.

## 2.10 threat model을 먼저 제한해야 한다

초기 논문은 다음으로 범위를 제한하는 것이 안전하다.

- Windows native PE32/PE32+
- unpacked 또는 정적 disassembly가 가능한 표본
- self-modifying code 제외
- managed .NET 제외 또는 별도 track
- 분석 시 샘플을 실행하지 않음

packed/obfuscated malware는 일반화·실패 분석 track으로 두고, unpacking까지 해결했다고 주장하지 않는다.

---

## 3. 권장 논문 포지셔닝

### 권장 제목 1

**From File Labels to Byte Evidence: Budget-Aware Weakly Supervised Localization in Static PE Binaries**

### 권장 제목 2

**UA-SAHI-Mal: Budget-Aware Weakly Supervised Localization of Security-Relevant Regions in Static PE Binaries**

### 조건부 제목

**Bridging the Ground-Truth Gap: An Analyst-Audited Benchmark and Budgeted Localization Framework for Static PE Malware**

`malicious payload`는 shellcode·embedded payload처럼 더 좁은 의미로 해석될 수 있으므로, 실제 정답이 확보되기 전에는 `security-relevant byte regions` 또는 `malware components`가 안전하다.

### 한 문장 pitch

> UA-SAHI-Mal learns from file-level labels to rank and refine security-relevant byte intervals in high-resolution static PE representations, while an independently constructed, analyst-audited benchmark measures evidence recall under explicit analysis budgets.

---

## 4. 수정된 기여 항목

1. **Benchmark audit and task formalization**
   공개 정적 PE 데이터셋과 지역화 연구를 재현 가능한 프로토콜로 감사하고, file-level detection과 malicious-component retrieval을 구분한다.

2. **PEAtlas and canonical byte-evidence representation**
   file offset, RVA, section, instruction/function, pixel 사이를 가역적으로 연결하고, 정답을 bbox가 아닌 byte-interval union으로 보존한다.

3. **Budget-aware weakly supervised hierarchical localizer**
   file label, negative-bag supervision, relation-aware MIL, structure-guided UA, counterfactual consistency, uncertainty/coverage guard를 결합해 주어진 비용 안에서 증거를 선택·세분화한다.

4. **Multi-tier, non-pooled evaluation benchmark**
   controlled provenance, YARA/capa silver, source-grounded gold를 별도로 구축하고, 최종적으로 in-the-wild analyst audit을 수행한다.

5. **Analyst-centered Pareto evaluation**
   AP뿐 아니라 relevant-function recall, first-hit rank, reviewed bytes/functions, time-to-evidence와 end-to-end latency를 평가한다.

---

## 5. 제안 방법: 수정된 UA-SAHI-Mal

## 5.1 PEAtlas: 구조 보존형 가역 표현

PE 파일의 disk byte sequence를 `b=(b_0,...,b_{N-1})`라 한다. 각 byte에는 file offset, section, RVA 가능 여부, 권한, validity를 연결한다.

고정 폭 raster와 section-aligned atlas를 모두 구현한다.

### Raster baseline

```text
pi_W(o) = (o mod W, floor(o/W))
```

### Section-aligned atlas

각 section을 독립된 row band에 배치하여 section 사이의 인공적인 인접성을 줄인다. header, overlay, certificate/debug region을 별도 band로 둔다. 각 pixel에는 원 file offset 또는 `⊥`를 저장한다.

입력 채널 예시:

```text
X = [byte/255, local_entropy, section_id, is_read, is_write,
     is_execute, is_raw_valid, is_memory_mapped]
```

핵심 ablation:

- 1D raw bytes
- fixed-width grayscale raster
- section-aligned atlas
- Hilbert/space-filling layout(선택)

## 5.2 Weak coarse evidence learner

파일 i를 tile bag `B_i={t_ij}`로 표현하고, encoder `f_theta`로 tile embedding `h_ij`를 얻는다.

```text
h_ij = f_theta(t_ij)
```

relation-aware aggregator가 tile score `a_ij`와 file prediction `p_i`를 계산한다.

```text
a_i = g_phi({h_ij, position_ij, section_ij})
p_i = sigmoid(q(sum_j a_ij h_ij))
```

Negative PE는 모든 tile이 악성 evidence가 아니라는 더 강한 supervision을 제공한다. Positive PE에서는 일부 tile만 관련된 positive-unlabeled setting으로 처리한다.

## 5.3 Structure-guided UA evidence reconstruction

저해상도 evidence map `E_lr`을 PEAtlas guidance `G`로 고해상도 `E_hr`에 복원한다.

```text
E_hr = UA(E_lr, G; phi*)
```

`phi*`의 test-time optimization 비용을 반드시 총 시간에 포함한다. 또한 byte-only guidance와 multi-channel structural guidance를 비교한다.

## 5.4 예산 제한 선택

candidate tile `t_j`의 점수를 다음처럼 구성할 수 있다.

```text
s_j = evidence_j
    + alpha * uncertainty_j
    + beta  * novelty_j
    + gamma * section_coverage_j
```

비용 함수 `c(t_j)`와 예산 B 아래에서 집합 S를 선택한다.

```text
maximize    Sum_{j in S} s_j
subject to  Sum_{j in S} c(t_j) <= B
```

학습 시 soft top-k 또는 differentiable subset selection을 사용할 수 있고, 추론에서는 deterministic budgeted selection을 사용한다.

## 5.5 계층형 refinement

선택된 coarse tile만 더 작은 sub-tile로 분할한다.

```text
file -> coarse tiles -> selected tiles -> subtiles -> byte intervals
```

중단 기준:

- interval length threshold
- evidence concentration
- uncertainty threshold
- remaining budget

최종 출력은 다음이다.

```text
[(start_offset, end_offset, confidence, section, mapped_functions, evidence_source)]
```

## 5.6 학습 목적함수

권장 총 손실은 다음과 같다.

```text
L = L_file
  + lambda_neg  L_negative_instance
  + lambda_cons L_cross_layout_consistency
  + lambda_cf   L_counterfactual
  + lambda_stab L_perturbation_stability
  + lambda_cost max(0, C(S)-B)
```

- `L_file`: malware/benign classification
- `L_negative_instance`: benign file의 tile score 억제
- `L_cross_layout_consistency`: raster 폭·section layout이 바뀌어도 같은 byte interval 강조
- `L_counterfactual`: selected-only 입력은 예측을 유지하고, selected-deleted 입력은 악성 score를 낮춤
- `L_perturbation_stability`: 비실행 padding·row wrap 변화에 대한 안정성
- `L_cost`: 분석 예산 위반 패널티

---

## 6. 수정된 benchmark 설계

## Tier 0: Mapping and Transformation Unit Tests

목적은 모델 성능이 아니라 좌표 변환의 정확성 검증이다.

- PE parser 2종 이상 교차 검증
- random offset round trip
- RVA↔offset mapped/unmapped test
- section raw/virtual size 불일치
- overlay, certificate, debug region
- row-wrap mask generation
- function interval union rendering

통과 기준 예시:

```text
10^6 valid offset round trips에서 오류 0
모든 unmapped RVA가 명시적 INVALID 반환
mask->offset->mask exact equality
```

## Tier 1: Controlled-Provenance Benchmark

정상 프로그램에 안전하게 컴파일한 security-relevant module과 matched inert control을 삽입·링크한다.

변수:

- module capability
- 길이
- section
- 위치
- compiler/toolchain
- optimization
- entropy-matched control
- code vs data placement

이 tier는 mapping sanity와 spurious-cue 분석을 위한 것이며 실제 malware 결과로 과장하지 않는다.

## Tier 2: Silver Evidence Benchmark

- YARA match byte intervals
- capa instruction/basic-block/function matches
- EMBER2024-capa function fragments
- 필요 시 CAPA rule namespace와 ATT&CK/MBC category

필수 통제:

- training-rule/evaluation-rule 분리
- capability holdout
- family holdout
- duplicate function hash 제거
- gold와 결과를 절대 합산하지 않음

## Tier 3: Source-Grounded Gold Benchmark

후보:

- DeepReflect 공개 ground-truth artifact
- 공개 소스 malware 또는 연구용 안전 replica
- source-level security-relevant modules

정답 구축:

1. gold build 생성
2. PDB/DWARF/map/line table 수집
3. function/code chunk를 RVA 집합으로 추출
4. RVA를 file-offset interval union으로 변환
5. 두 명 이상의 분석가가 악성·지원·불확실 component 판정
6. disagreement adjudication
7. 원문 source reference와 provenance 저장

## Tier 4: In-the-Wild Analyst Audit

최상위 보안학회를 목표로 한다면 강하게 권장한다.

- unpacked, statically analyzable PE
- 모델별 blind/randomized presentation
- 최소 2~5명의 숙련 분석가
- 동일 시간 또는 동일 함수 검토 예산

측정:

- time-to-first-relevant-function
- precision@K functions
- relevant-function recall@K
- reviewed function/byte fraction
- analyst confidence
- inter-rater agreement
- 모델 제안이 최종 판단을 바꾼 비율

---

## 7. 연구질문

### RQ1. File-level validity

UA-SAHI-Mal이 EMBER LightGBM, MalConv 계열, full-image CNN/ViT, 고해상도 MIL과 비교해 file-level detection을 유지하는가?

### RQ2. Evidence localization under budget

동일한 tile/function/latency budget에서 UA-SAHI-Mal이 Random, Uniform, Entropy, CAM, MIL attention, DeepReflect보다 높은 gold relevant-component recall을 달성하는가?

### RQ3. Structure-guided reconstruction

UA가 bilinear, bicubic, guided/JBU보다 byte-level AUPRC, interval IoU, ranking stability를 개선하며 추가 비용을 정당화하는가?

### RQ4. Guard and objective contribution

uncertainty/coverage guard, counterfactual loss, layout consistency가 false-negative component와 shortcut reliance를 줄이는가?

### RQ5. Analyst utility

모델이 분석가의 검토 함수·바이트 수와 time-to-evidence를 실제로 감소시키는가?

### RQ6. Robustness and domain shift

compiler, optimization, packing, padding, family, temporal shift에서 증거 지역화가 얼마나 유지되는가?

### 조건부 RQ7. Small components

실제 gold component 크기 분포에서 작은 영역이 충분히 존재하고 full-image baseline의 성능 저하가 확인될 때만 small-object 분석을 추가한다.

---

## 8. 필수 baseline

## 8.1 File-level detection

- EMBER LightGBM
- MalConv/MalConv2
- full-image ResNet/EfficientNet/ViT
- Peters–Farhat high-resolution MIL
- PE-MILCon
- section-aware representation baseline
- UA-SAHI-Mal file head

## 8.2 Weak localization and retrieval

- Random-K
- uniform section/grid-K
- entropy-K
- Grad-CAM
- HiResCAM 또는 LayerCAM
- Integrated Gradients
- ABMIL
- CLAM
- DSMIL
- TransMIL
- Peters MIL attention
- PE-MILCon attention
- DeepReflect
- capa/YARA oracle output
- DLLicious/X-MinHash 계열(재현 가능한 범위)
- full exhaustive scan

## 8.3 Upsampling

- nearest
- bilinear
- bicubic
- guided filtering/JBU
- Upsample Anything

## 8.4 Ablation

- no UA
- no budget loss
- no counterfactual loss
- no consistency loss
- no uncertainty guard
- no coverage guard
- uncertainty only
- coverage only
- byte-only guidance
- structural guidance
- raster vs section atlas

---

## 9. 지표와 통계

## 9.1 File level

- PR-AUC
- ROC-AUC
- TPR at FPR 0.1% and 1%
- F1
- expected calibration error

## 9.2 Localization

주 지표:

- byte-level precision, recall, F1, AUPRC
- evidence recall at byte/function/latency budget
- relevant-function recall@K
- precision@K functions
- first relevant function rank
- reviewed-byte fraction
- reviewed-function fraction

보조 지표:

- interval IoU
- mask IoU/Dice
- derived bbox AP50/AP75
- boundary error

## 9.3 Efficiency

- coarse model time
- UA optimization time
- selection time
- fine refinement time
- disassembly/capa preprocessing time(온라인/오프라인 구분)
- end-to-end wall-clock latency
- throughput
- peak VRAM/RAM
- FLOPs 또는 detector/encoder calls

## 9.4 신뢰구간과 검정

- 최소 5개 seed 또는 bootstrap confidence interval
- 동일 sample에 대한 paired bootstrap/permutation test
- effect size 함께 보고
- family·time·compiler·packer별 stratified 결과
- 여러 tier를 하나의 숫자로 평균하지 않음

---

## 10. 데이터 분할과 누수 통제

- temporal split
- family-disjoint split
- compiler/toolchain-disjoint split
- source-project-disjoint split
- packer-disjoint split
- file hash 중복 제거
- TLSH/ssdeep near-duplicate cluster 분리
- function hash 중복 제거
- 동일 source function의 여러 build가 train/test에 나뉘지 않도록 group split
- YARA/capa rule 및 capability holdout

특히 EMBER2024-capa는 같은 함수가 여러 파일에 반복될 수 있으므로 function-level hash deduplication이 필수다.

---

## 11. 가장 위험한 리뷰어 공격과 답변 조건

| 리뷰어 공격 | 현재 설계의 취약점 | 방어 가능한 조건 |
|---|---|---|
| “공백이 이미 DeepReflect에 있다” | 최초 주장 과장 | 체계적 audit + 공개 byte-interval benchmark + 동일 조건 재평가 |
| “MIL attention은 설명이 아니다” | attention만 결과로 사용 | 독립 gold, deletion/sufficiency, analyst study |
| “marker를 찾았을 뿐” | EICAR/shellcode injection | matched controls와 source-grounded/in-the-wild 결과 분리 |
| “capa/YARA를 GT로 썼다” | circularity | silver로 명시, rule holdout, gold와 비혼합 |
| “PDB bbox가 잘못됐다” | 함수 연속성 가정 | interval union, gold build, optimized domain-shift track |
| “SAHI가 아니다” | detector 없음 | 실제 fine detector 도입 또는 명칭 수정 |
| “2D 이미지가 임의적이다” | row-width shortcut | 1D·raster·section atlas 비교와 layout consistency |
| “UA edge가 semantic edge가 아니다” | byte grayscale만 사용 | structural guidance와 upsampling ablation |
| “파일 라벨로 악성 함수 식별은 식별 불가능” | positive bag 혼합 | negative supervision, PU objective, analyst gold, 한계 명시 |
| “분석가에게 실제로 유용한가” | proxy metric만 존재 | Tier 4 analyst audit |

---

## 12. Go/No-Go 게이트

## G0. 좌표 무결성

- 모든 valid raw byte의 round-trip mapping이 정확한가?
- 함수가 interval union으로 정확히 복원되는가?

실패 시 논문 중단 또는 mapper 논문으로 축소한다.

## G1. Gold feasibility

- 최소 여러 family/source project에서 분석가 검증 component를 구축할 수 있는가?
- 한 family 또는 몇 개 sample에만 국한되지 않는가?

실패 시 `malicious localization` 표현을 버리고 `weak evidence retrieval`로 축소한다.

## G2. Weak-localization signal

- file classification 성능을 유지하면서 gold function recall이 Random/Entropy/MIL attention보다 개선되는가?
- selected evidence deletion 시 malware score가 일관되게 하락하는가?

실패 시 UA/selector를 재설계한다.

## G3. Budget Pareto

- exhaustive scan 대비 명확한 비용 절감과 작은 recall 감소 또는 동일 recall을 보이는가?
- UA TTO 비용을 포함해도 이득인가?

실패 시 UA를 제거하거나 offline kernel/cache 설계를 검토한다.

## G4. Analyst utility

- time-to-first-evidence와 reviewed-function fraction이 실질적으로 감소하는가?

실패 시 최상위 보안학회 주장이 약해진다.

## G5. Robustness

- layout, compiler, optimization, padding 변화에서 위치가 안정적인가?

실패 시 shortcut detector로 판정될 가능성이 높다.

---

## 13. 투고 전략

### 1순위: 보안 학회

USENIX Security, ACM CCS, IEEE S&P, NDSS가 가장 적합하다. 이 경우 시스템·보안 기여가 전면에 있어야 한다.

필수 요소:

- 현실적 threat model
- gold/silver 분리
- 공개 artifact 또는 재현 가능한 데이터 생성기
- adaptive/shortcut robustness
- 분석가 연구
- 윤리·안전 취급 절차

### 2순위: 보안 저널

IEEE TIFS 또는 IEEE TDSC는 benchmark와 실험 범위를 확장해 제출하기 적합하다. 학회보다 긴 평가와 추가 ablation을 수용하기 쉽다.

### 일반 ML 학회

NeurIPS·ICML·ICLR 본 트랙을 목표로 하면 다음이 추가로 필요하다.

- malware 밖의 고해상도 weak localization benchmark에서도 적용 가능
- budgeted subset selection의 일반적 학습 이론 또는 새로운 최적화
- 강한 MIL/WSOL baseline에 대한 일관된 우위
- task-specific engineering을 넘어선 일반성

현재 방향은 일반 ML보다 보안학회에 더 적합하다.

---

## 14. 수정된 논문 목차

1. Introduction
2. Motivation, Threat Model, and Task Definition
3. A Reproducible Audit of the PE Localization Ground-Truth Gap
4. PEAtlas: Invertible Structure-Preserving PE Representation
5. UA-SAHI-Mal: Budgeted Weak Evidence Localization
6. Multi-Tier Benchmark Construction
7. Experimental Methodology
8. Results
9. Analyst Study and Case Studies
10. Security and Robustness Analysis
11. Discussion, Ethics, and Limitations
12. Related Work
13. Conclusion

기존 설계의 Section 2를 단순한 비판문으로 쓰지 말고, 검색식·기간·데이터셋 포함 조건·제외 근거를 가진 systematic audit으로 만들어야 한다.

---

## 15. 최종 판단

### 현재 설계 그대로

- 연구 아이디어·문제 선택: 좋음
- top-tier security submission: 시기상조
- 가장 큰 문제: 평가 정답의 의미가 불명확하고 방법이 기존 MIL/top-K와 겹침

### 수정 설계로 진행할 경우

다음 네 가지가 확보되면 실제 논문으로 발전할 수 있다.

1. source/analyst-grounded byte-interval gold benchmark
2. CAM/MIL 이상의 학습·선택 기여
3. exhaustive scan 대비 명확한 recall–cost Pareto 개선
4. 실제 분석가 workload 감소

즉 이 연구는 **쓸 수 있는 논문**이다. 다만 성공의 중심은 YOLO나 SAHI라는 이름이 아니라, `신뢰 가능한 byte evidence`, `독립 평가`, `분석 예산`, `분석가 효용`에 있다.

---

## 참고문헌 및 핵심 자료

1. Downing, E. et al. *DeepReflect: Discovering Malicious Functionality through Binary Reconstruction*. USENIX Security, 2021. https://www.usenix.org/conference/usenixsecurity21/presentation/downing
2. Peters, T. and Farhat, H. *High-resolution Image-based Malware Classification using Multiple Instance Learning*. arXiv:2311.12760, 2023. https://arxiv.org/abs/2311.12760
3. Kim, T. N. et al. *PE-MILCon: Multiple-Instance Learning with Contrastive Multi-View Representation for Static Windows PE Malware Detection*. Computers, Materials & Continua, 2026. https://doi.org/10.32604/cmc.2026.084268
4. Yevsikov, A. and Nissim, N. *DLLicious: Detection and Explainability of Malicious DLL Files Using Novel Static Feature Extraction Methods*. Expert Systems with Applications, 2026. https://doi.org/10.1016/j.eswa.2026.132188
5. Seo, M. et al. *Upsample Anything: A Simple and Hard to Beat Baseline for Feature Upsampling*. CVPR, 2026. https://arxiv.org/abs/2511.16301
6. Akyon, F. C. et al. *Slicing Aided Hyper Inference and Fine-tuning for Small Object Detection*. ICIP, 2022. https://doi.org/10.1109/ICIP46576.2022.9897990
7. Ilse, M. et al. *Attention-based Deep Multiple Instance Learning*. ICML, 2018. https://proceedings.mlr.press/v80/ilse18a.html
8. Lu, M. Y. et al. *Data-efficient and Weakly Supervised Computational Pathology on Whole-slide Images*. Nature Biomedical Engineering, 2021. https://doi.org/10.1038/s41551-020-00682-w
9. Li, B. et al. *Dual-stream Multiple Instance Learning Network for Whole Slide Image Classification*. CVPR, 2021. https://arxiv.org/abs/2011.08939
10. Shao, Z. et al. *TransMIL: Transformer-based Correlated Multiple Instance Learning*. NeurIPS, 2021. https://proceedings.neurips.cc/paper/2021/hash/10c272d06794d3e5785d5e7c5356e9ff-Abstract.html
11. Joyce, R. J. et al. *EMBER2024: A Benchmark Dataset for Holistic Evaluation of Malware Classifiers*. KDD, 2025. https://arxiv.org/abs/2506.05074
12. Anderson, H. S. and Roth, P. *EMBER: An Open Dataset for Training Static PE Malware Machine Learning Models*. 2018. https://arxiv.org/abs/1804.04637
13. Yang, L. et al. *BODMAS: An Open Dataset for Learning-based Temporal Analysis of PE Malware*. DLS, 2021. https://whyisyoung.github.io/BODMAS/
14. Mandiant. *capa: Extract Capabilities from Executable Files*. https://mandiant.github.io/capa/
15. VirusTotal. *YARA C API*. https://yara.readthedocs.io/en/latest/capi.html
16. Microsoft. *PE Format*. https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
17. Microsoft. *Debugging Optimized Code and Inline Functions*. https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/debugging-optimized-code-and-inline-functions-external
18. Demetrio, L. and Biggio, B. *secml-malware: A Python Library for Adversarial Robustness Evaluation of Windows Malware Classifiers*. 2021. https://github.com/pralab/secml_malware
