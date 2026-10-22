# Creates .venv (Python 3.12, sharing the system site-packages, where torch, numpy, OpenCV and Pillow live) and
# installs the audio-analysis packages. Output goes to logs\setup.log.
$ErrorActionPreference = 'Continue'
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
New-Item -ItemType Directory -Force (Join-Path $root 'logs') | Out-Null
$log = Join-Path $root 'logs\setup.log'
"start $(Get-Date)" | Out-File $log
py -3.12 -m venv --system-site-packages (Join-Path $root '.venv') *>> $log
$py = Join-Path $root '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip *>> $log
& $py -m pip install --no-deps stable-ts openai-whisper demucs *>> $log
& $py -m pip install numba tiktoken more-itertools julius lameenc openunmix dora-search soundfile librosa *>> $log
& $py -c "import stable_whisper, demucs, librosa, torch; print('IMPORT_OK', torch.cuda.is_available())" *>> $log
"done $(Get-Date)" | Out-File $log -Append
