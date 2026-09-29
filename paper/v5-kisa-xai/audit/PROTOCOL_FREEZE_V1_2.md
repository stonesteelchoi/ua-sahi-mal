# PSA-XAI V1.2 동결 준비 초안

상태: 사전 등록 addendum 작성 완료, 실제 동결·실행 전. V1.1 동결 YAML·가설·판정은 유지한다. V1.2는 탐색적 추가 검정이다.

## 실행 전 확인 및 동결 절차

1. `paper/v5-kisa-xai/protocol/PSA_XAI_V1_2_ADDENDUM.yaml`과 `audit/C11_ADJUDICATION_TEMPLATE.md`를 검토한다. V1.1 parent YAML SHA-256을 재계산해 addendum의 `parent_protocol_sha256`과 대조한다.
2. V1.2 addendum YAML SHA-256을 재계산해 아래에 기록한다. 이후 변경하면 해시를 다시 계산하고 새 버전 판정 여부를 검토한다.
3. addendum·판정 틀·동결 문서를 먼저 커밋하고 태그한다. 구현(C11-b)·통계(C11-c)는 태그 뒤 별도 커밋으로 남기며, 태그 이후 YAML은 수정하지 않는다. 커밋 ID와 clean/dirty 상태를 아래에 기록한다.
4. 사용자가 실행 전 해당 커밋에 `psa-xai-v1.2-frozen` 태그를 찍고 태그 대상 커밋을 확인한다. **실제 V1.2 동결은 사용자가 이 태그를 찍을 때 완료된다.** 태그 전에는 V1.2 test 실행을 시작하지 않는다.
5. 동결 뒤 main·era 각 seed 42/43/44에 대해 고정된 addendum과 checkpoint로 실행하고 ledger·결과 해시를 `C11_ADJUDICATION_TEMPLATE.md`에 기록한다. V1.1 ledger는 읽기 전용 비교 근거로 사용한다.

PowerShell 확인 명령(읽기 전용):

```powershell
(Get-FileHash -LiteralPath 'paper/v5-kisa-xai/protocol/PSA_XAI_V1_1_FROZEN.yaml' -Algorithm SHA256).Hash.ToLower()
(Get-FileHash -LiteralPath 'paper/v5-kisa-xai/protocol/PSA_XAI_V1_2_ADDENDUM.yaml' -Algorithm SHA256).Hash.ToLower()
git rev-parse HEAD
git status --short
```

사용자 동결 명령(실행 전 커밋을 확인한 뒤):

```powershell
git tag psa-xai-v1.2-frozen <reviewed-commit-id>
git rev-parse psa-xai-v1.2-frozen^{commit}
```

## 동결 기록란

| 항목 | 기록 |
|---|---|
| V1.1 parent YAML SHA-256 | `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709` (C11-a 재계산 확인) |
| V1.2 addendum YAML SHA-256 | `9712217fc49db0fb1f495a901526e985c731bfe3650dacb1bb875fbe4fcb4162` (C11-a2 보정 후 재계산, 실행 전 재확인) |
| 사전 실행 커밋 ID | ____ |
| 커밋 후 작업 트리 상태 | ____ |
| 사용자 태그 생성 일시 | ____ |
| `psa-xai-v1.2-frozen` 대상 커밋 ID | ____ |
| 실행 시작 일시 | ____ |
