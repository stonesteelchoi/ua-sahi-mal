목표: PSA-XAI P2 파서 정책을 비조작 원칙으로 확정·검증하고 동결 후 학습·XAI 실험을 재현 가능하게 수행한다.
완료: C0, C1, C2a, C2b, C3, C4, C5(사용자 실행 완료), C6, C6 보완, C7, C8a(준비), C8b-a, C8b-b, C8b-c(C8b 종결), C8p(YAML 보완)
다음: C8r — 사용자 재학습 완료 후 seed 42·43·44 검증 / C8 gate와 방향 일치 확인
남은 청크: C8r 재학습 결과 재검증; C9 승인 후 XAI; C10 통계·결과 문서

확정 규칙·결정(형식·기준 포함):
- 세션당 청크 1개만 수행하며 완료 전 다음 청크로 이동하지 않는다. 청크당 새 파일 3개, 웹 검색 2회, 수정·생성 파일 5개 이하.
- held-out test payload는 전체 프로토콜 동결 전 접근하지 않는다. 원본 PE를 실행·가져오기·동적 로드·수정하지 않는다.
- 오류 표본을 제외하지 않고 모든 예외를 ledger에 유지한다. 매핑 정책 변경은 버전과 합성 회귀 fixture를 먼저 갖춘다.
- P2-MALFORMED-HEADER-V1: directory-count 초과와 선언 optional-header 결손/절단을 고정 reason으로 남기고 비어 있지 않은 파일 전체를 unknown으로 매핑한다. parser 비교 상태는 parse error로 남긴다.
- P2-SECTION-DISAGREEMENT-V1: section 수 차이는 `section_count_disagreement`, 정규화 raw 경계 차이는 `raw_section_boundary_disagreement`로 기록하고 전체 unknown으로 매핑한다. 기타 raw field 차이는 fallback 없이 disagreement; native overlay 차이는 진단값이다.
- P2 gate: fallback reason counts가 62/1/10과 일치하고 미분류 parse error·hash/size 오류·기타 disagreement 0건 및 새 reason 부재일 때만 통과. `p2_structure_gate_passed`만으로 동결을 승인하지 않는다.
- C6 결정: P2 구조 매핑 정책 `conservative_unknown_v1`(위 두 정책 버전)을 이번 census의 모집단·구현 해시 기준으로 동결한다. 전체 프로토콜 동결은 미승인(`protocol_freeze_authorized=false`). 근거 `paper/v5-kisa-xai/audit/P2_CENSUS_ADJUDICATION_2026-09-24.md`.
- C7 결정: 기존 파일럿·합성 CUDA 확인 기록에 따라 batch size 512와 Grad-CAM target layer `layer4.1`을 유지한다. C7은 재실행 없이 train/validation 범위에서만 판정했다. 근거 `paper/v5-kisa-xai/audit/C7_BATCH_TARGET_LAYER_2026-09-24.md`.
- 전체 프로토콜 동결(`protocol_freeze_authorized=true`)은 C8 완료 후 C9 전에 사용자가 승인하며, 그 전까지 test payload는 열지 않는다.
- 장시간 실행(census, 학습)은 사용자가 별도 `.venv` 창에서 한다. Codex는 명령만 기록하고 직접 실행하지 않으며, 결과 판정은 다음 청크에서 한다.
- C8 사전 등록: ImageNet 초기화, seed 42·43·44, batch 512, train/validation만 사용. 세 seed 모두 validation macro-F1 > majority macro-F1+0.10, balanced accuracy ≥0.70, 양 class recall ≥0.60, seed 방향 일치일 때 sanity gate 통과. 하나라도 실패하면 XAI 중단.
- 기존 run의 C8 gate 시점: 기준은 검증기 출력 열람 전에 기록했으나 해당 학습 완료 후 정했다(사용자 진술). 기존 run에 대해 학습 전 사전 등록으로 표현하지 않는다. Validation은 초기화·checkpoint 선택에 사용됐으므로 성능 보고는 전체 동결 후 held-out test 1회 평가로 한다.
- C8b-c 결정: epoch 상한 30·patience 5는 run 당시 인자 기록이 없어 종료 양상과 run 이후 코드 기본값 경유의 **간접 확증**으로 판정하고 C8b를 종결한다. 전체 프로토콜 동결 승인은 하지 않는다.
- C8p 결정: YAML에 동일 sample·달성 budget·fill random state 쌍체 규칙과 effect·95% CI·Holm 조정 p·eligible n 보고 필드를 명시했다. P2 교차검사·fallback blocker는 `audit/P2_CENSUS_ADJUDICATION_2026-09-24.md` 근거로 해소했다. 전체 프로토콜 동결은 미승인.

