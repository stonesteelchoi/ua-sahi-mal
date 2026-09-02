[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot,

    [Parameter(Mandatory = $true)]
    [string]$PythonExe,

    [Parameter(Mandatory = $true)]
    [string[]]$Annotations,

    [Parameter(Mandatory = $true)]
    [string]$ImagesRoot,

    [Parameter(Mandatory = $true)]
    [string]$SplitMap,

    [Parameter(Mandatory = $true)]
    [string]$WorkRoot,

    [Parameter(Mandatory = $true)]
    [string]$BaseModel,

    [Parameter(Mandatory = $true)]
    [string]$TeacherModel,

    [string]$AnnotationVersion = "decode-bayesian-gradcam-v1",

    [string]$DatasetRevision = "decode-static-v1",

    [ValidateSet("class-agnostic", "roi-family")]
    [string]$ClassPolicy = "class-agnostic",

    [ValidateRange(1, 10000)]
    [int]$Epochs = 100,

    [ValidateRange(1, 4096)]
    [int]$BatchSize = 16,

    [ValidateRange(32, 8192)]
    [int]$ImageSize = 640,

    [string]$Device = "cpu",

    [int]$Seed = 42,

    [ValidateSet("dense", "boxes")]
    [string]$CoarseMode = "dense",

    [ValidateSet("bilinear", "jbu", "upa", "auto")]
    [string]$Upsampler = "jbu",

    [ValidateRange(0.000001, 1.0)]
    [double]$Budget = 0.5,

    [ValidateRange(1, 8192)]
    [int]$SliceHeight = 256,

    [ValidateRange(1, 8192)]
    [int]$SliceWidth = 256,

    [string]$PredictSource,

    [switch]$SkipTraining
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-ExistingFile {
    param([string]$PathValue, [string]$Label)
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        throw "$Label does not exist or is not a file: $PathValue"
    }
    return (Resolve-Path -LiteralPath $PathValue).Path
}

function Resolve-ExistingDirectory {
    param([string]$PathValue, [string]$Label)
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        throw "$Label does not exist or is not a directory: $PathValue"
    }
    return (Resolve-Path -LiteralPath $PathValue).Path
}

