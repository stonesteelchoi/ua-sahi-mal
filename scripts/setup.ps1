param(
    [ValidateSet("cu128", "cpu")]
    [string]$TorchIndex = "cu128",
    [string]$PythonExecutable = "python",
    [switch]$SkipTorch
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

Set-Location -LiteralPath $RepoRoot

$PythonVersion = & $PythonExecutable -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ($LASTEXITCODE -ne 0) {
    throw "Could not execute Python: $PythonExecutable"
}
$PythonVersionObject = [version]$PythonVersion
if ($PythonVersionObject -lt [version]"3.10" -or $PythonVersionObject -ge [version]"3.13") {
    throw "Python 3.10-3.12 is required; found $PythonVersion at $PythonExecutable"
}

git -c "safe.directory=$RepoRoot" submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw "git submodule update failed" }

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExecutable -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "virtual environment creation failed" }
}

& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed" }

if (-not $SkipTorch) {
    $TorchUrl = "https://download.pytorch.org/whl/$TorchIndex"
    & $VenvPython -m pip install torch==2.8.0 torchvision==0.23.0 --index-url $TorchUrl
    if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }
}

& $VenvPython -m pip install "opencv-python>=4.12.0.88,<5" -e (Join-Path $RepoRoot "external\sahi")
if ($LASTEXITCODE -ne 0) { throw "SAHI installation failed" }
& $VenvPython -m pip install -e "${RepoRoot}[dev]"
if ($LASTEXITCODE -ne 0) { throw "project installation failed" }
& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "installed dependency check failed" }
& $VenvPython -c "import cv2; print(cv2.__version__)"
if ($LASTEXITCODE -ne 0) { throw "OpenCV import check failed" }
& $VenvPython -m ua_sahi_mal doctor
if ($LASTEXITCODE -ne 0) { throw "environment doctor failed" }
