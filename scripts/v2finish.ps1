# Re-encode Short 3 (wrapped echo line) and make a 720p phone preview of the music video.
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
# ffmpeg: FFMPEG if set, otherwise the one on PATH.
$ff = if ($env:FFMPEG) { $env:FFMPEG } else { (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source }
if (-not $ff) { throw 'ffmpeg not found: put it on PATH or set $env:FFMPEG' }
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\v2finish.log"
Add-Type -Name PowerF -Namespace Win32 -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.PowerF]::SetThreadExecutionState([uint32]2147483649) | Out-Null
"finish start $(Get-Date)" | Out-File $log
$env:COMP_WORKERS = '14'
& $py "$PSScriptRoot\comp.py" short SH3 *> "$root\logs\v2_short_SH3b.log"
"SH3 exit $LASTEXITCODE $(Get-Date)" | Out-File $log -Append
& $ff -y -v error -i "$root\out\Hello World - Music Video (1080p master).mp4" -vf scale=1280:720:flags=lanczos -c:v libx264 -preset medium -crf 25 -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart "$root\out\Hello World - Music Video (720p preview).mp4" *> "$root\logs\v2_preview.log"
"PREVIEW exit $LASTEXITCODE $(Get-Date)" | Out-File $log -Append
"FINISH DONE $(Get-Date)" | Out-File $log -Append
Start-Sleep 900
[Win32.PowerF]::SetThreadExecutionState([uint32]2147483648) | Out-Null
