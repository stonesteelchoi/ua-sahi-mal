목표: PSA-XAI P2 파서 정책을 비조작 원칙으로 확정·검증하고 동결 후 학습·XAI 실험을 재현 가능하게 수행한다.
완료: C0, C1, C2a, C2b, C3, C4, C5(사용자 실행 완료), C6, C6 보완, C7, C8a(준비), C8b-a, C8b-b, C8b-c(C8b 종결), C8p(YAML 보완), C8r-a, C8r-b, C8r-c(C8r 종결), C9p(동결 준비), C9a(정책·era·해시 판정)
다음: C9b — 미해결 창 크기·era 분석 범위 결정 및 사용자 검증 출력 판정 / 동결 전 조건 확정
남은 청크: C9b 창·era 범위·검증 판정; C9 동결 승인 후 XAI; C10 통계·결과 문서

확정 규칙·결정(형식·기준 포함):
- 세션당 청크 1개만 수행하며 완료 전 다음 청크로 이동하지 않는다. 기본 청크당 새 파일 3개, 웹 검색 2회, 수정·생성 파일 5개 이하. C9p는 사용자 지정 동결 준비 청크로 새 파일 8개까지 허용했다.
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
- C8 gate 기준은 09-15 초안 커밋 c1262f09에 등록, 최종 모델은 09-24 재학습. 기존 run의 학습 전 등록 여부는 확정하지 않고 기존 run을 학습 전 C8 사전 등록으로 표현하지 않는다. Validation은 초기화·checkpoint 선택에 사용됐으므로 성능 보고는 전체 동결 후 held-out test 1회 평가로 한다.
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
- C8r-a: 기존·재학습 검증 JSON의 공통 validation 지표·gate·방향은 seed 42/43/44에서 정확히 일치한다. 새 JSON의 AUROC·시간·경로·해시는 달라 JSON 전체 동일은 아니다. 재학습 provenance에 커밋 `62a15542f14b94b16271dbac8defbe99ee57b3ca`와 batch 512·ImageNet·epochs 30·patience 5·3 seed 명령이 직접 기록돼 있다. C8 gate는 이 재학습 전 등록 기준이고 검증 결과상 통과했다. C9 후보는 `D:\secure-malware-data\psa\runs\c8_retrain_20260924\seed{42,43,44}_imagenet_bs512\best.pt`이며 SHA-256은 `291af0bd…`, `4156f2b8…`, `62c0d8b0…`; 이전 runs 체크포인트를 대체한다. 근거 `audit/C8R_RETRAIN_ADJUDICATION_2026-09-24.md`.
- C8r-b·c: 세 학습 로그에서 patience 5, 종료 epoch 18/10/16, seed별 checkpoint 경로·SHA-256을 직접 확인했다. 로그에는 전체 명령·epochs-max 30·초기화·batch 인자 자체가 출력되지 않아 그 항목의 로그 직접 확증은 없다. provenance 명령과 summary 검증 결과가 나머지 근거다.
- YAML 17,431은 중복 제외 전 test 악성 수: split manifest·raster index 모두 17,431, 중복 raster 제외 24건 후 검증기 17,407. 정상 test도 12,740에서 중복 1건 제외 후 12,739. YAML 미수정. 기존·재학습 best.pt 가중치 텐서 동일성용 사용자 Python 한 줄 명령은 C8r 판정 문서에 기록했으며 결과는 미확인.
- C8r 최종 판정: 재학습 validation sanity gate 통과, C8r 종결. C9 후보 모델은 C8r-a 지정 재학습 best.pt 3개. 근거 `audit/C8R_RETRAIN_ADJUDICATION_2026-09-24.md`.
- C9p: YAML에 원 분할 counts 유지, 중복 제외 139087/29933/30146 병기, test 악성 17407·제외 24건 주석, ImageNet 고정, 재학습 validation AUROC 0.9868352431/0.9873733953/0.9871156021 대 metadata 0.95(서로 다른 평가 분할) 기록.
- C9a: `statistics.unit=imphash_group`(그룹 내 파일별 쌍체 차이 평균 후 그룹 재표집), `sensitivity_analysis=file`, `fills.robustness=local_median` 고정. era 70938(49622/10662/10654), 32153그룹, SHA fd0a9900…d91a; 작은 악성 PE32+ 층 편차와 main 학습/검증 교차 5774/3212, 전체 era test 미관측 평가 불가 기록. 지정 파일 5개 SHA-256 직접 재계산 모두 기준과 일치해 `all_hashes_above_unchanged` 근거 충족. 상세 `audit/C9_FREEZE_PREP_2026-09-24.md`.
- C9a: freeze verifier 기대 해시를 C8 재학습 3개로 변경하고 `remaining_blocker`를 P2 판정 근거로 교체. 사용자 재실행 명령은 C9 판정 문서에 기록, Codex 세션 실행은 하지 않았다. C8r 가중치 비트 단위 재현 seed 42/43/44 `identical=True`는 사용자 보고로 C8r 판정 문서에 추기했다.

미해결·주의:
- 전체 프로토콜 동결 미승인. C8 완료 후 C9 전 사용자 승인.
- `local_median` 창 크기는 구현에 없어 미해결; 제안 5×5. YAML·handoff에는 era CNN/XAI 분석 계획이 미고정; 선택지: era 전용 3 seed 학습 / main∩era test 1668건 평가 / V1.2 exploratory 지정.
- C8b는 간접 확증으로 종결. epoch 상한·patience의 run 당시 직접 증거는 없으며 이를 직접 확증으로 인용하지 않는다.
- C8r 가중치 동일성은 사용자 보고로 기록했고 독립 재실행은 하지 않았다. C9·test payload 접근은 전체 프로토콜 동결 승인 전 금지.
- Codex 세션에서는 `.venv` 런처가 base Python 경로 문제로 실행되지 않는다(사용자 창에서는 정상). 실행이 필요한 검증은 사용자가 `.venv` 창에서 한다.
- pytest는 `.pytest_tmp` 접근 거부로 별도 `--basetemp`를 쓴다.
- 기존 사용자 수정(`TRAINING_HANDOFF_KO.md`, `PSA_XAI_V1_0_DRAFT.yaml`)과 미추적 patch·bundle을 보존한다.
- PROGRESS.md 한글이 C6 세션에서 `?`로 손상되어 2026-09-24 복원했다. 이 파일을 고친 뒤에는 한글이 정상인지 확인한다.
