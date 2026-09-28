# C10 PSA-XAI V1.1 held-out 판정 — 2026-09-29

## 판정 기준과 결론

동결 protocol `PSA_XAI_V1_1_FROZEN.yaml`의 주 검정은 main 악성 test, top 10% budget, structure-conditioned resampling fill, 구조 매칭 무작위 20회 대조군이다. 동일 파일의 repeat별 쌍체 차이를 imphash 그룹 안에서 평균한 뒤 2,000회 그룹 bootstrap으로 seed 평균 효과와 95% CI, 단측 우월성 p를 구하고 두 가설에 Holm 보정을 적용했다. 유의수준은 0.05이다. 양수가 우월성 방향이다. Era는 독립 재현·robustness 범위로 주 family에 넣지 않는다.

**한 가설만 기각:** H2는 main seed 평균 효과 +0.330590, 95% CI [0.313117, 0.348328], 단측 p 0.000500, Holm p 0.001000으로 지지된다. H1은 -0.024572, CI [-0.033632, -0.016005], 단측 p와 Holm p 모두 1.000000으로 지지되지 않으며 추정 방향이 음수다. 이는 H1의 영가설이 참이라는 입증이 아니다. 세 main seed의 H2는 모두 양수, H1은 모두 음수다. Test 성능은 validation 기반 checkpoint 선택과 구분한다.

## 1. Held-out test 성능

혼동행렬은 `[[TN,FP],[FN,TP]]`이다. 여섯 JSON 모두 `split=test`; split counts와 혼동행렬의 행 합계가 일치한다. SHA-256은 평가 JSON 파일 자체의 해시다.

| 모집단 | Seed | 유효 N (정상/악성) | AUROC | Macro-F1 | Balanced accuracy | 정상 recall | 악성 recall | 혼동행렬 | 평가 JSON SHA-256 |
|---|---:|---|---:|---:|---:|---:|---:|---|---|
| main | 42 | 30,146 (12,739/17,407) | 0.986697 | 0.951536 | 0.951864 | 0.946699 | 0.957029 | [[12060,679],[748,16659]] | `63992bd8957ce1f3170b9aeefd370efaeae32ed6b35b22741603c2fcdcd3825a` |
| main | 43 | 30,146 (12,739/17,407) | 0.987379 | 0.944273 | 0.945196 | 0.943245 | 0.947148 | [[12016,723],[920,16487]] | `589fa354ddc7dfb75d3a21bc62f217f2dd2645bfe77d963b0f5a85aeba852640` |
| main | 44 | 30,146 (12,739/17,407) | 0.985079 | 0.949030 | 0.951016 | 0.957296 | 0.944735 | [[12195,544],[962,16445]] | `867a341744dc75ea3711fa2ac459a8ade323386df18ce3fa220e8a0d368c040f` |
| era | 42 | 10,652 (5,320/5,332) | 0.977684 | 0.941887 | 0.941884 | 0.937782 | 0.945986 | [[4989,331],[288,5044]] | `190d5c03b90f4b4220b02fc79067d14013c8f01e63f4fd2465628e9f031acc28` |
| era | 43 | 10,652 (5,320/5,332) | 0.964631 | 0.923484 | 0.923481 | 0.916917 | 0.930045 | [[4878,442],[373,4959]] | `7d1671173f147e3f995c9c358d88d296aa439721fcf1c8c8c0b7958472289170` |
| era | 44 | 10,652 (5,320/5,332) | 0.973484 | 0.923408 | 0.923453 | 0.892105 | 0.954801 | [[4746,574],[241,5091]] | `193f49577f6ab2df35c88e28559a6a4f6b32b7e60bd2a13e3d2fa1052d5539ed` |

## 2. Main 주 검정과 seed 방향

