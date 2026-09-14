# KISA-XAI v5 paper workspace

## 현재 상태

- 연구선: `KISA-XAI-v5`
- 프로토콜: `KISA-XAI-V5.0-DRAFT`
- 상태: 데이터 접근 전 설계 초안
- 과제: 정적 Windows PE 정상·악성 이진 탐지
- 주 데이터 후보: `KISA_CISC2017_datachallenge_Malwares.01`
- 외부 평가 후보: `KISA-datachallenge2018-Malwares.03`의 라벨 보유 PE 부분집합
- 주 모델: ResNet-18
- 주 설명기: Grad-CAM
- 주 설명 예산: 원본 파일 바이트의 10%
- 실제 v5 결과: 없음

이 폴더는 KISA 원본 정상·악성파일을 사용한 이진 탐지와 XAI 평가 연구의 단일
진입점이다. 패밀리 분류를 다룬 `v4-xai`는 이전 설계로 보존하며, 데이터·라벨·결과를
v5와 합치지 않는다.

## 연구의 한 문장 정의

> KISA 원본 PE로 학습한 정적 악성코드 탐지기의 Grad-CAM 상위 구간이 동일 바이트
> 예산의 무작위·엔트로피·위치·구조 일치 대조군보다 악성 판정에 더 필요하고 충분한지
> 검증하고, 그 효과와 PE 구조 분포가 다른 연도 데이터셋에서도 유지되는지 평가한다.

## 문서 지도

| 문서 | 역할 |
|---|---|
| [`RESEARCH_PROPOSAL_KO.md`](RESEARCH_PROPOSAL_KO.md) | 제출·검토용 국문 연구계획서 원본 |
| [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | 데이터 감사, 학습, XAI, 통계, 종료 규칙 |
| [`protocol/KISA_XAI_V5_0_DRAFT.yaml`](protocol/KISA_XAI_V5_0_DRAFT.yaml) | 기계 판독 가능한 설계 스냅샷 |
| [`deliverables/최석철_개인프로젝트계획서_KISA_XAI_v5.docx`](deliverables/최석철_개인프로젝트계획서_KISA_XAI_v5.docx) | 제출·공유용 Word 문서 |
| [`CHANGELOG.md`](CHANGELOG.md) | v5 변경 이력 |
| [`../decisions/ADR-003-kisa-binary-xai.md`](../decisions/ADR-003-kisa-binary-xai.md) | v4 패밀리 분류에서 v5 이진 탐지로 전환한 결정 |

## 데이터 사용 결정

1. KISA 2017 대용량 정상/악성파일 I의 실제 archive와 이용조건을 확인한 뒤 주 데이터로
   승격한다.
2. 2017 자료를 확보하지 못하고 KISA 2018의 라벨 보유 세트를 확보한 경우, suffix 감사를
   통과한 PE만 주 데이터로 사용할 수 있다.
3. KISA 2018을 주 데이터로 사용하면 외부 평가는 KISA 2019의 라벨 보유 PE 부분집합으로
   이동한다.
4. BIG2015와 MaleVis는 v5 결과에 합치지 않는다. SOREL-20M disarmed 파일럿은 PEAtlas의
   좌표 변환 회귀 검사에만 사용하며 탐지 성능이나 XAI 효과 추정에는 포함하지 않는다.
5. KISA archive를 확보하지 못하면 v5는 설계 초안으로 남고, 실제 결과가 있는 논문으로
   제출하지 않는다.

## 동결 조건

다음 사항을 모두 채운 커밋만 `KISA-XAI-V5.1-FROZEN`으로 올린다.

- 데이터 이용조건과 archive hash
- 파일 수, 라벨 결합률, PE32/PE32+ 수와 제외 사유
- suffix 및 dataset marker 감사 결과
- exact·near-duplicate group과 split hash
- 입력 표현, pixel-to-file-offset map, 모델, seed, target layer
- deletion fill, 대조군, 예산, 주 지표와 통계 검정
- test 및 외부 데이터 봉인 절차

## 주장 언어

사용 가능한 표현은 `모델 귀속 구간`, `악성 판정 근거 후보`, `설명 충실성`, `PE 구조
정합성`, `교차연도 외부 평가`이다. 위치 정답이나 분석가 실험 없이 `실제 악성 코드
구간`, `악성 행위 위치`, `리버싱 시간 단축`, `시간적 강건성 입증`이라고 쓰지 않는다.