function Invoke-PipelinePython {
    param([string[]]$Arguments)
    Write-Host ("python " + ($Arguments -join " "))
    & $script:ResolvedPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

$ResolvedRepo = Resolve-ExistingDirectory -PathValue $RepoRoot -Label "RepoRoot"
$script:ResolvedPython = Resolve-ExistingFile -PathValue $PythonExe -Label "PythonExe"
$ResolvedImages = Resolve-ExistingDirectory -PathValue $ImagesRoot -Label "ImagesRoot"
$ResolvedSplitMap = Resolve-ExistingFile -PathValue $SplitMap -Label "SplitMap"
$ResolvedBaseModel = Resolve-ExistingFile -PathValue $BaseModel -Label "BaseModel"
if ([IO.Path]::GetExtension($ResolvedBaseModel).ToLowerInvariant() -ne ".pt") {
    throw "BaseModel must be a local .pt file: $ResolvedBaseModel"
}
if ($Annotations.Count -lt 1) {
    throw "At least one ROI annotation JSON is required"
}
$ResolvedAnnotations = @()
foreach ($Annotation in $Annotations) {
    $ResolvedAnnotations += Resolve-ExistingFile -PathValue $Annotation -Label "Annotation"
}

$ResolvedWork = [IO.Path]::GetFullPath($WorkRoot)
if (Test-Path -LiteralPath $ResolvedWork) {
    if (-not (Test-Path -LiteralPath $ResolvedWork -PathType Container)) {
        throw "WorkRoot exists but is not a directory: $ResolvedWork"
    }
    if ((Get-ChildItem -LiteralPath $ResolvedWork -Force | Select-Object -First 1)) {
        throw "Refusing to reuse non-empty WorkRoot: $ResolvedWork"
    }
} else {
    New-Item -ItemType Directory -Path $ResolvedWork | Out-Null
}

$env:PYTHONPATH = Join-Path $ResolvedRepo "src"
$env:ULTRALYTICS_SAFE_LOAD = "true"
$env:YOLO_OFFLINE = "true"
$env:YOLO_AUTOINSTALL = "false"
$env:PIP_NO_INDEX = "1"
$env:WANDB_MODE = "offline"

$Manifest = Join-Path $ResolvedWork "manifest.json"
$Prepared = Join-Path $ResolvedWork "prepared"
$DataYaml = Join-Path $Prepared "dataset.yaml"
$TrainRoot = Join-Path $ResolvedWork "train"
$EvaluateRoot = Join-Path $ResolvedWork "evaluate"
$PredictRoot = Join-Path $ResolvedWork "predict"
$CheckpointMetadata = Join-Path $ResolvedWork "checkpoint.metadata.json"
$EvaluationJson = Join-Path $ResolvedWork "detector-test.metrics.json"
$EvaluationCsv = Join-Path $ResolvedWork "detector-test.metrics.csv"
$PipelineInputs = Join-Path $ResolvedWork "pipeline_inputs.json"
$PaperTableInput = Join-Path $ResolvedWork "paper-table.input.json"

$ImportArguments = @(
    "-m", "ua_sahi_mal", "import-decode"
)
foreach ($Annotation in $ResolvedAnnotations) {
    $ImportArguments += @("--annotation", $Annotation)
}
$ImportArguments += @(
    "--images-root", $ResolvedImages,
    "--split-map", $ResolvedSplitMap,
    "--output", $Manifest,
    "--dataset-name", $DatasetRevision,
    "--annotation-version", $AnnotationVersion,
    "--teacher-model", $TeacherModel,
    "--class-policy", $ClassPolicy
)

Push-Location $ResolvedRepo
try {
    Invoke-PipelinePython -Arguments $ImportArguments
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "validate-data",
        "--manifest", $Manifest
    )
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "prepare-data",
        "--manifest", $Manifest,
        "--output-dir", $Prepared,
        "--allow-sensitive-output"
    )

    if ($SkipTraining) {
        $RecordArguments = @(
            "-m", "ua_sahi_mal", "record-run",
            "--repo-root", $ResolvedRepo,
            "--base-model", $ResolvedBaseModel
        )
        foreach ($Annotation in $ResolvedAnnotations) {
            $RecordArguments += @("--annotation", $Annotation)
        }
        $RecordArguments += @(
            "--split-map", $ResolvedSplitMap,
            "--manifest", $Manifest,
            "--data", $DataYaml,
            "--dataset-revision", $DatasetRevision,
            "--teacher-model", $TeacherModel,
            "--annotation-version", $AnnotationVersion,
            "--class-policy", $ClassPolicy,
            "--epochs", $Epochs.ToString(),
            "--batch-size", $BatchSize.ToString(),
            "--image-size", $ImageSize.ToString(),
            "--device", $Device,
            "--seed", $Seed.ToString(),
            "--output", $PipelineInputs
        )
        Invoke-PipelinePython -Arguments $RecordArguments
        Write-Host "Static import/prepare completed. Training was explicitly skipped."
        Write-Host "WorkRoot: $ResolvedWork"
        return
    }

    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "train",
        "--data", $DataYaml,
        "--model", $ResolvedBaseModel,
        "--epochs", $Epochs.ToString(),
        "--image-size", $ImageSize.ToString(),
        "--batch-size", $BatchSize.ToString(),
        "--device", $Device,
        "--seed", $Seed.ToString(),
        "--project", $TrainRoot,
        "--name", "ua-sahi-mal-yolo11"
    )

    $BestCheckpoint = Join-Path $TrainRoot "ua-sahi-mal-yolo11\weights\best.pt"
    $ResolvedBest = Resolve-ExistingFile -PathValue $BestCheckpoint -Label "trained best.pt"
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "validate-checkpoint",
        "--model", $ResolvedBest,
        "--data", $DataYaml,
        "--dataset-revision", $DatasetRevision,
        "--output", $CheckpointMetadata
    )
    $ValidatedCheckpoint = Get-Content -LiteralPath $CheckpointMetadata -Raw | ConvertFrom-Json
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "paper-table-template",
        "--experiment-id", "$DatasetRevision-yolo11-primary",
        "--dataset-revision", $DatasetRevision,
        "--checkpoint-sha256", $ValidatedCheckpoint.sha256,
        "--output", $PaperTableInput
    )
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "evaluate",
        "--data", $DataYaml,
        "--model", $ResolvedBest,
        "--split", "test",
        "--image-size", $ImageSize.ToString(),
        "--batch-size", $BatchSize.ToString(),
        "--device", $Device,
        "--project", $EvaluateRoot,
        "--name", "ua-sahi-mal-test",
        "--dataset-revision", $DatasetRevision,
        "--metrics-json", $EvaluationJson,
        "--metrics-csv", $EvaluationCsv
    )

    if ([string]::IsNullOrWhiteSpace($PredictSource)) {
        $TestImages = Join-Path $Prepared "images\test"
        $Chosen = Get-ChildItem -LiteralPath $TestImages -File |
            Where-Object { $_.Extension.ToLowerInvariant() -in @(".png", ".jpg", ".jpeg") } |
            Sort-Object Name |
            Select-Object -First 1
        if ($null -eq $Chosen) {
            throw "No prepared test image is available for predict"
        }
        $ResolvedPredictSource = $Chosen.FullName
    } else {
        $ResolvedPredictSource = Resolve-ExistingFile -PathValue $PredictSource -Label "PredictSource"
    }
    $GroundTruth = Join-Path $Prepared "annotations\test.json"
    Invoke-PipelinePython -Arguments @(
        "-m", "ua_sahi_mal", "predict",
        "--source", $ResolvedPredictSource,
        "--model", $ResolvedBest,
        "--data", $DataYaml,
        "--dataset-revision", $DatasetRevision,
        "--output-dir", $PredictRoot,
        "--device", $Device,
        "--coarse-mode", $CoarseMode,
        "--upsampler", $Upsampler,
        "--budget", $Budget.ToString([Globalization.CultureInfo]::InvariantCulture),
        "--slice-height", $SliceHeight.ToString(),
        "--slice-width", $SliceWidth.ToString(),
        "--batch-size", "1",
        "--image-size", $ImageSize.ToString(),
        "--ground-truth", $GroundTruth,
        "--iou-threshold", "0.5"
    )

    $RecordArguments = @(
        "-m", "ua_sahi_mal", "record-run",
        "--repo-root", $ResolvedRepo,
        "--base-model", $ResolvedBaseModel
    )
    foreach ($Annotation in $ResolvedAnnotations) {
        $RecordArguments += @("--annotation", $Annotation)
    }
    $RecordArguments += @(
        "--split-map", $ResolvedSplitMap,
        "--manifest", $Manifest,
        "--data", $DataYaml,
        "--dataset-revision", $DatasetRevision,
        "--teacher-model", $TeacherModel,
        "--annotation-version", $AnnotationVersion,
        "--class-policy", $ClassPolicy,
        "--epochs", $Epochs.ToString(),
        "--batch-size", $BatchSize.ToString(),
        "--image-size", $ImageSize.ToString(),
        "--device", $Device,
        "--seed", $Seed.ToString(),
        "--best-checkpoint", $ResolvedBest,
        "--output", $PipelineInputs
    )
    Invoke-PipelinePython -Arguments $RecordArguments
    Write-Host "Pipeline completed: $ResolvedWork"
} finally {
    Pop-Location
}
