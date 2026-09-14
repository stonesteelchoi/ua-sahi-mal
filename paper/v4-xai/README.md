# XAI-v4 paper workspace

## 현재 상태

- 연구선: `XAI-v4`
- 문서 상태: 설계 초안
- 코드 브랜치: `research/xai-v4`
- 기준 커밋: `6581b2f6d5437c6feb742dae5793457577bd8945`
- v4 실제 결과: 없음
- 주 데이터 후보: Microsoft BIG2015 파생 코퍼스
- 보조 데이터 후보: MaleVis 224×224
- 선택적 외부 감사: SOREL-20M disarmed 파일럿

이 폴더는 설명 가능한 악성코드 이미지 분류 연구의 단일 진입점이다. 과거 v1–v3
연구선은 보존하지만, 그 수치와 체크포인트를 v4 결과로 이월하지 않는다.

## 연구의 한 문장 정의

> 파일 수준 패밀리 라벨로 학습한 악성코드 이미지 분류기의 Grad-CAM 영역이 동일
> 면적의 무작위·엔트로피 영역보다 실제 분류 결정에 더 필요한지 검증하고, 그 설명이
> PE 관련 구조 구간과 어떻게 대응하는지 분석한다.

## 문서 지도

| 문서 | 역할 |
|---|---|
| [`RESEARCH_DESIGN.md`](RESEARCH_DESIGN.md) | 연구 질문, 기여, 방법, 지표, 범위 |
| [`DATASET_DECISION.md`](DATASET_DECISION.md) | 보유 데이터 비교와 최종 선택 규칙 |
| [`KISA_DATASET_AUDIT.md`](KISA_DATASET_AUDIT.md) | KISA 공개 악성코드 목록의 적합성·접근조건·전환 기준 |
| [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md) | 분할, 학습, XAI, 통계, 성공 게이트 |
| [`protocol/XAI_V4_0_DRAFT.yaml`](protocol/XAI_V4_0_DRAFT.yaml) | 설계값과 미확정값을 구분한 기계 판독 protocol snapshot |
| [`draft/PAPER_DRAFT_KO.md`](draft/PAPER_DRAFT_KO.md) | 결과를 꾸며 넣지 않은 국문 논문 초안 |
| [`CHANGELOG.md`](CHANGELOG.md) | v4 문서와 프로토콜 변경 이력 |
| [`../decisions/ADR-002-xai-v4-direction.md`](../decisions/ADR-002-xai-v4-direction.md) | v3에서 v4로 전환한 결정 기록 |

## 허용되는 용어

- `패밀리 판정 근거 후보`
- `모델 귀속 영역(model-attributed region)`
- `약지도 설명 영역`
- `예산 제한 설명(budgeted explanation)`
- `구조 정합성(structural alignment)`

다음 표현은 별도 근거를 확보하기 전에는 사용하지 않는다.

- `실제 악성 코드 구역`
- `악성 행위 ground truth`
- `정확한 바이트 오프셋 복원`
- `리버싱 시간 대폭 단축`
- `Grad-CAM이 패밀리 고유 구조를 입증`

## 버전 규칙

1. 설계 문서의 초기 식별자는 `XAI-V4.0-DRAFT`이다.
2. 데이터셋, 분할, 모델, target layer, 예산, 지표를 확정하면
   `XAI-V4.1-FROZEN`으로 올리고 해당 커밋에 태그를 붙인다.
3. test 결과를 본 뒤 프로토콜을 바꾸면 `XAI-V4.2-EXPLORATORY`로 분리한다.
4. 실행 디렉터리는 `runs/xai-v4/<protocol>/<dataset>/<model>/<seed>/`를 사용한다.
5. 체크포인트에는 데이터 revision, split hash, 모델, seed를 기록한다.
6. 표와 그림은 저장된 per-sample 결과에서 생성하며 수동으로 숫자를 옮기지 않는다.
7. 실제 데이터, 가역 이미지, 모델 체크포인트는 Git에 커밋하지 않는다.

## 최소 완료 조건

- BIG2015 validity 처리를 수정한 새 데이터 revision
- 정확 중복 및 가능한 근접 중복을 그룹화한 고정 split
- 동일 split에서 학습한 3-seed 분류기
- Grad-CAM, random-area, entropy-area 비교
- 5/10/20/40% 면적 예산별 실제 재추론 deletion과 keep-only 평가
- 최소 두 가지 fill에 대한 민감도 분석
- 모든 결과와 실패를 포함한 per-sample record
- 제출용 표·그림과 본문의 수치 자동 대조

분류 성능만 나오고 explanation gate가 실패하면 논문은 “효과적인 국지화 방법”이
아니라 “악성코드 이미지에서 Grad-CAM 설명의 충실성 한계” 평가 논문으로 마무리한다.
