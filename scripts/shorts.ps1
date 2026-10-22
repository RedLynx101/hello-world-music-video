param([int]$workers = 4)
# Comp + encode the three vertical Shorts from existing plates.
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\shorts.log"
Add-Type -Name Power2 -Namespace Win32 -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power2]::SetThreadExecutionState([uint32]2147483649) | Out-Null
$env:COMP_WORKERS = "$workers"
"shorts start $(Get-Date) workers=$workers" | Out-File $log
foreach ($s in 'SH1', 'SH2', 'SH3') {
    & $py "$PSScriptRoot\comp.py" short $s *> "$root\logs\short_$s.log"
    "$s exit $LASTEXITCODE $(Get-Date)" | Out-File $log -Append
}
"SHORTS DONE $(Get-Date)" | Out-File $log -Append
[Win32.Power2]::SetThreadExecutionState([uint32]2147483648) | Out-Null
