# KISA-XAI v5 변경 이력

## 2026-09-14 (2차) — P0 데이터 접근 사전 점검, 환경 회귀검사, xai 의존성 그룹

- `audit/DATA_ACCESS_AUDIT_2026-09-14.md`·`audit/data_access_audit_20260914.json`: KISA 2017/2018/2019
  공식 페이지에 다운로드·신청·로그인·약관 요소가 없고 신청 메뉴(`278.do`)가 삭제 상태임을 확인.
  현재 확인된 채널은 KISA 사이버보안빅데이터센터(방문 분석, 원본 반출 불가, 폐쇄망)와 C-TAS(회원 승인).
  P0 판정 **NO-GO(접근 대기)**. 프로토콜 수치는 변경하지 않음(V5.0-DRAFT 유지).
- `audit/ENV_CHECK_2026-09-14_cloud-linux-cpu.md`: Linux CPU 샌드박스에서 torch 2.8.0/torchvision 0.23.0
  설치, pytest 390 통과, smoke·evidence smoke·안전검사·수치감사·build 통과. CUDA 검사는 GPU 부재로 미수행.
- `pyproject.toml`: `xai` 선택 의존성 그룹 추가(grad-cam 1.5.x, scikit-learn, scipy, pefile,
  opencv-python-headless<5 고정). CPU Grad-CAM 1건과 empty-CAM 사례 재현.
- `scripts/kisa_xai_env_check.ps1`: Windows NVIDIA 장비용 환경·CUDA·회귀검사 일괄 기록 스크립트 추가.

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
