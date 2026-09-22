# ocr_words.ps1 —— 用 Windows.Media.Ocr 出「词 + 坐标」词表
#   powershell -ExecutionPolicy Bypass -File ocr_words.ps1 原图.png > words.txt
# 输出：x<TAB>y<TAB>w<TAB>h<TAB>text   （坐标为 **2 倍图** 坐标）
#
# 为什么要 2 倍图：位图里的标签只有 15~20px 高，直接 OCR 会把 Quark-Gluon
# 认成 Quark-GIuon、Plasma 认成 PIasma。放大 2 倍再 OCR 错字率明显下降，
# 剩下的错字用 labels.py 的 FIX 表修。
param([Parameter(Mandatory=$true)][string]$Image, [string]$Lang = 'zh-Hans-CN')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                   $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) {
    $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(); $task.Result
}
# 1) 放大 2 倍（用 .NET，免得依赖 ImageMagick）
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile((Resolve-Path $Image).Path)
$big = New-Object System.Drawing.Bitmap($src.Width * 2, $src.Height * 2)
$g = [System.Drawing.Graphics]::FromImage($big)
$g.InterpolationMode = 'HighQualityBicubic'
$g.DrawImage($src, 0, 0, $big.Width, $big.Height)
$tmp = [IO.Path]::Combine($env:TEMP, ("ocr2x_" + [IO.Path]::GetFileNameWithoutExtension($Image) + ".png"))
$big.Save($tmp, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $big.Dispose(); $src.Dispose()
Write-Verbose "2x 图: $tmp"

# 2) OCR
$eng = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$lng = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]
$e = $eng::TryCreateFromLanguage((New-Object $lng $Lang))
if (-not $e) { $e = $eng::TryCreateFromUserProfileLanguages() }
if (-not $e) { throw "没有可用的 OCR 语言包（设置 → 时间和语言 → 语言 → 添加中文/英文）" }
$sf = Await ([Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]::GetFileFromPathAsync($tmp)) ([Windows.Storage.StorageFile])
$stream = Await ($sf.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res = Await ($e.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
foreach ($ln in $res.Lines) {
    foreach ($w in $ln.Words) {
        $r = $w.BoundingRect
        Write-Output ("{0:F1}`t{1:F1}`t{2:F1}`t{3:F1}`t{4}" -f $r.X, $r.Y, $r.Width, $r.Height, $w.Text)
    }
}
