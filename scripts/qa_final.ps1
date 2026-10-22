# QA for finished MP4s in out\: probe each file, pull six frames across it and tile them into a contact sheet.
param([string]$which = 'all')
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
# ffmpeg / ffprobe: FFMPEG / FFPROBE if set, otherwise the ones on PATH.
$ffmpeg = if ($env:FFMPEG) { $env:FFMPEG } else { (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source }
$ffprobe = if ($env:FFPROBE) { $env:FFPROBE } else { (Get-Command ffprobe -ErrorAction SilentlyContinue).Source }
if (-not $ffmpeg -or -not $ffprobe) { throw 'ffmpeg/ffprobe not found: put them on PATH or set $env:FFMPEG and $env:FFPROBE' }
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
$dst = "$root\analysis\final"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Get-ChildItem "$root\out" -Filter *.mp4 | Where-Object { $which -eq 'all' -or $_.Name -like "*$which*" } | ForEach-Object {
    $f = $_.FullName
    $info = & $ffprobe -v error -show_entries format=duration,bit_rate:stream=codec_name,width,height,r_frame_rate,sample_rate,channels -of compact $f
    "== $($_.Name)  ($([math]::Round($_.Length/1MB,1)) MB)"
    $info
    $tag = ($_.BaseName -replace '[^A-Za-z0-9]', '')
    $dur = [double](& $ffprobe -v error -show_entries format=duration -of csv=p=0 $f)
    $times = @(0.15, 0.3, 0.45, 0.6, 0.75, 0.9) | ForEach-Object { [math]::Round($dur * $_, 2) }
    $outs = @()
    foreach ($t in $times) {
        $o = "$dst\$tag`_$t.jpg"
        & $ffmpeg -v error -y -ss $t -i $f -frames:v 1 -q:v 3 $o
        $outs += $o
    }
    & $py "$PSScriptRoot\sheet.py" "$dst\sheet_$tag.jpg" 480 @outs
}