가정:
- C7~C10은 동결된 P2 매핑 정책 위에서 진행한다. 매핑 정책을 바꾸면 새 버전·fixture·census가 필요하다.
- 저장소 증거와 합성 fixture로 판정하며 외부 조사 없이 진행한다.

후속 청크에 필요한 요약·수치:
- 기대 파일 201,549개 모두 길이·SHA-256 검증 통과. P2 train/validation 169,020개(train 139,087, validation 29,933).
- P2 census 2026-09-24(policy v1): agreement 168,947; accepted_unknown_fallback 73 = directory-count 62 / optional-header 1 / section_count_disagreement 10; raw_section_boundary_disagreement 0; mismatch_fields section_count 10, raw_section_overlay_boundary 5; error·disagreement 0; gate passed; `protocol_freeze_authorized=false`.
- 출력: `D:\secure-malware-data\psa\audit\p2_census_20260924_policy_v1\` (summary SHA-256 b43de950…, ledger 217,302,754바이트 SHA-256 de937d73…). 저장소 복사본 `paper/v5-kisa-xai/audit/p2_census_20260924_policy_v1/{summary.json,audit_plan.json}`.
- 코드: 커밋 ff57e250d0d58b0ae3e2bfa1b638b521c7573885; `structure.py` 6d79fa79…, `psa_structure_audit.py` fdc5ce7d…; manifest 3dc0bd7f…. 전체 해시와 실행 명령은 판정 문서에 있다. 환경: `.venv` Python 3.12.10, pefile 2024.8.26.
- 문서: 판정 `audit/P2_CENSUS_ADJUDICATION_2026-09-24.md`; 정책 `protocol/P2_MALFORMED_HEADER_POLICY_V1.md`, `protocol/P2_SECTION_DISAGREEMENT_POLICY_V1.md`; 이전 근거 `audit/P2_POSTRESTORE_2026-09-23.md`.
- 테스트: 구조·audit 합성 테스트 23 passed(C4). pefile이 필요한 4건은 `.venv`에서만 실행 가능.
- C7 근거: pilot peak 6,070.7/8,123.4 MiB(74.73%), 학습 최대 6,072.7 MiB(74.76%); `layer4.1` BasicBlock, 합성 CUDA activation/gradient `[1,512,7,7]`. 기존 아티팩트 존재와 SHA-256 확인, 재실행 없음.
- C8a 대조: `runs/psa-orchestration/freeze_prereqs_20260921.json`의 batch 512, VRAM 8,123.4/6,070.7/6,072.7 MiB, 74.73%/74.76%, `layer4.1` BasicBlock, activation·gradient `[1,512,7,7]`, 출력 `[1,2]`, 악성 logit 1이 C7 판정 문서와 일치. JSON의 옛 `remaining_blocker`는 당시 이력.
- 기존 ImageNet seed 42·43·44 학습 결과는 `D:\secure-malware-data\psa\runs`에 있으며, 51개 복원은 래스터와 일치해 재학습이 필요하지 않음(`P2_POSTRESTORE_2026-09-23.md`). C8b는 우선 기존 결과 검증.
- C8b 사용자 PowerShell(.venv) 확인 명령: `cd C:\research\ua-sahi-mal`; `$c8Runs = 'D:\secure-malware-data\psa\runs'`; `.\.venv\Scripts\python.exe scripts\psa_verify_training.py --rasters-dir D:\secure-malware-data\psa\rasters --runs-dir $c8Runs --out runs\psa-orchestration\c8_training_verify_20260924.json`; `Get-Content -Encoding utf8 runs\psa-orchestration\c8_training_verify_20260924.json`에서 `all_seeds_passed`, `direction_agreement`, 각 seed의 `sanity_gate_passed` 확인. 검증기는 체크포인트 SHA-256·counts도 대조하고 test payload는 읽지 않음.
- 사용자 보고(2026-09-24): 현재 HEAD `62a15542f14b94b16271dbac8defbe99ee57b3ca` 코드로 seed 42·43·44를 `D:\secure-malware-data\psa\runs\c8_retrain_20260924`에 재학습 중. 완료 후 이 폴더를 `--runs-dir`로 재검증한다. 위 C8 sanity gate는 이번 재학습에 적용할 사전 등록 기준이며, 이전 run에 소급하지 않는다. 실행·완료 상태는 Codex가 직접 확인하지 않았다.
- C8b-a 판정: 검증 JSON은 `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`; seed 42/43/44 validation macro-F1 0.953395/0.946615/0.952926, balanced accuracy 0.952678/0.945863/0.953281, 양 class recall 모두 ≥0.932271. 보고서 `audit/C8B_TRAINING_VERIFY_2026-09-24.md`.
- C8b-b: D: run summary 3개에서 seed 42/43/44, init imagenet, batch 512 직접 확인. history epoch은 0 기준, 마지막 번호 18/10/16. `epochs_ran-best.epoch`은 모두 6이나 최적 뒤 실행은 `(epochs_ran-1)-best.epoch=5`; 각 후속 5 epoch에 macro-F1 최고값 갱신 없음. patience 5 동작과 부합. 판정 문서의 C8b-a 산술 오류 정정.
- 세 summary에 `epochs_max`, `early_stopping_patience` 설정 필드가 없어 값 자체는 미확증. C8b-c에서 실행 설정 근거 확인 필요. 판정 `audit/C8B_TRAINING_VERIFY_2026-09-24.md`.
- C8b-c: 현재 `scripts/psa_train.py` 기본값은 epochs_max 30·patience 5. run 직전 커밋 2075df27(2026-09-15 22:12:34 +09:00)에 이 파일이 없고 run 이후 커밋 661db79f(2026-09-21 07:47:04 +09:00)에서 기본값 30/5로 처음 추가되어 전후 동일성 비교 불가. 세 run 폴더는 각각 best.pt·summary.json만 있고 args·config·log 파일 없음. 종료 양상과 사후 코드 기본값을 통한 간접 확증으로 C8b 종결. 상세 `audit/C8B_TRAINING_VERIFY_2026-09-24.md`.
- C9 YAML 계획 확인: Grad-CAM·`layer4.1`, 4개 budget, uniform/front/entropy/structure-matched 대조군, deletion ΔNLL·keep-only와 3종 fill, 동일 sample·달성 budget·fill random state, 쌍체 bootstrap 2,000·Holm 2검정·effect·95% CI·조정 p·eligible n 명시.

미해결·주의:
- 전체 프로토콜 동결 미승인. C8 완료 후 C9 전 사용자 승인.
- C8b는 간접 확증으로 종결. epoch 상한·patience의 run 당시 직접 증거는 없으며 이를 직접 확증으로 인용하지 않는다.
- C8r에서 사용자 재학습 완료 여부와 검증 JSON을 확인한다. 완료·gate 통과 전 C9로 넘어가지 않는다.
- Codex 세션에서는 `.venv` 런처가 base Python 경로 문제로 실행되지 않는다(사용자 창에서는 정상). 실행이 필요한 검증은 사용자가 `.venv` 창에서 한다.
- pytest는 `.pytest_tmp` 접근 거부로 별도 `--basetemp`를 쓴다.
- 기존 사용자 수정(`TRAINING_HANDOFF_KO.md`, `PSA_XAI_V1_0_DRAFT.yaml`)과 미추적 patch·bundle을 보존한다.
- PROGRESS.md 한글이 C6 세션에서 `?`로 손상되어 2026-09-24 복원했다. 이 파일을 고친 뒤에는 한글이 정상인지 확인한다.
