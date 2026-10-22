# v2 full pipeline: bake the scene, render 16:9 + vertical plates on two Blender instances, then comp + encode
# the music video and the three Shorts. Keeps the PC awake throughout. Progress -> logs\v2render.log
$ErrorActionPreference = 'Continue'
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
# Blender 5.x: BLENDER if set, otherwise blender on PATH.
$bl = if ($env:BLENDER) { $env:BLENDER } else { (Get-Command blender -ErrorAction SilentlyContinue).Source }
if (-not $bl) { throw 'Blender not found: put blender on PATH or set $env:BLENDER to blender.exe' }
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = 'python' }
New-Item -ItemType Directory -Force "$root\logs" | Out-Null
$log = "$root\logs\v2render.log"
Add-Type -Name PowerV2 -Namespace Win32 -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.PowerV2]::SetThreadExecutionState([uint32]2147483649) | Out-Null
function Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Out-File $log -Append }
"v2render start $(Get-Date)" | Out-File $log
Remove-Item Env:COMP_PROJ -ErrorAction SilentlyContinue
Remove-Item Env:COMP_PLATES -ErrorAction SilentlyContinue

# 0. keep the v1 plates aside (archives an earlier run's plates, .blend and MP4s once; a no-op on a fresh checkout)
if ((Test-Path "$root\plates") -and -not (Test-Path "$root\plates_v1")) { Rename-Item "$root\plates" 'plates_v1'; Log 'v1 plates moved to plates_v1' }
New-Item -ItemType Directory -Force "$root\plates\169", "$root\plates\916" | Out-Null
if ((Test-Path "$root\hello_world.blend") -and -not (Test-Path "$root\hello_world_v1.blend")) { Copy-Item "$root\hello_world.blend" "$root\hello_world_v1.blend" }
New-Item -ItemType Directory -Force "$root\out\v1" | Out-Null
Get-ChildItem "$root\out" -Filter '*.mp4' | ForEach-Object { if (-not (Test-Path "$root\out\v1\$($_.Name)")) { Move-Item $_.FullName "$root\out\v1\" } }

# 1. bake the full scene
if ($args -notcontains 'skipbuild') {
    Log 'build start'
    & $bl -b --factory-startup -P "$PSScriptRoot\world.py" *> "$root\logs\v2build.log"
    if (-not (Select-String -Path "$root\logs\v2build.log" -Pattern 'WORLD_DONE' -Quiet)) { Log 'BUILD FAILED'; exit 1 }
    Log 'build done'
}

# 2. render: A = 16:9 front half, B = vertical ranges then 16:9 back half
$ex169 = "import bpy; s=bpy.context.scene; s.render.use_overwrite=False; s.render.use_placeholder=True"
$ex916 = "import bpy; s=bpy.context.scene; s.camera=bpy.data.objects['CamV']; s.render.resolution_x=1080; s.render.resolution_y=1920; s.render.use_overwrite=False; s.render.use_placeholder=True"
$blend = "`"$root\hello_world.blend`""
$o169 = "`"$root\plates\169\f_#####`""
$o916 = "`"$root\plates\916\f_#####`""
Log 'render start'
$A = Start-Process -FilePath $bl -ArgumentList '-b', $blend, '--python-expr', "`"$ex169`"", '-o', $o169, '-s', 220, '-e', 3950, '-a' `
     -RedirectStandardOutput "$root\logs\v2rA.log" -RedirectStandardError "$root\logs\v2rA.err" -WindowStyle Hidden -PassThru
$jobB = {
    param($bl, $blend, $ex916, $ex169, $o916, $o169, $root)
    & $bl -b $blend.Trim('"') --python-expr $ex916 -o $o916.Trim('"') -s 1342 -e 1993 -a *> "$root\logs\v2rB1.log"
    & $bl -b $blend.Trim('"') --python-expr $ex916 -o $o916.Trim('"') -s 3783 -e 5292 -a *> "$root\logs\v2rB2.log"
    & $bl -b $blend.Trim('"') --python-expr $ex169 -o $o169.Trim('"') -s 3951 -e 5571 -a *> "$root\logs\v2rB3.log"
}
$B = Start-Job -ScriptBlock $jobB -ArgumentList $bl, $blend, $ex916, $ex169, $o916, $o169, $root
while (-not $A.HasExited -or $B.State -eq 'Running') {
    Start-Sleep 60
    $n1 = (Get-ChildItem "$root\plates\169" -Filter 'f_*.exr' | Where-Object Length -gt 0).Count
    $n2 = (Get-ChildItem "$root\plates\916" -Filter 'f_*.exr' | Where-Object Length -gt 0).Count
    Log "progress 169=$n1/5352 916=$n2/2162"
}
Log 'render passes finished'

# 3. fill any gaps (crashed frames leave empty placeholders)
function Gaps($dir, $ranges) {
    $miss = @()
    foreach ($r in $ranges) { foreach ($f in $r[0]..$r[1]) {
        $p = '{0}\f_{1:D5}.exr' -f $dir, $f
        if (-not (Test-Path $p) -or (Get-Item $p).Length -eq 0) { $miss += $f } } }
    return $miss
}
foreach ($pass in 1..2) {
    $m169 = Gaps "$root\plates\169" @(,@(220, 5571))
    $m916 = Gaps "$root\plates\916" @(@(1342, 1993), @(3783, 5292))
    Log "gaps pass $pass : 169=$($m169.Count) 916=$($m916.Count)"
    if ($m169.Count -eq 0 -and $m916.Count -eq 0) { break }
    foreach ($f in $m169) { Remove-Item ('{0}\plates\169\f_{1:D5}.exr' -f $root, $f) -ErrorAction SilentlyContinue
        & $bl -b "$root\hello_world.blend" --python-expr $ex169 -o "$root\plates\169\f_#####" -f $f *> "$root\logs\v2gap.log" }
    foreach ($f in $m916) { Remove-Item ('{0}\plates\916\f_{1:D5}.exr' -f $root, $f) -ErrorAction SilentlyContinue
        & $bl -b "$root\hello_world.blend" --python-expr $ex916 -o "$root\plates\916\f_#####" -f $f *> "$root\logs\v2gap.log" }
}
Log 'PLATES DONE'

# 4. comp + encode
$env:COMP_WORKERS = '14'
& $py "$PSScriptRoot\comp.py" video *> "$root\logs\v2_video.log"
Log "VIDEO exit $LASTEXITCODE"
foreach ($s in 'SH1', 'SH2', 'SH3') {
    & $py "$PSScriptRoot\comp.py" short $s *> "$root\logs\v2_short_$s.log"
    Log "$s exit $LASTEXITCODE"
}
Log 'V2 ALL DONE'
Start-Sleep 1800   # stay awake another 30 minutes so the finished files can be checked before the PC sleeps
[Win32.PowerV2]::SetThreadExecutionState([uint32]2147483648) | Out-Null
