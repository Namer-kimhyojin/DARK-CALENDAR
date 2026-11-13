param(
    [string]$SourceDirectory = "artifacts/flipbook-stickers/sources",
    [string]$OutputDirectory = "Assets/flipbook"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$thresholds = [ordered]@{ blossom = 128; aurora = 128; starlight = 192 }
foreach ($sticker in $thresholds.Keys) {
    $source = Join-Path $SourceDirectory "$sticker.png"
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing transparent sprite sheet: $source"
    }
    $threshold = $thresholds[$sticker]
    $filter = 'format=rgba,scale=1280:1280:flags=lanczos,crop=320:320:mod(n\,4)*320:floor(n/4)*320,scale=144:144:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:reserve_transparent=1[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:alpha_threshold=' + $threshold
    $destination = Join-Path $OutputDirectory "$sticker.gif"
    & ffmpeg -v error -y -loop 1 -framerate 24 -t 0.666667 -i $source -filter_complex $filter -gifflags 0 -loop 0 $destination
    if ($LASTEXITCODE -ne 0) { throw "GIF encoding failed: $sticker" }
}
