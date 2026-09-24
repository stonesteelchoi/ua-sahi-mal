목표: PSA-XAI P2 파서 정책을 비조작 원칙으로 확정·검증하고 동결 후 학습·XAI 실험을 재현 가능하게 수행한다.
완료: C0~C8r(세부 아래), C9p, C9a, C9b-b, C8f(전체 프로토콜 동결); C9 도구·명령 준비; C9c-a(test census 증거 복사); C9c-b1(main fallback 판정); C9c-b2(era·freeze 판정); C9x-1(Grad-CAM); C9x-2(대조군·perturb)
다음: C9x-3 — 통계·실행 비용 검토 / 쌍체 효과·CI·명령 검증
남은 청크: C9x-3 통계·비용 검토; C9v 합성 회귀; C10 평가·문서
확정 규칙·결정(형식·기준 포함):
- 세션당 청크 1개만 수행한다. C9b-a는 사용자 지정으로 수정·생성 파일 8개까지 허용했다.
- held-out test payload는 전체 프로토콜 동결 전 접근하지 않는다. 원본 PE를 실행·가져오기·동적 로드·수정하지 않는다.
- 오류 표본을 제외하지 않고 모든 예외를 ledger에 유지한다. 매핑 정책 변경은 버전과 합성 회귀 fixture를 먼저 갖춘다.
- P2-MALFORMED-HEADER-V1: directory-count 초과와 선언 optional-header 결손/절단을 고정 reason으로 남기고 비어 있지 않은 파일 전체를 unknown으로 매핑한다. parser 비교 상태는 parse error로 남긴다.
- P2-SECTION-DISAGREEMENT-V1: section 수 차이는 `section_count_disagreement`, 정규화 raw 경계 차이는 `raw_section_boundary_disagreement`로 기록하고 전체 unknown으로 매핑한다. 기타 raw field 차이는 fallback 없이 disagreement; native overlay 차이는 진단값이다.
- P2 gate: fallback reason counts가 62/1/10과 일치하고 미분류 parse error·hash/size 오류·기타 disagreement 0건 및 새 reason 부재일 때만 통과. `p2_structure_gate_passed`만으로 동결을 승인하지 않는다.
- C6 결정: P2 구조 매핑 정책 `conservative_unknown_v1`(위 두 정책 버전)을 이번 census의 모집단·구현 해시 기준으로 동결한다. 전체 프로토콜 동결은 미승인(`protocol_freeze_authorized=false`). 근거 `paper/v5-kisa-xai/audit/P2_CENSUS_ADJUDICATION_2026-09-24.md`.
- C7 결정: 기존 파일럿·합성 CUDA 확인 기록에 따라 batch size 512와 Grad-CAM target layer `layer4.1`을 유지한다. C7은 재실행 없이 train/validation 범위에서만 판정했다. 근거 `paper/v5-kisa-xai/audit/C7_BATCH_TARGET_LAYER_2026-09-24.md`.
- 전체 프로토콜 동결은 사용자 승인일 2026-09-24에 완료했다(`protocol_freeze_authorized=true`). 고정 근거와 YAML SHA-256은 `audit/PROTOCOL_FREEZE_2026-09-24.md`; main test·era test 각 1회 접근 허용.
- 장시간 실행(census, 학습)은 사용자가 별도 `.venv` 창에서 한다. Codex는 명령만 기록하고 직접 실행하지 않으며, 결과 판정은 다음 청크에서 한다.
- C8 사전 등록: ImageNet 초기화, seed 42·43·44, batch 512, train/validation만 사용. 세 seed 모두 validation macro-F1 > majority macro-F1+0.10, balanced accuracy ≥0.70, 양 class recall ≥0.60, seed 방향 일치일 때 sanity gate 통과. 하나라도 실패하면 XAI 중단.
- C8 gate 기준은 09-15 초안 커밋 c1262f09에 등록, 최종 main 모델은 09-24 provenance 커밋 62a15542f14b94b16271dbac8defbe99ee57b3ca 재학습. 기존 run에 소급하지 않는다. Validation은 초기화·checkpoint 선택에 사용; 성능 보고는 동결 후 held-out test 1회.
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
- C8b-a 판정: 검증 JSON은 `all_seeds_passed=true`, `direction_agreement=true`, `test_evaluation_performed=false`; seed 42/43/44 validation macro-F1 0.953395/0.946615/0.952926, balanced accuracy 0.952678/0.945863/0.953281, 양 class recall 모두 ≥0.932271. 보고서 `audit/C8B_TRAINING_VERIFY_2026-09-24.md`.
- C8b-b: D: run summary 3개에서 seed 42/43/44, init imagenet, batch 512 직접 확인. history epoch은 0 기준, 마지막 번호 18/10/16. `epochs_ran-best.epoch`은 모두 6이나 최적 뒤 실행은 `(epochs_ran-1)-best.epoch=5`; 각 후속 5 epoch에 macro-F1 최고값 갱신 없음. patience 5 동작과 부합. 판정 문서의 C8b-a 산술 오류 정정.
- C8b-c: 현재 `scripts/psa_train.py` 기본값은 epochs_max 30·patience 5. run 직전 커밋 2075df27(2026-09-15 22:12:34 +09:00)에 이 파일이 없고 run 이후 커밋 661db79f(2026-09-21 07:47:04 +09:00)에서 기본값 30/5로 처음 추가되어 전후 동일성 비교 불가. 세 run 폴더는 각각 best.pt·summary.json만 있고 args·config·log 파일 없음. 종료 양상과 사후 코드 기본값을 통한 간접 확증으로 C8b 종결. 상세 `audit/C8B_TRAINING_VERIFY_2026-09-24.md`.
- C8r-b·c: 세 학습 로그에서 patience 5, 종료 epoch 18/10/16, seed별 checkpoint 경로·SHA-256을 직접 확인했다. 로그에는 전체 명령·epochs-max 30·초기화·batch 인자 자체가 출력되지 않아 그 항목의 로그 직접 확증은 없다. provenance 명령과 summary 검증 결과가 나머지 근거다.
- YAML 17,431은 중복 제외 전 test 악성 수: split manifest·raster index 모두 17,431, 중복 raster 제외 24건 후 검증기 17,407. 정상 test도 12,740에서 중복 1건 제외 후 12,739. YAML 미수정. 기존·재학습 best.pt 가중치 텐서 동일성용 사용자 Python 한 줄 명령은 C8r 판정 문서에 기록했으며 결과는 미확인.
- C9p: YAML에 원 분할 counts 유지, 중복 제외 139087/29933/30146 병기, test 악성 17407·제외 24건 주석, ImageNet 고정, 재학습 validation AUROC 0.9868352431/0.9873733953/0.9871156021 대 metadata 0.95(서로 다른 평가 분할) 기록.
- C9a: `statistics.unit=imphash_group`(그룹 내 파일별 쌍체 차이 평균 후 그룹 재표집), `sensitivity_analysis=file`, `fills.robustness=local_median` 고정. era 70938(49622/10662/10654), 32153그룹, SHA fd0a9900…d91a; 작은 악성 PE32+ 층 편차와 main 학습/검증 교차 5774/3212, 전체 era test 미관측 평가 불가 기록. 지정 파일 5개 SHA-256 직접 재계산 모두 기준과 일치해 `all_hashes_above_unchanged` 근거 충족. 상세 `audit/C9_FREEZE_PREP_2026-09-24.md`.
- C9a: freeze verifier 기대 해시를 C8 재학습 3개로 변경하고 `remaining_blocker`를 P2 판정 근거로 교체. 사용자 재실행 명령은 C9 판정 문서에 기록, Codex 세션 실행은 하지 않았다. C8r 가중치 비트 단위 재현 seed 42/43/44 `identical=True`는 사용자 보고로 C8r 판정 문서에 추기했다.
- C9b-a 사용자 결정: era 전용 ResNet-18/ImageNet/512/30/5/seed 42·43·44, validation macro-F1 선택, main과 동일 sanity gate. era train/val만 학습·선택; 전체 동결 후 era test 1회. H1·H2는 robustness 재현으로 방향·CI를 보고하며 주 가설 family 2개에는 추가하지 않는다. era test는 era 모델에만 unseen; 중복 제외 유효 건수는 학습 로그에서 확정. local_median은 5×5.
- C9b-a P2 두 정책은 main test·era test 구조 매핑에도 같은 reason/fallback 적용. 미분류 parse error·비대상 disagreement는 표본 유지, 구조 귀속 불가 표시, 건수 보고. 동결 후 정책 변경 없음; train/val 62/1/10 gate는 test에 적용하지 않고 기술 통계만 보고.
- C9b-a CLI: `psa_train.py train/eval`과 `psa_verify_training.py`에 선택적 `--split-manifest`; 생략하면 기존 raster_index.csv split 사용. `tests/test_psa_split_manifest.py` 사용자 `.venv` 창 합성 회귀 1 passed 확인.
- era 명령 준비: `$eraManifest='D:\secure-malware-data\psa\audit\era_stratified_freeze_20260924\split_manifest_era.csv'; $eraRuns='D:\secure-malware-data\psa\runs\era_20260924'; if ((Get-FileHash -LiteralPath $eraManifest -Algorithm SHA256).Hash.ToLower() -ne 'fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a') { throw 'era manifest hash mismatch' }; New-Item -ItemType Directory -Path $eraRuns -Force | Out-Null`.
- provenance 명령: `$prov=@('main_retrain_commit=62a15542f14b94b16271dbac8defbe99ee57b3ca', ('era_code_head='+ (git rev-parse HEAD)), ('train_script_sha256='+ (Get-FileHash scripts/psa_train.py -Algorithm SHA256).Hash), ('verify_script_sha256='+ (Get-FileHash scripts/psa_verify_training.py -Algorithm SHA256).Hash), 'era_manifest_sha256=fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a', 'architecture=resnet18; init=imagenet; batch=512; epochs_max=30; patience=5; seeds=42,43,44; selection=validation_macro_f1; workers=4') -join "`n"; .\.venv\Scripts\python.exe -c "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text(sys.argv[2]+chr(10),encoding='utf-8')" (Join-Path $eraRuns 'run_provenance.txt') $prov`.
- era 학습 명령(사용자 `.venv` 창, 위 두 줄 실행 후): `foreach ($seed in 42,43,44) { & .\.venv\Scripts\python.exe -u scripts\psa_train.py train --rasters-dir D:\secure-malware-data\psa\rasters --split-manifest $eraManifest --out-dir $eraRuns --batch-size 512 --init imagenet --seed $seed --epochs-max 30 --patience 5 --workers 4 2>&1 | Tee-Object -FilePath (Join-Path $eraRuns "seed${seed}_train.log"); if ($LASTEXITCODE -ne 0) { throw "seed $seed failed" } }`. 각 seed best.pt·summary.json과 로그 생성, 로그의 `splits`로 중복 제외 건수 확정.
- C9b-b era 판정: 유효 train/val/test 49593/10660/10652, 중복 제외 33; 세 seed sanity gate·방향 일치, test 미평가. 체크포인트 SHA-256 세 값과 train/verify 스크립트 해시 직접 일치, provenance HEAD 8323ab75. 세 best.pt를 동결 후 era test 모델로 지정. Era metadata AUROC 0.90–0.91, JSON의 0.95는 main용. Main 대비 validation AUROC 차이는 서로 다른 분할의 기술 통계. 상세 `audit/ERA_TRAINING_2026-09-24.md`; JSON 복사본 `runs/psa-orchestration/era_training_verify_20260924.json`.
- C9c-a: main/era test census는 30146/10652건, agreement 30104/10651, fallback 42(40 directory-count+2 section_count)/1(directory-count), unattributable 0. 두 summary·audit_plan을 `audit/{main,era}_test_structure_census_20260924/`에 각각 복사하고 원본과 SHA-256 일치 확인. D: ledger SHA-256 main 53bc25ecf7b144cb5d1599fba9052b0eb9d52ef973947672fdbc720ecbd85c7b, era bf538e933bfd87a19a0e5ed47bdf2a40344e3bbd602215b61586d00072473b16. 모델 평가·gate 판정 없음. C9c-b1: main fallback 42건 전부 악성, imphash 10그룹, fallback 최대 16건, 40/2 reason; 구조 비교 H1·H2 예상 eligible_n 17365(17407-42), 표본은 유지. C9c-b2: era fallback sample 64884 1건 악성·1 imphash 그룹, 예상 eligible_n 5331(5332-1). 두 audit_plan의 `test_payload_access=true`, 원본 생성 시각 era 19:01:05·main 19:02:47 KST는 근사 시작 시각이며 정확한 첫 읽기 시각은 없음. 상세 `audit/C9_TEST_STRUCTURE_ADJUDICATION_2026-09-24.md`, `audit/PROTOCOL_FREEZE_2026-09-24.md`.
- C9x-1/2: Grad-CAM은 `psa_train.build_model("random", device)`+checkpoint 및 공용 `preprocess_raster`를 사용한다. `psa_perturb.py`는 달성 고유 byte budget 대조군 4종, fill 3종, deletion ΔNLL·keep-only 악성 logit, 구조 fallback eligible=false, 원본 SHA·래스터 재구성 검증 및 JSONL 기록을 구현. 합성 PE pytest 4 passed, torch 필요 2 skipped; py_compile 통과. 명령은 `audit/C9X{1,2}_*COMMANDS_2026-09-24.md`에 기록, 실제 test 미실행. Forward: agreement 2,016/file, fallback 1,056/file; main 35,052,192/seed, era 10,748,352/seed, 3 seed 총 137,401,632. 10/50 ms/pass 가정시 forward만 15.9/79.5일, 실측 아님.

