param(
    [string]$SourceDirectory = "artifacts/weather-animations/sources",
    [string]$OutputDirectory = "Assets/weather/animations"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$sheets = [ordered]@{
    sky = @("clear_day", "clear_night", "partly_cloudy_day", "partly_cloudy_night")
    rain = @("cloudy", "fog", "drizzle", "rain")
    winter = @("heavy_rain", "snow", "heavy_snow", "thunderstorm")
    hail = @("hail")
}

foreach ($sheet in $sheets.GetEnumerator()) {
    $source = Join-Path $SourceDirectory ($sheet.Key + ".png")
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing weather animation sheet: $source"
    }
    for ($row = 0; $row -lt $sheet.Value.Count; $row++) {
        $condition = $sheet.Value[$row]
        $destination = Join-Path $OutputDirectory "$condition.gif"
        $tileRow = "$row"
        $duration = "1.333333"
        if ($condition -eq "hail") {
            $tileRow = "floor(n/4)"
            $duration = "5.333333"
        }
        # Normalize the grid and trim tile edges before smoothing the frame transitions.
        $crop = 'scale=1280:1280:flags=lanczos,crop=iw/4:ih/4:mod(n\,4)*out_w:' + $tileRow + '*out_h,crop=iw-4:ih-4:2:2'
        $filter = $crop + ',scale=256:256:flags=lanczos,framerate=fps=9:interp_start=0:interp_end=255:scene=100,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=3'
        & ffmpeg -v error -y -loop 1 -framerate 3 -t $duration -i $source -filter_complex $filter -loop 0 $destination
        if ($LASTEXITCODE -ne 0) { throw "GIF encoding failed: $condition" }
    }
}