| 범위 | 가설 | 효과 | 95% CI | 단측 p | Holm p | 적격 파일 N | 그룹 N |
|---|---|---:|---|---:|---:|---:|---:|
| seed 평균 | H1 | -0.024572 | [-0.033632, -0.016005] | 1.000000 | 1.000000 | 17,346 | 5,864 |
| seed 평균 | H2 | +0.330590 | [0.313117, 0.348328] | 0.000500 | 0.001000 | 17,346 | 5,864 |
| seed 42 | H1 | -0.005851 | [-0.019085, 0.007430] | 0.807596 | 0.807596 | 17,353 | 5,867 |
| seed 42 | H2 | +0.413501 | [0.390542, 0.434730] | 0.000500 | 0.001000 | 17,353 | 5,867 |
| seed 43 | H1 | -0.035678 | [-0.044688, -0.026732] | 1.000000 | 1.000000 | 17,363 | 5,874 |
| seed 43 | H2 | +0.298988 | [0.270763, 0.326272] | 0.000500 | 0.001000 | 17,363 | 5,874 |
| seed 44 | H1 | -0.030789 | [-0.045538, -0.017265] | 1.000000 | 1.000000 | 17,353 | 5,869 |
| seed 44 | H2 | +0.279813 | [0.260243, 0.298238] | 0.000500 | 0.001000 | 17,353 | 5,869 |

## 3. Era 재현

| 범위 | 가설 | 효과 | 95% CI | 단측 p | Holm p | 적격 파일 N | 그룹 N |
|---|---|---:|---|---:|---:|---:|---:|
| seed 평균 | H1 | -0.024661 | [-0.040229, -0.009628] | 0.999500 | 0.999500 | 5,302 | 1,412 |
| seed 평균 | H2 | +0.264930 | [0.239557, 0.290463] | 0.000500 | 0.001000 | 5,302 | 1,412 |
| seed 42 | H1 | -0.022283 | [-0.050032, 0.006466] | 0.939030 | 0.939030 | 5,311 | 1,419 |
| seed 42 | H2 | +0.452407 | [0.410184, 0.495437] | 0.000500 | 0.001000 | 5,311 | 1,419 |
| seed 43 | H1 | -0.023051 | [-0.041529, -0.005894] | 0.996002 | 0.996002 | 5,323 | 1,424 |
| seed 43 | H2 | +0.072981 | [0.047039, 0.100195] | 0.000500 | 0.001000 | 5,323 | 1,424 |
| seed 44 | H1 | -0.035531 | [-0.054640, -0.016434] | 1.000000 | 1.000000 | 5,329 | 1,428 |
| seed 44 | H2 | +0.263019 | [0.227018, 0.298920] | 0.000500 | 0.001000 | 5,329 | 1,428 |

Era의 H1 음수·H2 양수 방향은 main과 일치한다. Era seed 43 H2는 **그룹 단위 +0.072981 [0.047039, 0.100195]**이지만 **파일 단위 -0.017582 [-0.029193, -0.005417]**, 단측 p 0.999000으로 방향이 뒤집힌다. 그룹 가중과 파일 가중의 차이를 숨기지 않고 robustness 제한으로 기록한다. Era 결과는 main 판정을 소급 변경하지 않는다.

## 4. Sensitivity·하위집단

다음 p는 단측 미보정 p이며 주 검정의 Holm p를 대신하지 않는다. 파일 단위는 동일 적격 파일에서 재표집 단위를 바꾼 sensitivity다.

| 모집단·범위 | 가설 | 효과 | 95% CI | p | 적격 파일 N |
|---|---|---:|---|---:|---:|
| main seed 평균 파일 단위 | H1 | -0.027321 | [-0.032259, -0.022442] | 1.000000 | 17,346 |
| main seed 평균 파일 단위 | H2 | +0.344847 | [0.335014, 0.354817] | 0.000500 | 17,346 |
| era seed 평균 파일 단위 | H1 | -0.015990 | [-0.021748, -0.010275] | 1.000000 | 5,302 |
| era seed 평균 파일 단위 | H2 | +0.168938 | [0.154931, 0.181646] | 0.000500 | 5,302 |
| main 정탐 악성 | H1 | -0.025493 | [-0.031829, -0.019384] | 1.000000 | 15,823 |
| main 정탐 악성 | H2 | +0.353816 | [0.334086, 0.372116] | 0.000500 | 15,823 |
| era 정탐 악성 | H1 | -0.023555 | [-0.035277, -0.012708] | 1.000000 | 4,833 |
| era 정탐 악성 | H2 | +0.300009 | [0.271105, 0.328837] | 0.000500 | 4,833 |
| main mean-pool | H1 | -0.025310 | [-0.034338, -0.016322] | 1.000000 | 15,666 |
| main mean-pool | H2 | +0.334800 | [0.316252, 0.354150] | 0.000500 | 15,666 |
| era mean-pool | H1 | -0.025166 | [-0.041801, -0.008452] | 0.999500 | 5,031 |
| era mean-pool | H2 | +0.302081 | [0.273190, 0.331082] | 0.000500 | 5,031 |
| main nearest-repetition | H1 | -0.017263 | [-0.056691, 0.018949] | 0.805097 | 1,680 |
| main nearest-repetition | H2 | +0.222758 | [0.169118, 0.273905] | 0.000500 | 1,680 |
| era nearest-repetition | H1 | -0.042217 | [-0.099957, 0.008480] | 0.944028 | 271 |
| era nearest-repetition | H2 | -0.025210 | [-0.070952, 0.020203] | 0.842579 | 271 |

