param(
    [string]$SourceDirectory = "artifacts/date-animations/sources",
    [string]$OutputDirectory = "Assets/date_animations"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
# Generated sheets contain 4 x 4 full-bleed frames. Normalize cell boundaries,
# trim the outer two pixels, interpolate softly, and share a bounded GIF palette.
$filter = 'scale=1280:1280:flags=lanczos,crop=iw/4:ih/4:mod(n\,4)*out_w:floor(n/4)*out_h,crop=iw-4:ih-4:2:2,scale=320:320:flags=lanczos,framerate=fps=8:interp_start=0:interp_end=255:scene=100,split[a][b];[a]palettegen=max_colors=96:stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=3'
foreach ($animation in @("sakura", "ocean", "moon", "forest", "coffee", "cat")) {
    $source = Join-Path $SourceDirectory "$animation.png"
    $destination = Join-Path $OutputDirectory "$animation.gif"
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing animation sheet: $source"
    }
    & ffmpeg -v error -y -loop 1 -framerate 4 -t 4 -i $source -filter_complex $filter -loop 0 $destination
    if ($LASTEXITCODE -ne 0) { throw "GIF encoding failed: $animation" }
}
