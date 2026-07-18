$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$failures = [Collections.Generic.List[string]]::new()
$checks = [Collections.Generic.List[object]]::new()

function Add-Check([string]$Name, [bool]$Passed, [string]$Detail) {
    $checks.Add([ordered]@{ name = $Name; pass = $Passed; detail = $Detail })
    if (-not $Passed) { $failures.Add("$Name — $Detail") }
}

function Test-RequiredFile([string]$RelativePath) {
    $path = Join-Path $projectRoot $RelativePath
    $exists = Test-Path -LiteralPath $path -PathType Leaf
    Add-Check "File: $RelativePath" $exists $(if ($exists) { "present" } else { "missing" })
    return $exists
}

$requiredDocs = @(
    "README.md",
    "docs\ARCHITECTURE.md",
    "docs\JUDGE_TESTING_GUIDE.md",
    "docs\VALIDATION_REPORT.md",
    "docs\LIVE_GPT_VALIDATION.md",
    "docs\DEVPOST_SUBMISSION.md",
    "docs\YOUTUBE_METADATA.md",
    "docs\FINAL_SUBMISSION_CHECKLIST.md",
    "docs\DEMO_SCRIPT.md",
    "docs\DEMO_SHOT_LIST.md",
    "docs\SAMPLE_RESEARCH_REPORT.json",
    "docs\WINDOWS_PORTABLE_BUILD.md"
)
foreach ($relative in $requiredDocs) { [void](Test-RequiredFile $relative) }

$liveDocument = Join-Path $projectRoot "docs\LIVE_GPT_VALIDATION.md"
$livePass = (Test-Path -LiteralPath $liveDocument) -and ((Get-Content -LiteralPath $liveDocument -Raw) -match "\*\*PASS\*\*")
Add-Check "Genuine GPT-5.6 validation" $livePass $(if ($livePass) { "PASS record present" } else { "PASS record absent" })
$liveReport = Join-Path $projectRoot "submission-artifacts\raw\live-gpt-report.json"
$liveReportValid = $false
if (Test-Path -LiteralPath $liveReport -PathType Leaf) {
    try {
        $report = Get-Content -LiteralPath $liveReport -Raw | ConvertFrom-Json
        $liveReportValid = (
            $report.gpt_used -eq $true -and
            $report.model -like "gpt-5.6-sol*" -and
            $report.live_validation.structured_output_valid -eq $true -and
            $report.live_validation.numerical_traceability_valid -eq $true
        )
    }
    catch { $liveReportValid = $false }
}
Add-Check "Sanitized live report" $liveReportValid $(if ($liveReportValid) { "validated" } else { "missing or invalid" })

$audioFiles = @(
    "submission-artifacts\audio\aeternus_voiceover.wav",
    "submission-artifacts\audio\aeternus_voiceover.srt"
)
foreach ($relative in $audioFiles) { [void](Test-RequiredFile $relative) }

Add-Type -AssemblyName System.Drawing
for ($index = 1; $index -le 6; $index++) {
    $match = Get-ChildItem -LiteralPath (Join-Path $projectRoot "docs\devpost\gallery") -Filter ("{0:00}-*.png" -f $index) -File -ErrorAction SilentlyContinue
    $valid = $false
    $detail = "missing"
    if (@($match).Count -eq 1) {
        $image = [Drawing.Image]::FromFile($match.FullName)
        try {
            $valid = $image.Width -eq 1800 -and $image.Height -eq 1200 -and $match.Length -lt 5MB
            $detail = "$($image.Width)x$($image.Height), $($match.Length) bytes"
        }
        finally { $image.Dispose() }
    }
    elseif (@($match).Count -gt 1) { $detail = "multiple matching images" }
    Add-Check ("Gallery {0:00}" -f $index) $valid $detail
}

$video = Join-Path $projectRoot "submission-artifacts\Aeternus_OpenAI_Build_Week_Demo.mp4"
$videoValidation = Join-Path $projectRoot "submission-artifacts\VIDEO_VALIDATION.txt"
$videoPass = (Test-Path -LiteralPath $video -PathType Leaf) -and (Test-Path -LiteralPath $videoValidation -PathType Leaf)
if ($videoPass) {
    $validationText = Get-Content -LiteralPath $videoValidation -Raw
    $videoPass = $validationText -notmatch '\[FAIL\]' -and $validationText -match '\[PASS\] H\.264 video' -and $validationText -match '\[PASS\] AAC audio'
}
Add-Check "Final MP4 and ffprobe validation" $videoPass $(if ($videoPass) { "validated" } else { "missing or contains a failed check" })

$judgeFolder = Join-Path $projectRoot "submission-artifacts\Aeternus_BuildWeek_Judge_Package"
$judgeZip = Join-Path $projectRoot "submission-artifacts\Aeternus_BuildWeek_Judge_Package.zip"
$judgePass = (Test-Path -LiteralPath $judgeFolder -PathType Container) -and (Test-Path -LiteralPath $judgeZip -PathType Leaf) -and ((Get-Item -LiteralPath $judgeZip).Length -lt 35MB)
Add-Check "Judge package" $judgePass $(if ($judgePass) { "$((Get-Item -LiteralPath $judgeZip).Length) bytes" } else { "missing or at least 35 MB" })

& git -C $projectRoot diff --check
$diffPass = $LASTEXITCODE -eq 0
Add-Check "Git diff whitespace" $diffPass $(if ($diffPass) { "PASS" } else { "git diff --check failed" })

$trackedLarge = @(& git -C $projectRoot ls-files | Where-Object { $_ -match '\.(mp4|webm|wav|zip)$' })
Add-Check "Large generated media untracked" ($trackedLarge.Count -eq 0) $(if ($trackedLarge.Count -eq 0) { "PASS" } else { $trackedLarge -join ", " })

$result = [ordered]@{
    pass = $failures.Count -eq 0
    checks = $checks
    failures = $failures
}
Write-Output ($result | ConvertTo-Json -Depth 5)
if ($failures.Count -gt 0) { exit 1 }