Seed별 파일 sensitivity 방향: main H1 -/-/-, H2 +/+/+; era H1 -/-/-, H2 +/**-**/+ (42/43/44 순). Main seed 42 H1 파일 CI는 0을 가로지른다. Era nearest-repetition H2 역시 음수이며 CI가 0을 가로지른다. 정탐 subset의 H1은 양쪽 모집단에서 음수, H2는 양수다. 이 분석들은 탐색·민감도 결과다.

## 5. 기술 통계와 공간 교란 관찰

`psa_xai_stats.json`의 `populations.{main,era}.seed_average.descriptive` 각각 96행이 **전 조합의 수치 별표**다. Budget 0.05/0.10/0.20/0.40, fill 3종, control 4종, H1/H2 전체 조합의 `paired_mean`, `control_mean`, `eligible_n`을 그대로 보존한다. 아래는 10% budget의 H1 비교 발췌이며 주 검정 밖 비교의 p는 산출하지 않았다.

| 모집단 | Budget | Fill | Control | H1 쌍체 평균 | 대조군 평균 | 차이 | 적격 파일 N |
|---|---:|---|---|---:|---:|---:|---:|
| main | 0.10 | structure-conditioned resampling | front_position | +0.051803 | -0.013449 | +0.065252 | 17,395 |
| main | 0.10 | zero | front_position | +0.057714 | +0.006792 | +0.050923 | 17,395 |
| main | 0.10 | local_median | front_position | +0.001370 | +0.052067 | -0.050697 | 17,395 |
| era | 0.10 | structure-conditioned resampling | front_position | +0.044886 | -0.044079 | +0.088965 | 5,331 |

논의용 **V1.2 exploratory 후보**: Grad-CAM의 연속된 공간 블록과 흩어진 대조군의 교란 위치·형태가 결과에 영향을 줄 가능성이 있다. Front-position 대조에서는 main의 zero fill H1 차이가 약 +0.05(+0.050923)이고 resampling fill에서는 +0.065252다. 이는 구조 매칭 무작위와 비교한 동결 H1 주 검정이 아니며, fill에 따라 방향도 바뀐다. 공간 배치의 인과 설명으로 단정하거나 V1.1 판정에 반영하지 않는다.

## 6. 구조 CAM mass와 적격성

`structure_cam_mass`의 값은 JSON 필드 `mean` 그대로이며 정규화된 비율이라고 해석하지 않는다. 각 영역의 N은 main 17,407, era 5,332다. `unknown`은 fallback을 포함할 수 있는 구조 귀속 불가 영역으로 별도 표시한다.

| 구조 영역 | main 평균 CAM mass | era 평균 CAM mass |
|---|---:|---:|
| DOS/PE headers | 458.921 | 128.163 |
| executable sections | 10,722.095 | 8,753.051 |
| non-executable sections | 3,252.901 | 7,137.214 |
| resource-like sections | 3,311.334 | 2,039.259 |
| overlay | 3,274.377 | 1,724.065 |
| certificate table | 71.666 | 220.120 |
| unknown | 778.890 | 276.209 |

