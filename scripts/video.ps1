param([int]$workers = 8)
# Comp + encode the full 16:9 music video (1080p master + 1440p upload) from existing plates.
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\video.log"
Add-Type -Name Power3 -Namespace Win32 -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power3]::SetThreadExecutionState([uint32]2147483649) | Out-Null
$env:COMP_WORKERS = "$workers"
"video start $(Get-Date) workers=$workers" | Out-File $log
& $py "$PSScriptRoot\comp.py" video *> "$root\logs\video_comp.log"
"VIDEO DONE exit $LASTEXITCODE $(Get-Date)" | Out-File $log -Append
[Win32.Power3]::SetThreadExecutionState([uint32]2147483648) | Out-Null
