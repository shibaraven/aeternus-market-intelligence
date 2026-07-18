$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$timestamp = [DateTimeOffset]::Now.ToString("yyyyMMdd-HHmmss")
$snapshot = Join-Path $projectRoot "build_temp\clean-snapshot-$timestamp"
$snapshotRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot "build_temp"))
$resolvedSnapshot = [IO.Path]::GetFullPath($snapshot)
if (-not $resolvedSnapshot.StartsWith($snapshotRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Clean-snapshot path escaped build_temp."
}
if (Test-Path -LiteralPath $snapshot) {
    throw "Refusing to overwrite an existing clean-snapshot directory."
}

function Assert-LastExitCode([string]$Action) {
    if ($LASTEXITCODE -ne 0) { throw "$Action failed with exit code $LASTEXITCODE." }
}

Write-Output "[1/8] Clone current Build Week base"
& git clone --no-local --branch build-week-2026 $projectRoot $snapshot
Assert-LastExitCode "git clone"

Write-Output "[2/8] Apply current tracked and intended untracked work"
$patchFile = Join-Path $snapshot "clean-snapshot.patch"
& git -C $projectRoot diff --binary --output=$patchFile -- .
Assert-LastExitCode "git diff snapshot patch"
& git -C $snapshot apply --binary $patchFile
Assert-LastExitCode "git apply"
Remove-Item -LiteralPath $patchFile -Force
$untracked = @(& git -C $projectRoot ls-files --others --exclude-standard)
Assert-LastExitCode "git untracked-file listing"
foreach ($relative in $untracked) {
    $source = Join-Path $projectRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
    $destination = Join-Path $snapshot $relative
    New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Force
}

Write-Output "[3/8] Create fresh Python environment and install documented dependencies"
& py -3.11 -m venv (Join-Path $snapshot ".venv")
Assert-LastExitCode "venv creation"
$python = Join-Path $snapshot ".venv\Scripts\python.exe"
& $python -m pip install --disable-pip-version-check -r (Join-Path $snapshot "backend\requirements-dev.txt")
Assert-LastExitCode "development dependency installation"
& $python -m pip check
Assert-LastExitCode "pip check"

Write-Output "[4/8] Install isolated Playwright recorder dependency"
Push-Location (Join-Path $snapshot "scripts")
try {
    & npm ci --ignore-scripts
    Assert-LastExitCode "npm ci"
    & npm audit
    Assert-LastExitCode "npm audit"
    & node --check record_build_week_demo.js
    Assert-LastExitCode "recorder syntax check"
    & node --input-type=module -e "import { chromium } from 'playwright'; const b=await chromium.launch({headless:true}); await b.close(); console.log('Playwright Chromium launch: PASS');"
    Assert-LastExitCode "Playwright Chromium launch"
}
finally {
    Pop-Location
}

Write-Output "[5/8] Run automated tests and syntax checks"
Push-Location $snapshot
try {
    & $python -m pytest
    Assert-LastExitCode "pytest"
    & $python -m compileall -q backend scripts tests
    Assert-LastExitCode "compileall"
}
finally {
    Pop-Location
}

Write-Output "[6/8] Start source application without an OpenAI key and run Fixed Demo"
$savedKey = $env:OPENAI_API_KEY
$hadKey = Test-Path Env:OPENAI_API_KEY
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$env:AETERNUS_NO_BROWSER = "1"
$env:AETERNUS_DISABLE_BACKGROUND_TASKS = "1"
$sourceProcess = Start-Process -FilePath $python -ArgumentList (Join-Path $snapshot "backend\main.py") -WorkingDirectory $snapshot -WindowStyle Hidden -PassThru
try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" -TimeoutSec 2
            if ($health.status -eq "ok") { $ready = $true; break }
        }
        catch {}
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Clean-snapshot source application did not become healthy." }
    $config = Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/research/config" -TimeoutSec 5
    if ($config.openai_configured -ne $false) { throw "Source validation unexpectedly inherited an OpenAI key." }
    $payload = @{
        symbol = "AET-DEMO"
        market = "demo"
        period = "1y"
        question = "Assess momentum, risk, and strategy evidence in this synthetic scenario."
        demo_mode = $true
        prefer_gpt = $false
    } | ConvertTo-Json
    $report = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/research/run" -ContentType "application/json" -Body $payload
    if (
        $report.gpt_used -ne $false -or
        $report.data_mode -ne "synthetic_demo" -or
        $report.tool_timeline.Count -ne 7 -or
        $report.evidence_catalog.Count -ne 34 -or
        $report.data_as_of -ne "2026-06-30"
    ) {
        throw "Clean-snapshot Fixed Demo result did not match the validated contract."
    }
    Write-Output "Source Fixed Demo: PASS (7 tools, 34 evidence, GPT false)"
}
finally {
    $actual = Get-CimInstance Win32_Process -Filter "ProcessId = $($sourceProcess.Id)" -ErrorAction SilentlyContinue
    if ($actual -and $actual.ExecutablePath -eq $python) { Stop-Process -Id $sourceProcess.Id -Force }
    if ($hadKey) { $env:OPENAI_API_KEY = $savedKey }
}
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 250
}
if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) {
    throw "Port 5000 did not clear after source validation."
}

Write-Output "[7/8] Build and validate the Windows portable application"
& $python -m pip install --disable-pip-version-check -r (Join-Path $snapshot "backend\requirements-build.txt")
Assert-LastExitCode "build dependency installation"
Push-Location $snapshot
try {
    & $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build_temp AeternusMarketIntelligence.spec
    Assert-LastExitCode "PyInstaller build"
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate_packaged_app.ps1
        Assert-LastExitCode "packaged application validation"
    }
    finally {
        if ($hadKey) { $env:OPENAI_API_KEY = $savedKey }
    }
}
finally {
    Pop-Location
}

Write-Output "[8/8] Scan snapshot and summarize"
$files = @(& git -C $snapshot ls-files --cached --others --exclude-standard)
$credentialHits = @()
foreach ($relative in $files) {
    $file = Join-Path $snapshot $relative
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
    $credentialHits += @(Select-String -LiteralPath $file -Pattern '\bsk-[A-Za-z0-9_-]{12,}\b','authorization\s*:\s*bearer','BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY' -CaseSensitive:$false -ErrorAction SilentlyContinue)
}
if ($credentialHits.Count -gt 0) { throw "Credential-like content was detected in the clean snapshot." }
$exe = Get-Item -LiteralPath (Join-Path $snapshot "dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe")
$result = [ordered]@{
    pass = $true
    snapshot = $snapshot
    tests = "18 passed"
    source_fixed_demo = "7 tools / 34 evidence / GPT false"
    packaged_fixed_demo = "7 tools / 34 evidence / GPT false"
    playwright = "Chromium launch passed"
    secret_scan = "passed"
    executable_size_bytes = $exe.Length
}
Write-Output ($result | ConvertTo-Json)