| 모집단·범위 | CAM 표본 N | 빈 CAM 제외 N | 구조 비적격 N | 주 검정 적격 N | 그룹 N | census fallback N |
|---|---:|---:|---:|---:|---:|---:|
| main 42 | 17,407 | 12 | 42 | 17,353 | 5,867 | 42 |
| main 43 | 17,407 | 2 | 42 | 17,363 | 5,874 | 42 |
| main 44 | 17,407 | 12 | 42 | 17,353 | 5,869 | 42 |
| main seed 교집합 | 17,407 | seed별 12/2/12 | 42 | 17,346 | 5,864 | 42 |
| era 42 | 5,332 | 20 | 1 | 5,311 | 1,419 | 1 |
| era 43 | 5,332 | 8 | 1 | 5,323 | 1,424 | 1 |
| era 44 | 5,332 | 2 | 1 | 5,329 | 1,428 | 1 |
| era seed 교집합 | 5,332 | seed별 20/8/2 | 1 | 5,302 | 1,412 | 1 |

Seed 평균은 적격 파일 **교집합**으로 계산했다(main union 17,364→intersection 17,346; era union 5,331→intersection 5,302). Seed별 빈 CAM 집합이 달라 평균 행의 제외 N은 단순 합계가 아니다. 구조 비적격 fallback 42/1건은 ledger에 보존하고 주 구조 매칭 검정에서만 제외했다.

## 7. Ledger SHA-256 대조

통계 JSON `ledger_sha256`의 12개 값을 D: 원본의 `perturb_summary.json` 및 `gradcam_summary.json` 각 `ledger_sha256`과 직접 대조했다. 아래 여섯 쌍은 전부 일치한다. 이 확인은 원본 summary와의 대조이며 6 GB급 ledger를 다시 해시한 독립 검증은 아니다.

| 모집단 | Seed | Perturb ledger SHA-256 | Grad-CAM ledger SHA-256 | 원본 summary |
|---|---:|---|---|---|
| main | 42 | `b9e61de6b381427783c0e641d50fd847c5b24d25f5e9745392b38718dc69e6fa` | `0ad94ba6a89e9afa8cd769fc0af7396e83b5d529a5325c803bb354f95ab22da8` | 일치 |
| main | 43 | `92a3791e7733b8d9ad3fee107da57563c11b59b424df90224890524c437ab724` | `6f4c403c86a74e091622385736e2ffd99733f6e35709495f8cdcb17f2d55bff2` | 일치 |
| main | 44 | `b183c977c5f7adb2993f6be485b403fefa4e32cd0381ab38fcd21edf02aace49` | `a39649d5abe90ad37e05fde1b2b19ba29f2efb75d4f1de47ea75144430fa2f29` | 일치 |
| era | 42 | `76575637e8124add65a302650a4411e3cf69c87a3e00ae72b8ad20e638ae85ca` | `81fb930fd1bedf33e2ea69fc67c8a9bf998919ac063b136e035efd16027e7fb6` | 일치 |
| era | 43 | `36c22f71e73c1347bace7eeb4c618428894f83ab3b97cb2165ff97f4b2655430` | `b6eb36f826780a09995a0754a2e4fc3750cdcc20ef0649aa8fa692341cfa32f7` | 일치 |
| era | 44 | `7b96ca2dfd0e24fc7d1119341d4ee05e46d5f24061f2ab585630ffe3f86b2782` | `2a02b653bb8edaa932958a34f9fcdbf60c2834ab3aaca22f4e275a62c2078063` | 일치 |

## 8. 실행 provenance와 한계

