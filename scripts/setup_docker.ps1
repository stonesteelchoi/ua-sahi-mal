<#
.SYNOPSIS
    UA-SAHI-MAL 컨테이너 이미지를 빌드하고 검증한다.

.DESCRIPTION
    docker compose build -> verify -> (선택) offline 검증을 순서대로 실행하고,
    산출된 verification.json 을 docs/verification/ 에 복사해 커밋 가능한 상태로 만든다.

.PARAMETER TorchIndexUrl
    기본값은 CPU 휠 인덱스. 사내 프록시가 download.pytorch.org 를 막으면 'pypi',
    GPU 면 'https://download.pytorch.org/whl/cu124' 를 넘긴다.

.PARAMETER BaseImage
    Docker Hub 가 막힌 경우 사내 레지스트리 미러를 지정한다.

.EXAMPLE
    .\scripts\setup_docker.ps1
    .\scripts\setup_docker.ps1 -TorchIndexUrl pypi
    .\scripts\setup_docker.ps1 -BaseImage registry.corp/library/python:3.12-slim -SkipOffline
#>
param(
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cpu",
    [string]$BaseImage     = "python:3.12-slim",
    [string]$AptMirror     = "",
    [switch]$SkipOffline
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Compose = @("compose", "-f", "docker/docker-compose.yml")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker 를 찾을 수 없습니다. Docker Desktop 을 설치하고 실행하십시오."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker 데몬에 연결할 수 없습니다. Docker Desktop 이 실행 중인지 확인하십시오." }

$env:BASE_IMAGE      = $BaseImage
$env:TORCH_INDEX_URL = $TorchIndexUrl
$env:APT_MIRROR      = $AptMirror

Write-Host "[1/3] 이미지 빌드 (base=$BaseImage, torch index=$TorchIndexUrl)" -ForegroundColor Cyan
& docker @Compose build
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "빌드 실패. 프록시가 막힌 환경이라면 아래를 시도하십시오:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_docker.ps1 -TorchIndexUrl pypi"
    Write-Host "  .\scripts\setup_docker.ps1 -BaseImage <사내 미러>/library/python:3.12-slim"
    throw "docker compose build 실패"
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")

Write-Host "[2/3] 검증" -ForegroundColor Cyan
& docker @Compose run --rm verify bash /workspace/scripts/verify_env.sh "runs/verification/docker-$Stamp"
if ($LASTEXITCODE -ne 0) { throw "검증 실패 — runs/verification/docker-$Stamp 의 로그를 확인하십시오." }

if (-not $SkipOffline) {
    Write-Host "[3/3] 네트워크 차단 상태로 재검증" -ForegroundColor Cyan
    & docker @Compose run --rm offline bash /workspace/scripts/verify_env.sh "runs/verification/docker-offline-$Stamp"
    if ($LASTEXITCODE -ne 0) { throw "오프라인 검증 실패 — 저장소는 fail-closed 로 동작해야 합니다." }
} else {
    Write-Host "[3/3] 오프라인 검증 건너뜀" -ForegroundColor DarkGray
}

$Src = Join-Path $RepoRoot "runs\verification\docker-$Stamp\verification.json"
$Dst = Join-Path $RepoRoot ("docs\verification\verification-{0}-docker.json" -f (Get-Date).ToString("yyyyMMdd"))
if (Test-Path $Src) {
    Copy-Item $Src $Dst -Force
    Write-Host ""
    Write-Host "검증 결과를 커밋 가능한 위치로 복사했습니다: $Dst" -ForegroundColor Green
    Write-Host "  git add docs/verification && git commit -m ""Add Docker build verification result"""
}
Write-Host "완료." -ForegroundColor Green
