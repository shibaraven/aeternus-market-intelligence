$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifactRoot = Join-Path $projectRoot "submission-artifacts"
$packageDir = Join-Path $artifactRoot "Aeternus_BuildWeek_Judge_Package"
$zipPath = Join-Path $artifactRoot "Aeternus_BuildWeek_Judge_Package.zip"
$galleryDir = Join-Path $projectRoot "docs\devpost\gallery"
$liveValidation = Join-Path $projectRoot "docs\LIVE_GPT_VALIDATION.md"

if (-not (Test-Path -LiteralPath $liveValidation -PathType Leaf)) {
    throw "Missing docs/LIVE_GPT_VALIDATION.md."
}
$liveText = Get-Content -LiteralPath $liveValidation -Raw
if ($liveText -notmatch "\*\*PASS\*\*") {
    throw "Judge package refused: live GPT validation has not passed."
}

$required = @(
    "README.md",
    "docs\ARCHITECTURE.md",
    "docs\JUDGE_TESTING_GUIDE.md",
    "docs\VALIDATION_REPORT.md",
    "docs\LIVE_GPT_VALIDATION.md",
    "docs\DEVPOST_SUBMISSION.md",
    "docs\WINDOWS_PORTABLE_BUILD.md",
    "docs\SAMPLE_RESEARCH_REPORT.json",
    "docs\devpost\gallery\01-cover.png",
    "docs\devpost\gallery\02-ai-research-input.png",
    "docs\devpost\gallery\03-live-gpt-tool-timeline.png",
    "docs\devpost\gallery\04-evidence-report.png",
    "docs\devpost\gallery\05-backtest-comparison.png",
    "docs\devpost\gallery\06-architecture.png"
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relative) -PathType Leaf)) {
        throw "Missing required judge-package file: $relative"
    }
}

$resolvedArtifactRoot = [IO.Path]::GetFullPath($artifactRoot)
$resolvedPackageDir = [IO.Path]::GetFullPath($packageDir)
if (-not $resolvedPackageDir.StartsWith($resolvedArtifactRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Package path escaped the submission-artifacts directory."
}
if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}
New-Item -ItemType Directory -Path (Join-Path $packageDir "docs\devpost\gallery") -Force | Out-Null

foreach ($relative in $required) {
    $destination = Join-Path $packageDir $relative
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot $relative) -Destination $destination -Force
}

$hashLines = [Collections.Generic.List[string]]::new()
$executable = Join-Path $projectRoot "dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe"
if (Test-Path -LiteralPath $executable -PathType Leaf) {
    $hash = Get-FileHash -LiteralPath $executable -Algorithm SHA256
    $hashLines.Add("$($hash.Hash.ToLowerInvariant())  AeternusMarketIntelligence.exe")
}
$portableZip = Join-Path $artifactRoot "AeternusMarketIntelligence-Windows-x64.zip"
if (Test-Path -LiteralPath $portableZip -PathType Leaf) {
    $hash = Get-FileHash -LiteralPath $portableZip -Algorithm SHA256
    $hashLines.Add("$($hash.Hash.ToLowerInvariant())  AeternusMarketIntelligence-Windows-x64.zip")
}
if ($hashLines.Count -eq 0) { throw "No portable executable or ZIP was available for SHA256 hashing." }
[IO.File]::WriteAllLines((Join-Path $packageDir "SHA256SUMS.txt"), $hashLines, [Text.UTF8Encoding]::new($false))

$forbiddenFiles = Get-ChildItem -LiteralPath $packageDir -Recurse -File | Where-Object {
    $_.Name -match '^\.env($|\.)|\.(db|sqlite|sqlite3|pem|key)$' -or $_.FullName -match 'node_modules|browser|cache'
}
if ($forbiddenFiles) { throw "Forbidden file detected in judge package: $($forbiddenFiles.FullName -join ', ')" }
$textFiles = Get-ChildItem -LiteralPath $packageDir -Recurse -File | Where-Object { $_.Extension -in @('.md','.txt','.json') }
foreach ($file in $textFiles) {
    $text = Get-Content -LiteralPath $file.FullName -Raw
    if ($text -match '\bsk-[A-Za-z0-9_-]{12,}\b|authorization\s*:\s*bearer') {
        throw "Credential-like content detected in $($file.FullName)"
    }
}

if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $packageDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
$zip = Get-Item -LiteralPath $zipPath
if ($zip.Length -ge 35MB) { throw "Judge package ZIP exceeds 35 MB." }
Write-Output ([ordered]@{
    pass = $true
    folder = "submission-artifacts/Aeternus_BuildWeek_Judge_Package"
    zip = "submission-artifacts/Aeternus_BuildWeek_Judge_Package.zip"
    size_bytes = $zip.Length
    files = (Get-ChildItem -LiteralPath $packageDir -Recurse -File).Count
} | ConvertTo-Json)
