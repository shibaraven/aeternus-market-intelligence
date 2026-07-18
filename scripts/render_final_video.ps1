param(
    [int]$Crf = 20
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$artifactDir = Join-Path $projectRoot "submission-artifacts"
$rawVideo = Join-Path $artifactDir "raw\aeternus-demo-raw.webm"
$voiceover = Join-Path $artifactDir "audio\aeternus_voiceover.wav"
$subtitles = Join-Path $artifactDir "audio\aeternus_voiceover.srt"
$outputVideo = Join-Path $artifactDir "Aeternus_OpenAI_Build_Week_Demo.mp4"
$validationFile = Join-Path $artifactDir "VIDEO_VALIDATION.txt"
$tempDir = Join-Path $artifactDir "raw\video-render"
$titleCard = Join-Path $tempDir "title-card.mp4"
$endCard = Join-Path $tempDir "end-card.mp4"
$titleDuration = 7.0
$endDuration = 10.0

foreach ($required in @($rawVideo, $voiceover, $subtitles)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required media input: $required"
    }
}

New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
$fontRegular = "C:\Windows\Fonts\segoeui.ttf"
$fontSemibold = "C:\Windows\Fonts\seguisb.ttf"
if (-not (Test-Path -LiteralPath $fontSemibold)) { $fontSemibold = $fontRegular }

$titleFilter = @(
    "drawtext=fontfile='$($fontSemibold.Replace('\','/').Replace(':','\:'))':text='Aeternus Market Intelligence':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=360",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='From market data to evidence-backed stock research':fontcolor=0xCBD5E1:fontsize=34:x=(w-text_w)/2:y=485",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='in one AI workflow.':fontcolor=0xCBD5E1:fontsize=34:x=(w-text_w)/2:y=540"
) -join ","

& ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "color=c=0x070B15:s=1920x1080:r=30:d=$titleDuration" `
    -vf $titleFilter -an -c:v libx264 -preset medium -crf $Crf -pix_fmt yuv420p $titleCard
if ($LASTEXITCODE -ne 0) { throw "Failed to render the title card." }

$endFilter = @(
    "drawtext=fontfile='$($fontSemibold.Replace('\','/').Replace(':','\:'))':text='Aeternus Market Intelligence':fontcolor=white:fontsize=64:x=(w-text_w)/2:y=275",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='GPT-5.6 reasoning.':fontcolor=0x93C5FD:fontsize=36:x=(w-text_w)/2:y=430",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='Deterministic analytics.':fontcolor=0xA7F3D0:fontsize=36:x=(w-text_w)/2:y=486",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='Traceable evidence.':fontcolor=0xC4B5FD:fontsize=36:x=(w-text_w)/2:y=542",
    "drawtext=fontfile='$($fontRegular.Replace('\','/').Replace(':','\:'))':text='For research and educational purposes only.':fontcolor=0xCBD5E1:fontsize=27:x=(w-text_w)/2:y=690"
) -join ","

& ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "color=c=0x070B15:s=1920x1080:r=30:d=$endDuration" `
    -vf $endFilter -an -c:v libx264 -preset medium -crf $Crf -pix_fmt yuv420p $endCard
if ($LASTEXITCODE -ne 0) { throw "Failed to render the end card." }

$rawDurationText = & ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $rawVideo
if ($LASTEXITCODE -ne 0) { throw "ffprobe could not read the raw recording." }
$rawDuration = [double]::Parse(($rawDurationText | Select-Object -First 1), [Globalization.CultureInfo]::InvariantCulture)
$finalDuration = $titleDuration + $rawDuration + $endDuration

Push-Location $projectRoot
try {
    $subtitleFilterPath = "submission-artifacts/audio/aeternus_voiceover.srt"
    $filter = @"
[0:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[title];
[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[demo];
[2:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1[end];
[title][demo][end]concat=n=3:v=1:a=0[base];
[base]subtitles='$subtitleFilterPath':force_style='FontName=Segoe UI,FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&HCC000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=42,Alignment=2'[video];
[3:a]aresample=48000,apad=pad_dur=$([Math]::Ceiling($finalDuration))[audio]
"@ -replace "`r?`n", ""

    & ffmpeg -hide_banner -loglevel error -y `
        -i $titleCard -i $rawVideo -i $endCard -i $voiceover `
        -filter_complex $filter `
        -map "[video]" -map "[audio]" -t $finalDuration `
        -c:v libx264 -preset medium -crf $Crf -pix_fmt yuv420p -r 30 `
        -c:a aac -b:a 192k -movflags +faststart $outputVideo
    if ($LASTEXITCODE -ne 0) { throw "Failed to render the final video." }
}
finally {
    Pop-Location
}

$probeText = & ffprobe -v error -show_streams -show_format $outputVideo | Out-String
if ($LASTEXITCODE -ne 0) { throw "ffprobe validation failed." }
$probeJson = & ffprobe -v error -show_streams -show_format -of json $outputVideo | ConvertFrom-Json
$videoStream = $probeJson.streams | Where-Object { $_.codec_type -eq "video" } | Select-Object -First 1
$audioStream = $probeJson.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1
$duration = [double]::Parse($probeJson.format.duration, [Globalization.CultureInfo]::InvariantCulture)
$fileSize = (Get-Item -LiteralPath $outputVideo).Length

$checks = [ordered]@{
    "MP4 container" = $probeJson.format.format_name -match "mp4"
    "H.264 video" = $videoStream.codec_name -eq "h264"
    "AAC audio" = $audioStream.codec_name -eq "aac"
    "1920x1080" = ($videoStream.width -eq 1920 -and $videoStream.height -eq 1080)
    "yuv420p" = $videoStream.pix_fmt -eq "yuv420p"
    "audio track present" = $null -ne $audioStream
    "duration below 180 seconds" = $duration -lt 180
    "preferred 150-170 seconds" = ($duration -ge 150 -and $duration -le 170)
}
$passed = -not ($checks.Values -contains $false)

$lines = [Collections.Generic.List[string]]::new()
$lines.Add("Aeternus OpenAI Build Week Demo — Video Validation")
$lines.Add("Generated: $([DateTimeOffset]::Now.ToString('o'))")
$lines.Add("File: submission-artifacts/Aeternus_OpenAI_Build_Week_Demo.mp4")
$lines.Add("Size bytes: $fileSize")
$lines.Add("Duration seconds: $($duration.ToString('0.000', [Globalization.CultureInfo]::InvariantCulture))")
$lines.Add("")
$lines.Add("PASS/FAIL CHECKLIST")
foreach ($entry in $checks.GetEnumerator()) {
    $lines.Add("[$(if ($entry.Value) {'PASS'} else {'FAIL'})] $($entry.Key)")
}
$lines.Add("")
$lines.Add("EXACT FFPROBE OUTPUT")
$lines.Add($probeText.TrimEnd())
[IO.File]::WriteAllLines($validationFile, $lines, [Text.UTF8Encoding]::new($false))

if (-not $passed) { throw "The rendered video did not pass every technical check. See VIDEO_VALIDATION.txt." }
Write-Output ([ordered]@{
    pass = $true
    duration_seconds = [Math]::Round($duration, 3)
    size_bytes = $fileSize
    video_codec = $videoStream.codec_name
    audio_codec = $audioStream.codec_name
    resolution = "$($videoStream.width)x$($videoStream.height)"
    pixel_format = $videoStream.pix_fmt
    output = "submission-artifacts/Aeternus_OpenAI_Build_Week_Demo.mp4"
    validation = "submission-artifacts/VIDEO_VALIDATION.txt"
} | ConvertTo-Json)
