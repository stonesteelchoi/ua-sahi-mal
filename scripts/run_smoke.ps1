param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment is missing. Run scripts/setup_cpu.ps1 first."
}

if ($OutputDirectory) {
    & $VenvPython -m ua_sahi_mal smoke --output-dir $OutputDirectory
} else {
    & $VenvPython -m ua_sahi_mal smoke
}

if ($LASTEXITCODE -ne 0) { throw "synthetic smoke workflow failed" }
