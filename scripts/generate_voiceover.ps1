param(
    [string]$VoiceName = "Microsoft Zira Desktop",
    [int]$Rate = 2
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifactDir = Join-Path $projectRoot "submission-artifacts\audio"
$segmentDir = Join-Path $artifactDir "segments"
$outputWav = Join-Path $artifactDir "aeternus_voiceover.wav"
$outputSrt = Join-Path $artifactDir "aeternus_voiceover.srt"
$concatFile = Join-Path $segmentDir "concat.txt"
$silenceFile = Join-Path $segmentDir "silence.wav"

$captions = @(
    "Investment research often scatters charts, company facts, risk metrics, and backtests across separate tools, slowing decisions and hiding important context.",
    "A language model can summarize that material, but a confident figure is not useful unless its origin and calculation can be inspected.",
    "Aeternus Market Intelligence brings the workflow together while keeping every financial calculation inside deterministic, testable application code.",
    "A user chooses the data mode, market, symbol, period, and research question from one focused AI Research screen.",
    "This live result was coordinated by GPT-5.6 through the OpenAI Responses API. The model selected and called strict analytical tools, but it was not allowed to invent the displayed figures.",
    "The completed result identifies the actual model, shows every tool call, and links its structured synthesis back to stable evidence IDs.",
    "Price history, fundamentals, technical indicators, risk, and strategy comparisons are calculated by code; GPT handles planning, comparison, and evidence-grounded explanation.",
    "For a reliable judge path, the application includes a clearly labeled fixed synthetic demo that requires no API key and never pretends that GPT was called.",
    "The AET-DEMO scenario is reproducible, fixed through June thirtieth, twenty twenty-six, and explicitly separated from current market data.",
    "The report combines technical, fundamental, backtest, and risk views. Every evidence card shows its value, unit, date, source, method, and identifier.",
    "The comparison compounds buy-and-hold against the SMA twenty and SMA fifty crossover, shifts signals one session, and states transaction-cost assumptions.",
    "Bull and bear cases appear together with conflicting signals, uncertainties, follow-up questions, data limitations, and a visible financial disclaimer.",
    "The execution timeline provides a compact audit trail, while the server rejects missing evidence categories, unknown citations, and unmatched numerical claims.",
    "Codex audited the existing Flask application, preserved its working features, added the isolated agent boundary and interface, and strengthened tests, packaging, and reviewer documentation.",
    "Automated tests cover the deterministic math, tool scope, structured parsing, evidence enforcement, API behavior, and the credential-free demo path.",
    "Live data still depends on external providers, and backtests remain historical and simplified. The application does not execute trades, and historical performance does not guarantee future results."
)

function Format-SrtTime([double]$Seconds) {
    $time = [TimeSpan]::FromSeconds($Seconds)
    return "{0:00}:{1:00}:{2:00},{3:000}" -f [Math]::Floor($time.TotalHours), $time.Minutes, $time.Seconds, $time.Milliseconds
}

function Get-MediaDuration([string]$Path) {
    $value = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $Path
    if ($LASTEXITCODE -ne 0) { throw "ffprobe could not read $Path" }
    return [double]::Parse(($value | Select-Object -First 1), [Globalization.CultureInfo]::InvariantCulture)
}

New-Item -ItemType Directory -Path $segmentDir -Force | Out-Null
Get-ChildItem -LiteralPath $segmentDir -File -ErrorAction SilentlyContinue | Remove-Item -Force

Add-Type -AssemblyName System.Speech
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $installed = $synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
    if ($VoiceName -notin $installed) {
        $VoiceName = ($synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq "en-US" } | Select-Object -First 1).VoiceInfo.Name
    }
    if (-not $VoiceName) { throw "No English Windows speech voice is installed." }
    $synth.SelectVoice($VoiceName)
    $synth.Rate = $Rate
    $synth.Volume = 100

    for ($index = 0; $index -lt $captions.Count; $index++) {
        $segmentPath = Join-Path $segmentDir ("segment-{0:00}.wav" -f ($index + 1))
        $synth.SetOutputToWaveFile($segmentPath)
        $synth.Speak($captions[$index])
        $synth.SetOutputToNull()
    }
}
finally {
    $synth.Dispose()
}

& ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anullsrc=r=22050:cl=mono" -t 0.32 -c:a pcm_s16le $silenceFile
if ($LASTEXITCODE -ne 0) { throw "Failed to generate inter-caption silence." }

$concatLines = [Collections.Generic.List[string]]::new()
$srtLines = [Collections.Generic.List[string]]::new()
$cursor = 2.0
$leadSilence = Join-Path $segmentDir "lead-silence.wav"
& ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anullsrc=r=22050:cl=mono" -t $cursor -c:a pcm_s16le $leadSilence
if ($LASTEXITCODE -ne 0) { throw "Failed to generate lead silence." }
$concatLines.Add("file '$($leadSilence.Replace("'", "''"))'")

for ($index = 0; $index -lt $captions.Count; $index++) {
    $segmentPath = Join-Path $segmentDir ("segment-{0:00}.wav" -f ($index + 1))
    $duration = Get-MediaDuration $segmentPath
    $start = $cursor
    $end = $start + $duration
    $srtLines.Add(($index + 1).ToString())
    $srtLines.Add("$(Format-SrtTime $start) --> $(Format-SrtTime $end)")
    $srtLines.Add($captions[$index])
    $srtLines.Add("")
    $concatLines.Add("file '$($segmentPath.Replace("'", "''"))'")
    if ($index -lt $captions.Count - 1) {
        $concatLines.Add("file '$($silenceFile.Replace("'", "''"))'")
        $cursor = $end + 0.32
    }
    else {
        $cursor = $end
    }
}

[IO.File]::WriteAllLines($concatFile, $concatLines, [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllLines($outputSrt, $srtLines, [Text.UTF8Encoding]::new($false))

$preNormalized = Join-Path $segmentDir "voiceover-pre-normalized.wav"
& ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $concatFile -ar 48000 -ac 1 -c:a pcm_s16le $preNormalized
if ($LASTEXITCODE -ne 0) { throw "Failed to concatenate voiceover segments." }
& ffmpeg -hide_banner -loglevel error -y -i $preNormalized -af "loudnorm=I=-16:LRA=11:TP=-1.5" -ar 48000 -ac 1 -c:a pcm_s16le $outputWav
if ($LASTEXITCODE -ne 0) { throw "Failed to normalize the voiceover." }

$duration = Get-MediaDuration $outputWav
Write-Output ([ordered]@{
    pass = $true
    voice = $VoiceName
    rate = $Rate
    captions = $captions.Count
    duration_seconds = [Math]::Round($duration, 3)
    wav = "submission-artifacts/audio/aeternus_voiceover.wav"
    srt = "submission-artifacts/audio/aeternus_voiceover.srt"
} | ConvertTo-Json)
