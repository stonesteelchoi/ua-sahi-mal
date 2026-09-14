param(
    # Run scripts/setup.ps1 -TorchIndex <TorchIndex> before the checks.
    [switch]$Install,
    [ValidateSet("cu128", "cpu")]
    [string]$TorchIndex = "cu128",
    [string]$PythonExecutable = "python",
    # Skip the slow steps (pytest, build) when only the GPU/environment facts are needed.
    [switch]$Quick
)

# KISA-XAI-v5 environment check for a Windows NVIDIA workstation.
# Mirrors paper/v5-kisa-xai/HANDOFF_PROMPT_KO.md section 3 and docs/NEW_MACHINE_HANDOFF.md.
# Every step is recorded (exit code + log) in runs/kisa-xai-env-<tag>/ and summarised in summary.json.
# The script never stops at the first failure so that the full picture is captured in one run.

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepoRoot

$RunTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$CheckDir = Join-Path $RepoRoot "runs/kisa-xai-env-$RunTag"
New-Item -ItemType Directory -Path $CheckDir -Force | Out-Null
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

$Summary = [ordered]@{
    run_tag           = $RunTag
    started_at        = (Get-Date).ToString("o")
    repo_root         = $RepoRoot
    git_head          = (git rev-parse HEAD 2>$null)
    git_branch        = (git branch --show-current 2>$null)
    git_dirty         = [bool](git status --porcelain 2>$null)
    baseline_4b1f6ee_is_ancestor = $null
    os                = $null
    python            = $null
    gpu               = $null
    steps             = [ordered]@{}
}

git merge-base --is-ancestor 4b1f6ee HEAD 2>$null
$Summary.baseline_4b1f6ee_is_ancestor = ($LASTEXITCODE -eq 0)

function Invoke-Step {
    param([string]$Name, [scriptblock]$Command, [switch]$Skip)
    $LogPath = Join-Path $CheckDir ("{0}.log" -f $Name)
    if ($Skip) {
        $Summary.steps[$Name] = [ordered]@{ status = "skipped"; exit_code = $null; log = $LogPath }
        Write-Host ("[skip] {0}" -f $Name)
        return
    }
    Write-Host ("[step] {0}" -f $Name)
    $Started = Get-Date
    Set-Content -Path $LogPath -Value "" -Encoding utf8
    try {
        # Native stderr arrives as ErrorRecord objects under 2>&1; render them as plain text so
        # progress messages (e.g. `python -m build`) are not shown as red NativeCommandError blocks,
        # and write UTF-8 logs (Tee-Object in Windows PowerShell 5.1 would write UTF-16).
        & $Command 2>&1 | ForEach-Object {
            $Line = if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { "$_" }
            Add-Content -Path $LogPath -Value $Line -Encoding utf8
            Write-Host $Line
        }
        $Code = $LASTEXITCODE
    } catch {
        Add-Content -Path $LogPath -Value ("{0}" -f $_) -Encoding utf8
        $Code = 1
    }
    if ($null -eq $Code) { $Code = 0 }
    $Summary.steps[$Name] = [ordered]@{
        status    = $(if ($Code -eq 0) { "ok" } else { "failed" })
        exit_code = $Code
        seconds   = [math]::Round(((Get-Date) - $Started).TotalSeconds, 1)
        log       = $LogPath
    }
}

# --- 1. hardware / OS facts -------------------------------------------------
$OsInfo = Get-CimInstance Win32_OperatingSystem
$Summary.os = [ordered]@{
    caption        = $OsInfo.Caption
    version        = $OsInfo.Version
    total_ram_gib  = [math]::Round($OsInfo.TotalVisibleMemorySize / 1MB, 1)
    free_ram_gib   = [math]::Round($OsInfo.FreePhysicalMemory / 1MB, 1)
}
$Summary.disks = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    [ordered]@{ drive = $_.DeviceID; size_gib = [math]::Round($_.Size / 1GB, 1); free_gib = [math]::Round($_.FreeSpace / 1GB, 1) }
})

$NvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($NvidiaSmi) {
    nvidia-smi | Out-File (Join-Path $CheckDir "nvidia-smi.txt") -Encoding utf8
    $GpuQuery = nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
    $Summary.gpu = [ordered]@{ nvidia_smi = "present"; query = ($GpuQuery -join "; ") }
} else {
    $Summary.gpu = [ordered]@{ nvidia_smi = "not found"; query = $null }
}

$Summary.python = [ordered]@{
    system_python = (& $PythonExecutable --version 2>&1 | Out-String).Trim()
    venv_exists   = (Test-Path -LiteralPath $VenvPython)
}

# --- 2. optional install ----------------------------------------------------
if ($Install) {
    Invoke-Step -Name "00_setup_ps1" -Command {
        powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts/setup.ps1") -TorchIndex $TorchIndex -PythonExecutable $PythonExecutable
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Warning "No .venv found at $VenvPython. Re-run with -Install (or run scripts/setup.ps1 first)."
    $Summary.finished_at = (Get-Date).ToString("o")
    $Summary | ConvertTo-Json -Depth 6 | Out-File (Join-Path $CheckDir "summary.json") -Encoding utf8
    Write-Host "Summary written to $CheckDir\summary.json"
    exit 2
}

# --- 3. environment checks --------------------------------------------------
Invoke-Step -Name "01_pip_check" -Command { & $VenvPython -m pip check }
Invoke-Step -Name "02_doctor_strict" -Command { & $VenvPython -m ua_sahi_mal doctor --strict }
Invoke-Step -Name "03_cuda_compute" -Command {
    & $VenvPython -c "import torch; print('torch=', torch.__version__); print('cuda_runtime=', torch.version.cuda); assert torch.cuda.is_available(), 'CUDA unavailable'; print('gpu=', torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); free,total=torch.cuda.mem_get_info(); print('vram_total_mib=', total//2**20, 'vram_free_mib=', free//2**20); x=torch.randn(512,512,device='cuda'); y=x@x; torch.cuda.synchronize(); assert torch.isfinite(y).all().item(); print('CUDA computation OK:', y.device)"
}
Invoke-Step -Name "04_pip_freeze" -Command { & $VenvPython -m pip freeze | Out-File (Join-Path $CheckDir "pip-freeze.txt") -Encoding utf8; Get-Content (Join-Path $CheckDir "pip-freeze.txt") | Select-Object -First 5 }

# --- 4. regression checks (existing code; not v5 results) -------------------
Invoke-Step -Name "05_ruff" -Command { & $VenvPython -m ruff check src tests scripts }
Invoke-Step -Name "06_pytest" -Skip:$Quick -Command { & $VenvPython -m pytest }
Invoke-Step -Name "07_smoke" -Command { & $VenvPython -m ua_sahi_mal smoke }
Invoke-Step -Name "08_evidence_smoke" -Command { & $VenvPython -m ua_sahi_mal.evidence smoke --out (Join-Path $CheckDir "evidence-smoke") }
Invoke-Step -Name "09_repository_safety" -Command { & $VenvPython scripts/check_repository_safety.py }
Invoke-Step -Name "10_audit_paper_numbers" -Command { & $VenvPython scripts/audit_paper_numbers.py }
Invoke-Step -Name "11_build" -Skip:$Quick -Command { & $VenvPython -m build }

$Summary.finished_at = (Get-Date).ToString("o")
$Summary | ConvertTo-Json -Depth 6 | Out-File (Join-Path $CheckDir "summary.json") -Encoding utf8

Write-Host ""
Write-Host "==== KISA-XAI-v5 environment check summary ($RunTag) ===="
foreach ($k in $Summary.steps.Keys) {
    $s = $Summary.steps[$k]
    Write-Host ("{0,-24} {1,-8} exit={2}" -f $k, $s.status, $s.exit_code)
}
Write-Host "Summary written to $CheckDir\summary.json"
Write-Host "Passing doctor/smoke/pytest is a repository regression check only; it is not a KISA-XAI-v5 experimental result."