- 동결 protocol: `paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml`; 현재 재계산 SHA-256과 통계·여섯 평가 JSON의 `protocol_sha256` 모두 `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709`으로 일치한다.
- 재현 명령: `audit/C10_COMMANDS.md`의 eval 여섯 건 및 stats 명령. 명령 문서는 준비 명령이며 실제 실행 로그는 아니다. 평가 JSON은 실행 명령·시작/종료 시각·호스트·GPU·Python/torch/numpy 버전·Git dirty 상태를 기록하지 않는다. 이 항목은 **확인 불가**다. 통계 JSON 생성 파일 시각은 로컬 2026-09-29 00:43:31 KST이며 완료 시각의 대용으로만 본다. 현 checkout HEAD는 `b99d5e6839d528df74a252d90f7baf5dbd5e66`; 실제 평가 실행 HEAD는 JSON에서 확인되지 않는다.
- 통계 스크립트의 사후 두 수정은 `fc03c5c`(2026-09-29 00:13:11 KST, 공유 fill random state에서 **repeat별 쌍체 차이**로 수정), `b99d5e6`(00:38:05, seed별 빈 CAM 차이 때문에 **seed 적격 파일 교집합** 사용)이다. 통계 JSON 생성 시각 00:43:31보다 앞선 커밋이며 결과를 보기 전 도구 결함 수정으로 기록한다. 커밋 시각과 출력 생성 시각은 그 순서를 뒷받침하나, 출력 이전의 비기록 임시 분석까지 배제하는 독립 증거는 없다. 동결 YAML·가설·통계 단위는 변경하지 않았다.
- Main split은 `D:\secure-malware-data\psa\rasters\raster_index.csv`의 test, era split은 `D:\secure-malware-data\psa\audit\era_stratified_freeze_20260924\split_manifest_era.csv` SHA-256 `fd0a99000b05785ecf3fc01108529b37e08bb31f162b6defc3f3621459d2d91a`. 여섯 평가 JSON의 `input_sha256` 공통값은 raster index `94d02b247fc761d64fdea5aeac9afe2da6dc56bdcc998cc84d4a5c7d3f76f785`, rasters `bfd5e69305e6bcc0e9d53c1ed7d1434b82327cd79773a82ddd2b0538477f112c`, duplicate groups `ce91dec954cbcdbe441b29759b52b163be1d5c3009418c1c6a7131574a91686d`; era JSON 세 건의 split manifest hash도 위 동결값과 일치한다.
- Checkpoint: D: `psa\runs\c8_retrain_20260924\seed{42,43,44}_imagenet_bs512\best.pt`의 SHA-256은 순서대로 `291af0bd0b2133f3c501fe3efdae0f5503b6de7d4e095a5fc2b1c27a7561f48f`, `4156f2b8bf8c7995c8d62e4132102b28430d9fc69de49b293ec561af68bcaf56`, `62c0d8b002586676d61c7488099e362b4c15777a9406424c324c1f4fbec5639c`; era `psa\runs\era_20260924\seed{42,43,44}_imagenet_bs512\best.pt`는 `a1121de1a69992c9032d2278f2a43b6560ada3e5d03716097c145bc5c23dc2b6`, `f031295be823c37158411180f63c64a4eee5189e6077cc744aa69d408b6ee7bf`, `da30a11b32904116a83f3b408e37e7508bb6d4969fee8336fa8392a1caa729f1`. 여섯 평가 JSON의 checkpoint SHA-256은 동결 문서 기대값과 일치하며 eval이 checkpoint를 재해시했다. 모두 ImageNet 초기화; best epoch은 main 13/5/11, era 7/3/6(JSON 순서). Main 모델 provenance commit `62a15542`, era `8323ab75`는 동결 문서에 기록돼 있다.
- 평가 JSON: `runs/psa-orchestration/test_eval_{main,era}_seed{42,43,44}.json`(각 파일 SHA-256은 표 1). 통계: `runs/psa-orchestration/xai_stats_20260930/psa_xai_stats.json` SHA-256 `299c98693c8b652af0293f68986e9f448ac452f428c74a75517e0e16163fb3b2`, 동봉 MD SHA-256 `63e8165a02c3a791fb170c9504253fbf5c52b3689b9a4e7345887e31a11788de`. 원본 ledger·summary는 D: `psa\runs\xai_v1_1\{main,era}_seed{42,43,44}_{perturb,gradcam}\`에 있으며 관련 명령은 `audit/C10_COMMANDS.md`, perturb 실행 이력은 `audit/C9X2_PERTURB_COMMANDS_2026-09-24.md`에 있다.
- 동결 후 main/era test 구조 census와 이 여섯 평가 JSON이 확인된다. 별도 재실행이 없었다는 사실은 실행 로그만으로 독립 입증할 수 없다. 평가 JSON 내부의 실패·부분 실행·예외 기록은 없으며 여섯 건의 split counts·혼동행렬·summary가 완결됐다. 구조 fallback은 제외가 아니라 ledger 보존과 구조 검정 비적격 처리다.
