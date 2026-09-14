# KISA-XAI v5 변경 이력

## 2026-09-14 — KISA-XAI-V5.0-DRAFT

- 패밀리 분류 중심 XAI-v4를 보존하고 정적 PE 정상·악성 이진 탐지 연구선을 분리
- KISA 2017 대용량 정상/악성파일 I을 접근 조건부 주 데이터로 결정
- KISA 2018 라벨 보유 PE를 우선 외부 평가 후보로 결정
- 2017 접근 실패 시 2018→2019 순서의 조건부 대체 경로 정의
- 원본 바이트와 224×224 픽셀의 half-open interval map을 보존하는 입력 계약 정의
- Grad-CAM 대 structure-matched random의 10% 바이트 예산 H1/H2를 primary로 정의
- deletion, keep-only, randomization sanity, seed·fill 안정성, 구조 enrichment를 필수화
- metadata-only shortcut, suffix, file type, exact·near-duplicate 누수 감사 gate 추가
- 긍정·부분·부정·dataset-bias 결과별 종료 규칙 정의
- 국문 연구계획서, 실행 프로토콜, 기계 판독 YAML 작성

## 다음 revision 조건

KISA archive와 이용조건을 확보하고 P0 감사를 통과한 뒤 데이터 revision, split hash,
모델, target layer, fill 및 통계를 고정한 커밋만 `KISA-XAI-V5.1-FROZEN`으로 올린다.
