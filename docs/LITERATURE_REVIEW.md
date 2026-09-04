# 악성코드 바이트 이미지 XAI 선행연구 점검

- **검색일:** 2026-09-04
- **범위:** 악성코드 이미지의 saliency/occlusion 검증, raw-byte 모델의 구간 귀속, 교차 모델·교차 표현 검증, 전역 통계 의존, 경계 인식 업샘플링
- **주의:** 이 문서는 논문의 체계적 문헌고찰을 대신하지 않는다. 아래는 제목·초록 검색에서 끝내지 않고 확인 가능한 원 논문·공식 저장소의 방법과 주장까지 대조한 우선 문헌 집합이다.

> **범위 상태:** v2 BIG2015/XAI 연구선의 문헌 감사다. v3 static PE
> malicious-component 논문의 기준 문헌과 live artifact 상태는
> [`../paper/references/README.md`](../paper/references/README.md)에서 관리한다.

## 1. 결론

“악성코드 이미지 설명을 처음 정량 검증한다” 또는 “악성코드 바이트 구간을 처음
귀속한다”는 신규성 주장은 **성립하지 않는다**. 적어도 다음이 이미 존재한다.

- BIG2015·MalImg를 포함해 여러 CNN의 Grad-CAM/HiResCAM을 비교하고, 두 모델의
  누적 heatmap을 결합한 마스크로 별도 ViT를 학습한 연구가 있다.
- malware image의 Grad-CAM을 여러 변환·faithfulness·stability 지표로 비교한
  2026년 연구가 있다.
- raw-byte MalConv에서 byte attribution을 PE 영역·하위 구간으로 집계하고 실제
  기능 보존 perturbation/evasion으로 영향력을 검증한 연구가 있다.
- PE 섹션을 가리는 occlusion으로 malware image 설명을 검증한 2026년 학위논문도
  있다.

현재 프로젝트가 주장할 수 있는 더 좁은 차별점은 다음 조합이다.

1. **탐색에 참여하지 않은 모델**에서 동일 구간을 다시 가리는 교차 모델 검증,
2. 이미지를 보지 않는 histogram+bigram 모델까지 옮기는 **교차 표현 검증**,
3. 동일 geometry의 무작위 위치 대조와 여러 fill을 함께 둔 perturbation 대조,
4. “어디가 중요한가”가 아니라 **국소 답이 없을 때 어느 크기부터 검출되는가**를
   사전등록 기준과 감도 곡선으로 보고하는 것,
5. BIG2015 `.bytes`의 VA 정렬과 raw-value guide의 부적합을 결합해 경계 인식
   업샘플링의 실패 조건을 바이트 단위로 설명한 것.

단, 1–4는 현재 validity-mask 교란을 제거해 재실행하기 전에는 결과 주장이 아니라
**검증할 설계상의 차별점**일 뿐이다.

## 2. 직접 겹치는 문헌

