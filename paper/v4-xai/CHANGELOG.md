# XAI-v4 변경 이력

## 2026-09-14 — XAI-V4.0-DRAFT

- v3 static silver-evidence retrieval 연구선을 활성 논문 방향에서 내리고 보존 상태로 전환
- Grad-CAM 시각화 중심 아이디어를 faithfulness evaluation 중심으로 수정
- `악성 구역`을 `패밀리 판정 근거 후보`로 제한
- BIG2015를 주 데이터, MaleVis 224를 보조 데이터, SOREL을 선택적 구조/silver 감사로 결정
- Maldataset-2021의 `phoenixml` 출처와 역매핑 가능성을 미확인 상태로 기록
- ResNet-18을 주 모델, ResNet-50을 reference model로 조정
- valid area 기준 5/10/20/40% 예산과 10% primary budget 정의
- deletion, keep-only, randomization sanity, seed stability, 구조 enrichment를 필수 평가로 정의
- 결과가 없는 국문 논문 초안과 결과 입력 표 생성
- 국문 초안 3.2절에 VA 좌표, validity, 224×224 집계, CAM-to-address 투영 계약을 추가
- 설계값과 미확정 동결값을 분리한 `protocol/XAI_V4_0_DRAFT.yaml` 추가

## 다음 revision 조건

`XAI-V4.1-FROZEN`은 데이터 manifest, split hash, 입력 표현, 모델 설정, target layer,
fill, primary 통계를 확정한 커밋에만 부여한다.

test 결과를 본 뒤 변경한 분석은 `XAI-V4.2-EXPLORATORY`에 기록하며 v4.1의 gate를
소급 변경하지 않는다.