미해결·주의:
- V1.1 동결 완료; 정책·가설·통계 단위 변경 금지, 추가 분석은 V1.2 exploratory로만. 태그 `psa-xai-v1.1-frozen`은 동결 파일 커밋 뒤 사용자가 실행.
- C9b-a 합성 CLI 회귀 1 passed 사용자 확인. C9 새 구조 audit 합성 회귀는 이 세션 `.venv` base Python 접근 오류로 미실행; C9v에서 사용자 창 결과 확인. Era 학습·검증 판정 완료. local_median은 후속 XAI 단계에서 YAML의 5×5를 따른다.
- C8r 가중치 동일성은 사용자 보고로 기록했고 독립 재실행은 하지 않았다. 동결 승인 후 C9부터 test 접근 가능하며 1회 평가 규칙을 지킨다.
- Codex 세션에서는 `.venv` 런처가 base Python 경로 문제로 실행되지 않는다(사용자 창에서는 정상). C9x-1 hook 및 C9x-2 공용 전처리 합성 테스트 2건은 사용자 `.venv` 창 확인 필요; 실제 test XAI 미실행. C9x-2 entropy 256바이트 창·median 원본 바이트 격자 좌표는 YAML 미상세에 대한 구현 가정; 상세 명령 문서 참고.
- pytest는 `.pytest_tmp` 접근 거부로 별도 `--basetemp`를 쓴다.
- 기존 사용자 수정(`TRAINING_HANDOFF_KO.md`, `PSA_XAI_V1_0_DRAFT.yaml`)과 미추적 patch·bundle을 보존한다.
- PROGRESS.md 한글이 C6 세션에서 `?`로 손상되어 2026-09-24 복원했다. 이 파일을 고친 뒤에는 한글이 정상인지 확인한다.