| 연구 | 입력·과제 | 설명과 검증 | 본 연구와 겹침 | 남는 차이 |
|---|---|---|---|---|
| Brosolo, Puthuvath, Conti, “Through the Static” (JISA 2025) | MalImg, BIG2015, VX-Zoo의 정적 malware image family 분류 | 6개 CNN 재현, Grad-CAM/HiResCAM, 모델 쌍 누적 heatmap SSIM, 덜 중요한 영역을 가린 데이터로 별도 ViT 학습 | BIG2015, malware-image XAI, 모델 간 heatmap 비교, saliency mask | 원 모델의 인과적 deletion이 아니라 mask로 **재학습**한 성능 비교. 독립 모델에서 같은 byte range의 필요성, 비이미지 표현, matched random control은 없음 |
| Bhavikatti, Stamp, “A Comparison of Malware Image Transformations…” (arXiv 2026-08-12) | RawMal-TF 17 family, 8개 image transformation | Grad-CAM/HiResCAM과 정량 faithfulness·stability; 설명 품질과 정확도가 일치하지 않음 | malware-image 설명의 정량 faithfulness라는 넓은 신규성은 소멸 | 공개 초록 기준으로 byte-range 교차 모델/교차 표현 검증과 검출 하한은 확인되지 않음. 최종 원고에서 사용 지표를 직접 대조해야 함 |
| Ebrahimi, Jurecek, Stamp, “CAM-Guided Saliency Cutout…” (arXiv 2026-08-12) | RawMal-TF와 CIFAR-100, ResNet18 | HiResCAM 기반 high/low-saliency 및 random cutout 5–30%를 학습 증강으로 비교; malware에서는 모두 no-cutout보다 소폭 저하 | “자연영상용 부품의 malware image 전이는 실패할 수 있다”는 서사와 saliency 마스킹 | 설명의 인과적 귀속 검증이 아니라 training augmentation. 동일 파일의 necessity/sufficiency나 byte 좌표 평가는 아님 |
| de Jonge, “An analysis of different xAI methods…” (TU Delft 학사논문 2026) | PE/ELF malware image, ResNet-18 | Grad-CAM·LIME·SHAP 영역을 named binary section으로 매핑, family별 상위 3 section occlusion 시 accuracy 50% 미만 | malware image의 영역 설명을 실제 occlusion으로 검증했다는 직접 선행 | 동료심사 논문은 아니지만 선행 결과로는 공개됨. 고정 4 KB, matched random, fill 강건성, 교차 모델/표현은 없음 |
| Demetrio et al., “Explaining Vulnerabilities…” (2019) | raw-byte MalConv, benign/malware detection | Integrated Gradients를 PE 구조로 매핑; header가 핵심임을 발견하고 수십 byte header attack으로 확인 | byte attribution과 실제 perturbation 검증은 이미 존재 | family 분류가 아니며 malware image가 아님. 오히려 “raw-byte 모델은 전역 통계에 의존한다”는 보편 명제의 반례 |
| Aryal et al., “Explainability Guided Adversarial Evasion…” (2024) | MalConv, 2,000,000-byte PE, benign/malware | byte별 SHAP을 PE 영역과 하위 구간으로 합산, 4,096-byte 단위 등을 실제 adversarial injection/evasion과 연결 | MalConv의 구간 단위 귀속·평가와 4 KB granularity가 직접 겹침 | 공격 성공률이 검증 목표이고 한 모델의 자기 설명이다. 독립 모델/표현으로 동일 evidence를 검증하지 않음 |
| Uysal et al., DECODE (Scientific Reports 2025) | CAPE 동적 API call을 4개 128×128 행동 이미지로 변환, 8개 행위 category | MC-dropout Bayesian Grad-CAM으로 pseudo-region 생성, 시각 유사성 grouping, EfficientDet, API call 역매핑, 다중라벨 | XAI로 자동 ROI를 만들고 detector를 학습하는 프로젝트 v1의 핵심 아이디어와 직접 겹침 | 입력 의미가 동적 행위이며 ground truth가 teacher-generated pseudo-label. 정적 BIG2015 byte evidence의 인과 검증 baseline은 아님 |

### 원문 링크

