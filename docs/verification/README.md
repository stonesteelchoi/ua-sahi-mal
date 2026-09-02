# 환경 검증 기록

`scripts/verify_env.sh` 실행 결과를 보존하는 디렉터리다. `runs/` 는 `.gitignore` 대상이라
검증 근거가 저장소에 남지 않으므로, 논문에 인용할 실행 결과는 이곳에 복사해 커밋한다.

| 파일 | 환경 | 결과 |
|---|---|---|
| `verification-20260902-local-py312.json` | Python 3.12.3 / torch 2.8.0 / CPU (컨테이너 밖 네이티브) | ruff 통과, pytest 107건 통과, 합성 스모크 통과 |

## 아직 채워지지 않은 칸

Docker 이미지 빌드 자체는 아직 실행되지 않았다(작성 환경에서 컨테이너 레지스트리가 차단됨).
네트워크가 되는 장비에서 아래를 실행한 뒤 산출된 `verification.json` 을 이 디렉터리에 추가하면
검증이 완결된다.

```bash
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml run --rm verify
cp runs/verification/<타임스탬프>/verification.json docs/verification/verification-<날짜>-docker.json
```
