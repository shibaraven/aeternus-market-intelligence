param([switch]$AllowPartial)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceDir = Join-Path $projectRoot "submission-artifacts\raw\gallery-source"
$galleryDir = Join-Path $projectRoot "docs\devpost\gallery"
$fontRegular = "C:\Windows\Fonts\segoeui.ttf"
$fontSemibold = "C:\Windows\Fonts\seguisb.ttf"
if (-not (Test-Path -LiteralPath $fontSemibold)) { $fontSemibold = $fontRegular }

$sources = [ordered]@{
    "01-cover.png" = "cover-base.png"
    "02-ai-research-input.png" = "ai-research-input.png"
    "03-live-gpt-tool-timeline.png" = "live-gpt-tool-timeline.png"
    "04-evidence-report.png" = "evidence-report.png"
    "05-backtest-comparison.png" = "backtest-comparison.png"
    "06-architecture.png" = "architecture.png"
}
$missingSources = @($sources.Values | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $sourceDir $_) -PathType Leaf)
})
if ($missingSources.Count -gt 0 -and -not $AllowPartial) {
    throw "Missing required gallery source(s): $($missingSources -join ', ')"
}
New-Item -ItemType Directory -Path $galleryDir -Force | Out-Null

function Invoke-PngRender([string]$InputPath, [string]$OutputPath, [string]$Filter) {
    & ffmpeg -hide_banner -loglevel error -y -i $InputPath -vf $Filter -frames:v 1 -compression_level 9 $OutputPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to render $OutputPath" }
}

$font = $fontRegular.Replace('\','/').Replace(':','\:')
$fontBold = $fontSemibold.Replace('\','/').Replace(':','\:')
$baseScale = "scale=1800:1200:force_original_aspect_ratio=increase,crop=1800:1200"

$coverFilter = @(
    $baseScale,
    "drawbox=x=0:y=0:w=1800:h=280:color=0x070B15@0.94:t=fill",
    "drawtext=fontfile='$fontBold':text='Aeternus Market Intelligence':fontcolor=white:fontsize=66:x=90:y=64",
    "drawtext=fontfile='$font':text='From market data to evidence-backed stock research in one AI workflow.':fontcolor=0xCBD5E1:fontsize=30:x=94:y=164",
    "drawtext=fontfile='$font':text='GPT-5.6 reasoning  |  Deterministic analytics  |  Traceable evidence':fontcolor=0x93C5FD:fontsize=23:x=94:y=222"
) -join ","
if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["01-cover.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["01-cover.png"]) (Join-Path $galleryDir "01-cover.png") $coverFilter
}

if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["02-ai-research-input.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["02-ai-research-input.png"]) (Join-Path $galleryDir "02-ai-research-input.png") $baseScale
}
if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["03-live-gpt-tool-timeline.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["03-live-gpt-tool-timeline.png"]) (Join-Path $galleryDir "03-live-gpt-tool-timeline.png") $baseScale
}

$reportFilter = @(
    $baseScale,
    "drawbox=x=0:y=0:w=1800:h=74:color=0x070B15@0.92:t=fill",
    "drawtext=fontfile='$fontBold':text='Evidence-grounded report':fontcolor=white:fontsize=30:x=48:y=20",
    "drawtext=fontfile='$font':text='AET-DEMO  |  Data through 2026-06-30  |  Synthetic fixed scenario':fontcolor=0xC4B5FD:fontsize=20:x=1040:y=25"
) -join ","
if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["04-evidence-report.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["04-evidence-report.png"]) (Join-Path $galleryDir "04-evidence-report.png") $reportFilter
}

$backtestFilter = @(
    $baseScale,
    "drawbox=x=0:y=0:w=1800:h=76:color=0x070B15@0.94:t=fill",
    "drawtext=fontfile='$fontBold':text='Buy-and-hold vs. SMA20/SMA50':fontcolor=white:fontsize=30:x=48:y=20",
    "drawtext=fontfile='$font':text='Tested period 2025-07-14 to 2026-06-30  |  Historical results do not guarantee future results.':fontcolor=0xFDE68A:fontsize=19:x=710:y=26"
) -join ","
if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["05-backtest-comparison.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["05-backtest-comparison.png"]) (Join-Path $galleryDir "05-backtest-comparison.png") $backtestFilter
}

if (Test-Path -LiteralPath (Join-Path $sourceDir $sources["06-architecture.png"])) {
    Invoke-PngRender (Join-Path $sourceDir $sources["06-architecture.png"]) (Join-Path $galleryDir "06-architecture.png") $baseScale
}

Add-Type -AssemblyName System.Drawing
$results = @()
foreach ($name in $sources.Keys) {
    $path = Join-Path $galleryDir $name
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    $file = Get-Item -LiteralPath $path
    $image = [Drawing.Image]::FromFile($path)
    try {
        $valid = $image.Width -eq 1800 -and $image.Height -eq 1200 -and $file.Length -lt 5MB
        $results += [ordered]@{
            file = "docs/devpost/gallery/$name"
            width = $image.Width
            height = $image.Height
            size_bytes = $file.Length
            pass = $valid
        }
    }
    finally {
        $image.Dispose()
    }
}
if ($results.pass -contains $false) { throw "One or more Devpost images failed size or dimension validation." }
Write-Output ([ordered]@{
    complete = $missingSources.Count -eq 0
    generated = $results
    missing_sources = $missingSources
} | ConvertTo-Json -Depth 4)