- Brosolo et al.: [arXiv 원문](https://arxiv.org/abs/2503.02441),
  [JISA DOI](https://doi.org/10.1016/j.jisa.2025.104063)
- Bhavikatti & Stamp: [arXiv 원문](https://arxiv.org/abs/2608.12077)
- Ebrahimi et al.: [arXiv 원문](https://arxiv.org/abs/2608.11634)
- de Jonge: [TU Delft 원문 기록](https://resolver.tudelft.nl/uuid:d283eb65-6711-4ec8-9fa0-5e564d217b99)
- Demetrio et al.: [arXiv 원문](https://arxiv.org/abs/1901.03583)
- Aryal et al.: [arXiv 원문](https://arxiv.org/abs/2405.01728)
- Uysal et al.: [Scientific Reports 원문](https://www.nature.com/articles/s41598-025-21848-z),
  [공식 코드](https://github.com/dtuuba/DECODE-DEep_Classification_Of_Dynamic_Exploits)

## 3. 질문별 판정

### 악성코드 이미지에 occlusion/deletion-insertion을 적용해 인과 검증했는가

**있다.** de Jonge는 중요 PE/ELF section을 가리고 분류 정확도 변화를 측정한다.
Brosolo et al.은 CAM으로 정한 비중요 영역을 가린 데이터를 별도 ViT에 학습시켜
유용성을 검증한다. 두 설계는 현재 프로토콜과 같지는 않지만 “악성코드 이미지
설명을 perturbation으로 처음 검증”이라는 문장을 무효로 하기에 충분하다.

Bhavikatti & Stamp는 2026년 8월 논문에서 malware-image Grad-CAM의 정량
faithfulness를 명시한다. PDF의 지표 정의까지 논문 관련연구에 옮기기 전에 반드시
확인해야 한다. 공개 HTML이 없어 이번 점검에서는 초록 이상의 세부 수치까지
검증하지 못했다.

### byte evidence를 교차 모델 또는 교차 표현으로 검증했는가

여러 모델의 **heatmap 유사성**은 Brosolo et al.에 있다. 그러나 모델 A에서 찾은
동일 byte range를 독립 모델 B와 비이미지 C에서 다시 perturb해 necessity를 검증한
동일 설계는 이번 검색 범위에서 확인하지 못했다. “없다”가 아니라 **확인하지
못했다**고 써야 한다. 이 조합은 현재 가장 유망한 제한적 신규성이다.

### MalConv 계열 attribution을 구간 단위로 평가했는가

**있다.** Demetrio et al.은 Integrated Gradients를 PE component와 연결하고 실제
header attack으로 검증했다. Aryal et al.은 byte SHAP을 PE region과 subsection으로
합산하고 위치별 기능 보존 공격 성능을 비교했다. 따라서 “최초의 byte-range
attribution”은 주장할 수 없다.

### malware image classifier가 전역 통계에 의존함을 보였는가

전역/texture 통계만으로 family가 분류된다는 연구는 오래전부터 많다. 예를 들어
Nataraj 계열은 GIST texture, Roseline et al.은 1·2차 texture 통계를, MDMC는 byte
Markov transition의 전역 통계를 명시적으로 사용한다. 이는 전역 통계가 **충분할
수 있음**을 보이지만, 특정 CNN이 국소 신호 대신 전역 통계에 **의존함**을
인과적으로 보인 것은 아니다.

반대로 Demetrio et al.의 MalConv는 header라는 국소 영역에 크게 의존했다.
따라서 본 연구의 결론은 “악성코드 분류기는 전역 통계에 의존한다”가 아니라
“**이 BIG2015 `.bytes` 표현과 이 모델군에서는, 4 KB–1/16 범위의 국소 필요성보다
분산된 통계 신호가 관측됐다**”로 제한해야 한다.

### byte image에서 경계 인식 업샘플링 실패가 보고됐는가

이번 검색에서 JBU/UPA 등 guidance-aware feature upsampling을 malware byte image
경계 복원에 적용해 bilinear와 바이트 단위로 비교한 선행연구는 확인하지 못했다.
PAFE 등은 bilinear가 texture를 바꾼다고 지적하고 padding을 제안하지만, feature-map
경계 복원 실험은 아니다. 그러므로 실험 2의 구체적 실패 조건은 비교적 독창적일
가능성이 높다. 다만 실제 UPA를 측정하지 않았으므로 “경계 인식 업샘플링 전체가
실패한다”가 아니라 “raw-byte/row-entropy guidance를 쓴 고정 JBU가 이 좌표계에서
bilinear를 이기지 못했다”고 써야 한다.

## 4. 논문에서 버려야 할 주장과 남길 주장

버려야 한다.

- 최초의 malware-image XAI 또는 최초의 정량 faithfulness 평가
- 최초의 byte-level/region-level MalConv attribution
- 모든 malware image classifier는 전역 통계에 의존한다
- UPA가 실패했다, 또는 learned boundary-aware upsampling 전체가 실패했다
- heatmap이 겹치므로 설명이 맞다는 식의 model-agreement 주장

조건부로 남길 수 있다.

- 독립 모델·비이미지 표현·matched random·fill sensitivity를 한 프로토콜에 묶은
  **검증 설계**
- 국소 evidence가 존재하지 않는 조건에서 occlusion search가 보이는 검출 하한과
  통제군 붕괴 지점
- BIG2015 `.bytes`의 VA alignment와 guide discriminability를 연결한 JBU 실패
  메커니즘
- 모든 사전 기준을 그대로 공개한 부정 결과와 재현 가능한 산출물

## 5. 검색의 한계와 다음 확인

- 2026-08-12 공개된 Bhavikatti & Stamp PDF는 파일이 커서 이번 웹 점검에서 본문
  지표 정의를 추출하지 못했다. 투고 전 PDF를 직접 읽고 deletion/insertion,
  randomization, stability의 정확한 정의를 표로 대조해야 한다.
- de Jonge는 학사논문이며 동료심사 논문이 아니다. 그래도 공개 선행 결과이므로
  관련연구에서 빼면 안 된다.
- 키워드 검색은 누락될 수 있다. 최종 원고에서는 위 7편의 backward/forward
  citation chasing을 추가하고, 검색 데이터베이스·날짜·질의를 부록에 남겨야 한다.
- “교차 표현 perturbation 검증을 찾지 못했다”는 현재 검색 결과이지 부재 증명이
  아니다. 신규성 문구는 “to our knowledge”와 정확한 구성요소 조합으로 제한한다.
