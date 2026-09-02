param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "setup.ps1") -TorchIndex cpu -PythonExecutable $PythonExecutable
