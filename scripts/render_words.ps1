# Shape and rasterize the non-Latin thank-yous with Windows' own text engine (handles Arabic joining
# and Devanagari conjuncts, which Pillow can't without Raqm). Output: white-on-black PNG masks + meta.json.
# Run words_list.py first; it writes analysis\words\words.json.
Add-Type -AssemblyName System.Drawing
# Project root: HELLO_WORLD_ROOT if set, otherwise the folder above scripts\.
$root = if ($env:HELLO_WORLD_ROOT) { $env:HELLO_WORLD_ROOT } else { Split-Path -Parent $PSScriptRoot }
$dir = Join-Path $root 'analysis\words'
$list = [System.IO.File]::ReadAllText("$dir\words.json", [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$px = 160
$meta = @()
$i = 0
foreach ($w in $list) {
    try { $fam = New-Object System.Drawing.FontFamily($w.family) } catch { $fam = New-Object System.Drawing.FontFamily('Segoe UI') }
    $style = [System.Drawing.FontStyle]::($w.style)
    if (-not $fam.IsStyleAvailable($style)) { $style = [System.Drawing.FontStyle]::Regular }
    $font = New-Object System.Drawing.Font($fam, $px, $style, [System.Drawing.GraphicsUnit]::Pixel)
    $fmt = [System.Drawing.StringFormat]::GenericTypographic
    $tmp = New-Object System.Drawing.Bitmap 10, 10
    $g0 = [System.Drawing.Graphics]::FromImage($tmp)
    $size = $g0.MeasureString($w.word, $font, 100000, $fmt)
    $g0.Dispose(); $tmp.Dispose()
    $pad = 40
    $bw = [int]([math]::Ceiling($size.Width)) + 2 * $pad
    $bh = [int]([math]::Ceiling($px * 1.6)) + 2 * $pad
    $bmp = New-Object System.Drawing.Bitmap $bw, $bh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::Black)
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $g.DrawString($w.word, $font, [System.Drawing.Brushes]::White, [single]$pad, [single]$pad, $fmt)
    $g.Dispose()
    $asc = $fam.GetCellAscent($style) / $fam.GetEmHeight($style) * $px
    $file = "w_$i.png"
    $bmp.Save("$dir\$file", [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    $meta += [pscustomobject]@{ word = $w.word; file = $file; px = $px; baseline = $pad + $asc; family = $fam.Name }
    $i++
}
$json = $meta | ConvertTo-Json
[System.IO.File]::WriteAllText("$dir\meta.json", $json, (New-Object System.Text.UTF8Encoding $false))
"RENDERED $i"
$meta | Format-Table word, family, baseline | Out-String
