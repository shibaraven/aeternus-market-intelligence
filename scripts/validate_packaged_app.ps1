$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$exe = (Resolve-Path (Join-Path $projectRoot "dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe")).Path
$listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port 5000 is already in use." }

$env:AETERNUS_NO_BROWSER = "1"
$env:AETERNUS_DISABLE_BACKGROUND_TASKS = "1"
$process = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden -PassThru
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
    if (-not $ready) { throw "Packaged application did not become healthy." }

    $payload = @{
        symbol = "AET-DEMO"
        market = "demo"
        period = "1y"
        question = "Assess whether improving momentum is supported by risk and SMA crossover backtest evidence."
        demo_mode = $true
        prefer_gpt = $false
    } | ConvertTo-Json
    $report = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:5000/api/research/run" -ContentType "application/json" -Body $payload
    $html = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000").Content
    $result = [ordered]@{
        health = $health.status
        gpt_used = $report.gpt_used
        synthesis_mode = $report.synthesis_mode
        tools = $report.tool_timeline.Count
        evidence = $report.evidence_catalog.Count
        data_as_of = $report.data_as_of
        disclaimer = $report.disclaimer -match "does not execute trades"
        visible_evidence_id_markup = $html -match "Evidence ID:"
    }
    if (
        $result.health -ne "ok" -or
        $result.gpt_used -ne $false -or
        $result.tools -lt 7 -or
        $result.evidence -lt 30 -or
        -not $result.disclaimer -or
        -not $result.visible_evidence_id_markup
    ) {
        throw "Packaged application validation failed."
    }
    Write-Output ($result | ConvertTo-Json)
}
finally {
    $actual = Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)" -ErrorAction SilentlyContinue
    if ($actual -and $actual.ExecutablePath -eq $exe) {
        Stop-Process -Id $process.Id -Force
    }
}
