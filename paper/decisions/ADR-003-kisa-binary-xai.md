# ADR-003: KISA 원본 PE 이진 탐지와 구조 매핑 XAI로 전환

- 상태: Accepted
- 결정일: 2026-09-14
- 대체하는 활성 설계: `XAI-V4.0-DRAFT`
- 새 설계: `KISA-XAI-V5.0-DRAFT`

## 배경

XAI-v4는 BIG2015 패밀리 분류기의 Grad-CAM 충실성과 구조 정합을 평가하도록 설계되었다.
그러나 BIG2015 `.bytes`는 원본 PE file offset이 아닌 address-indexed dump이고, KISA 공개
목록에는 정상·악성 원본 파일과 이진 정답지를 제공한다고 설명된 데이터가 존재한다.

사용자는 패밀리 분류를 유지하는 선택보다 KISA 원본 파일을 이용한 정상·악성 이진
탐지와 교차연도 XAI 평가를 선택했다.

## 결정

1. 새 연구선을 `KISA-XAI-v5`로 분리한다.
2. KISA 2017 대용량 정상/악성파일 I을 접근 조건부 주 데이터로 둔다.
3. KISA 2018 라벨 보유 PE 부분집합을 우선 외부 평가로 둔다.
4. Grad-CAM 영역은 실제 악성 코드 정답이 아니라 모델 귀속 구간으로 취급한다.
5. 설명의 필요성과 충분성을 deletion·keep-only 및 structure-matched random으로 검증한다.
6. archive, 이용조건, PE 비율, suffix, 중복과 metadata shortcut 감사를 통과하기 전에는
   프로토콜을 동결하거나 결과를 주장하지 않는다.

## 이유

- 원본 PE는 file offset, RVA, section, certificate 및 overlay를 직접 계산할 수 있다.
- 정상과 악성 라벨이 있어 악성 판정 logit에 대한 설명을 정의할 수 있다.
- 2017과 2018/2019 세트가 모두 사용 가능하면 교차연도 외부 평가를 설계할 수 있다.
- 패밀리 라벨이 없으므로 기존 family-classification 제목을 유지하는 것보다 과제를
  이진 탐지로 명시하는 것이 타당하다.

## 결과와 제약

- XAI-v4 문서와 수치는 수정하거나 v5에 합치지 않는다.
- v5의 주요 기여는 새 탐지기보다 설명 평가와 좌표·누수 감사 프로토콜이다.
- KISA 접근이 실패하면 v5 empirical paper는 진행할 수 없다.
- 외부 데이터셋의 challenge 연도를 실제 sample 수집일로 해석하지 않는다.
- 위치 ground truth가 없으므로 semantic malicious-code localization을 주장하지 않는다.

## 검토한 대안

### BIG2015 패밀리 분류 유지

이미 보유한 자료를 활용할 수 있으나 원본 PE file-offset 주장과 정상·악성 탐지 과제를
직접 지원하지 않는다. 이전 설계로 보존한다.

### MaleVis 또는 PNG-only 데이터로 교체

빠른 이미지 분류에는 적합하지만 원본 PE 구조와 file offset을 검증할 수 없어 이번
연구 질문과 맞지 않는다.

### KISA 여러 연도를 합쳐 하나의 무작위 split 생성

sample 수는 늘지만 dataset marker와 연도 누수를 숨기고 외부 평가를 없애므로 채택하지
않는다.
