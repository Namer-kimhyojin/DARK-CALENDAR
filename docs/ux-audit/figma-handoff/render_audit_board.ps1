$ErrorActionPreference = 'Stop'

function Rgb([int]$r, [int]$g, [int]$b) {
    return $r + ($g * 256) + ($b * 65536)
}

function Add-Box($slide, [float]$x, [float]$y, [float]$w, [float]$h, [int]$fill, [int]$line, [float]$radius = 5) {
    $shape = $slide.Shapes.AddShape($radius, $x, $y, $w, $h)
    $shape.Fill.ForeColor.RGB = $fill
    $shape.Fill.Solid()
    $shape.Line.Visible = -1
    $shape.Line.ForeColor.RGB = $line
    $shape.Line.Weight = 1.25
    return $shape
}

function Add-Text($slide, [string]$value, [float]$x, [float]$y, [float]$w, [float]$h,
                  [float]$size, [int]$color, [bool]$bold = $false, [string]$font = 'Segoe UI',
                  [int]$align = 1) {
    $shape = $slide.Shapes.AddTextbox(1, $x, $y, $w, $h)
    $shape.TextFrame2.MarginLeft = 0
    $shape.TextFrame2.MarginRight = 0
    $shape.TextFrame2.MarginTop = 0
    $shape.TextFrame2.MarginBottom = 0
    $shape.TextFrame2.WordWrap = -1
    $shape.TextFrame2.TextRange.Text = $value
    $shape.TextFrame2.TextRange.Font.Name = $font
    $shape.TextFrame2.TextRange.Font.Size = $size
    $shape.TextFrame2.TextRange.Font.Bold = $(if ($bold) { -1 } else { 0 })
    $shape.TextFrame2.TextRange.Font.Fill.ForeColor.RGB = $color
    $shape.TextFrame2.TextRange.ParagraphFormat.Alignment = $align
    return $shape
}

function Add-PictureFit($slide, [string]$path, [float]$x, [float]$y, [float]$w, [float]$h) {
    $picture = $slide.Shapes.AddPicture($path, 0, -1, 0, 0, -1, -1)
    $ratio = [Math]::Min($w / $picture.Width, $h / $picture.Height)
    $picture.LockAspectRatio = -1
    $picture.Width = $picture.Width * $ratio
    $picture.Left = $x + (($w - $picture.Width) / 2)
    $picture.Top = $y + (($h - $picture.Height) / 2)
    return $picture
}

function Add-Pill($slide, [string]$value, [float]$x, [float]$y, [float]$w, [int]$fill, [int]$textColor) {
    Add-Box $slide $x $y $w 42 $fill $fill | Out-Null
    $label = Add-Text $slide $value $x ($y + 8) $w 26 17 $textColor $true 'Segoe UI' 2
    return $label
}

function Add-DecisionCard($slide, [string]$index, [string]$title, [string]$body,
                          [float]$x, [float]$y, [float]$w, [float]$h,
                          [int]$surface, [int]$stroke, [int]$primary, [int]$muted, [int]$accent) {
    Add-Box $slide $x $y $w $h $surface $stroke | Out-Null
    Add-Box $slide ($x + 18) ($y + 18) 48 48 $accent $accent | Out-Null
    Add-Text $slide $index ($x + 18) ($y + 27) 48 26 16 $primary $true 'Bahnschrift' 2 | Out-Null
    Add-Text $slide $title ($x + 82) ($y + 16) ($w - 102) 32 21 $primary $true 'Segoe UI' | Out-Null
    Add-Text $slide $body ($x + 82) ($y + 53) ($w - 102) ($h - 68) 16 $muted $false 'Segoe UI' | Out-Null
}

$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$handoff = $PSScriptRoot
$beforeDesktop = Join-Path $root 'docs\ux-audit\10-event-popup-enabled.png'
$beforeMobile = Join-Path $root 'docs\ux-audit\08-homepage-after-mobile.png'
$afterDesktop = Join-Path $handoff 'after-desktop.png'
$afterMobile = Join-Path $handoff 'after-mobile.png'
$afterBand = Join-Path $handoff 'after-event-band.png'
$output = Join-Path $handoff 'dark-calendar-homepage-ux-audit-board.png'

foreach ($source in @($beforeDesktop, $beforeMobile, $afterDesktop, $afterMobile, $afterBand)) {
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing source image: $source" }
}

$bg = Rgb 9 12 20
$surface = Rgb 18 23 35
$surface2 = Rgb 24 31 46
$stroke = Rgb 48 60 82
$primary = Rgb 243 246 252
$muted = Rgb 158 170 191
$accent = Rgb 104 92 255
$cyan = Rgb 62 207 232
$green = Rgb 80 211 145
$amber = Rgb 246 180 75
$red = Rgb 244 105 116

$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    $presentation = $ppt.Presentations.Add()
    $presentation.PageSetup.SlideWidth = 2880
    $presentation.PageSetup.SlideHeight = 1620
    $slide = $presentation.Slides.Add(1, 12)
    $slide.FollowMasterBackground = 0
    $slide.Background.Fill.ForeColor.RGB = $bg
    $slide.Background.Fill.Solid()

    # Header
    Add-Text $slide 'DARK CALENDAR' 60 44 500 46 29 $primary $true 'Bahnschrift SemiBold' | Out-Null
    Add-Text $slide 'HOMEPAGE UX AUDIT' 60 91 720 72 52 $primary $true 'Bahnschrift SemiBold' | Out-Null
    Add-Text $slide 'v3.6.0 / OPEN-SOURCE COMMUNICATION / 2026.07.18' 790 105 1000 42 20 $muted $false 'Segoe UI' | Out-Null
    Add-Pill $slide 'PUBLIC / LIVE' 2510 66 250 $green $bg | Out-Null
    Add-Text $slide 'GOAL: remove interruption / stabilize mobile navigation / clarify GPLv3' 790 145 1300 36 18 $cyan $false 'Segoe UI' | Out-Null

    $leftX = 60; $leftW = 700
    $centerX = 796; $centerW = 1160
    $rightX = 1992; $rightW = 828
    $topY = 215

    # BEFORE column
    Add-Pill $slide '01  BEFORE' $leftX $topY 190 $red $primary | Out-Null
    Add-Text $slide 'Entry-blocking event modal' $leftX ($topY + 58) $leftW 34 24 $primary $true 'Segoe UI' | Out-Null
    Add-Box $slide $leftX ($topY + 105) $leftW 405 $surface $stroke | Out-Null
    Add-Box $slide ($leftX + 20) ($topY + 125) ($leftW - 40) 315 (Rgb 235 238 244) $stroke | Out-Null
    Add-PictureFit $slide $beforeDesktop ($leftX + 28) ($topY + 133) ($leftW - 56) 299 | Out-Null
    Add-Text $slide 'ISSUE' ($leftX + 24) ($topY + 455) 70 28 17 $red $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Blocks the hero / forces dismissal / delays the primary CTA' ($leftX + 100) ($topY + 454) 560 30 17 $muted $false 'Segoe UI' | Out-Null

    Add-Text $slide 'Mobile information density' $leftX ($topY + 548) $leftW 34 24 $primary $true 'Segoe UI' | Out-Null
    Add-Box $slide $leftX ($topY + 595) $leftW 540 $surface $stroke | Out-Null
    Add-Box $slide ($leftX + 20) ($topY + 615) 270 490 (Rgb 235 238 244) $stroke | Out-Null
    Add-PictureFit $slide $beforeMobile ($leftX + 28) ($topY + 623) 254 474 | Out-Null
    Add-Text $slide 'Observed risks' ($leftX + 322) ($topY + 630) 330 34 20 $primary $true 'Segoe UI' | Out-Null
    Add-Text $slide "- Header navigation can wrap`n- Event competes with core content`n- License and pricing are separated`n- Pseudo-admin UI exposed in browser" ($leftX + 322) ($topY + 682) 330 200 18 $muted $false 'Segoe UI' | Out-Null
    Add-Box $slide ($leftX + 322) ($topY + 925) 330 145 $surface2 $stroke | Out-Null
    Add-Text $slide 'UX PRINCIPLE' ($leftX + 344) ($topY + 947) 280 30 18 $cyan $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Promotion stays visible in the flow without blocking the next action.' ($leftX + 344) ($topY + 986) 280 70 17 $primary $false 'Segoe UI' | Out-Null

    # AFTER column
    Add-Pill $slide '02  AFTER' $centerX $topY 190 $green $bg | Out-Null
    Add-Text $slide 'Current public homepage - desktop' $centerX ($topY + 58) $centerW 34 24 $primary $true 'Segoe UI' | Out-Null
    Add-Box $slide $centerX ($topY + 105) $centerW 690 $surface $stroke | Out-Null
    Add-Box $slide ($centerX + 20) ($topY + 125) ($centerW - 40) 560 (Rgb 235 238 244) $stroke | Out-Null
    Add-PictureFit $slide $afterDesktop ($centerX + 28) ($topY + 133) ($centerW - 56) 544 | Out-Null
    Add-Pill $slide 'NO MODAL' ($centerX + 35) ($topY + 705) 160 $green $bg | Out-Null
    Add-Text $slide 'Product value and download path are visible on first entry' ($centerX + 215) ($topY + 712) 850 28 17 $muted $false 'Segoe UI' | Out-Null

    Add-Text $slide 'Event promotion becomes an inline notice band' $centerX ($topY + 838) $centerW 34 24 $primary $true 'Segoe UI' | Out-Null
    Add-Box $slide $centerX ($topY + 885) $centerW 250 $surface $stroke | Out-Null
    Add-Box $slide ($centerX + 20) ($topY + 905) ($centerW - 40) 150 (Rgb 235 238 244) $stroke | Out-Null
    Add-PictureFit $slide $afterBand ($centerX + 28) ($topY + 913) ($centerW - 56) 134 | Out-Null
    Add-Text $slide 'Keeps the message, removes dismissal and interruption cost' ($centerX + 26) ($topY + 1076) 660 28 17 $cyan $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Repeatable inside the content flow' ($centerX + 700) ($topY + 1076) 400 28 17 $muted $false 'Segoe UI' 3 | Out-Null

    # MOBILE + decisions column
    Add-Pill $slide '03  MOBILE' $rightX $topY 210 $cyan $bg | Out-Null
    Add-Text $slide '390px live public viewport' $rightX ($topY + 58) $rightW 34 24 $primary $true 'Segoe UI' | Out-Null
    Add-Box $slide $rightX ($topY + 105) $rightW 690 $surface $stroke | Out-Null
    Add-Box $slide ($rightX + 22) ($topY + 125) 300 625 (Rgb 235 238 244) $stroke | Out-Null
    Add-PictureFit $slide $afterMobile ($rightX + 30) ($topY + 133) 284 609 | Out-Null
    Add-Text $slide 'Validation result' ($rightX + 355) ($topY + 140) 420 34 22 $primary $true 'Segoe UI' | Out-Null
    Add-Text $slide "OK  Single-row navigation`nOK  Stable CTA touch targets`nOK  Event does not block content`nOK  GPLv3 and paid distribution clarified`nOK  FAQ answers license questions" ($rightX + 355) ($topY + 196) 420 220 18 $muted $false 'Segoe UI' | Out-Null
    Add-Box $slide ($rightX + 355) ($topY + 454) 420 200 $surface2 $stroke | Out-Null
    Add-Text $slide 'FOLLOW-UP CHECKS' ($rightX + 379) ($topY + 478) 370 30 18 $amber $true 'Segoe UI' | Out-Null
    Add-Text $slide "- 320px regression test`n- Keyboard focus order`n- Download-link monitoring" ($rightX + 379) ($topY + 521) 370 110 17 $primary $false 'Segoe UI' | Out-Null

    Add-Text $slide 'Applied decisions' $rightX ($topY + 838) $rightW 34 24 $primary $true 'Segoe UI' | Out-Null
    $cardW = 396; $cardH = 118
    Add-DecisionCard $slide '01' 'Remove modal' 'Move event promotion into document flow' $rightX ($topY + 885) $cardW $cardH $surface $stroke $primary $muted $green
    Add-DecisionCard $slide '02' 'Mobile nav' 'Keep a compact single-row structure' ($rightX + 432) ($topY + 885) $cardW $cardH $surface $stroke $primary $muted $cyan
    Add-DecisionCard $slide '03' 'Clarify GPLv3' 'Explain open source and paid app together' $rightX ($topY + 1017) $cardW $cardH $surface $stroke $primary $muted $accent
    Add-DecisionCard $slide '04' 'Remove admin UI' 'Drop pseudo-security from public browser UI' ($rightX + 432) ($topY + 1017) $cardW $cardH $surface $stroke $primary $muted $amber

    # Bottom summary rail
    Add-Box $slide 60 1400 2760 150 $surface2 $stroke | Out-Null
    Add-Text $slide 'CHANGE FLOW' 88 1425 250 30 18 $cyan $true 'Bahnschrift SemiBold' | Out-Null
    Add-Text $slide 'Modal promotion' 365 1418 240 40 22 $primary $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide '>' 625 1416 70 44 30 $accent $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide 'Inline event band' 710 1418 280 40 22 $primary $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide '>' 1010 1416 70 44 30 $accent $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide 'Plain-language licensing' 1090 1418 380 40 22 $primary $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide '>' 1490 1416 70 44 30 $accent $true 'Segoe UI' 2 | Out-Null
    Add-Text $slide 'Trust-based download' 1570 1418 300 40 22 $primary $true 'Segoe UI' 2 | Out-Null
    Add-Pill $slide 'LIVE 200 OK' 2530 1422 230 $green $bg | Out-Null
    Add-Text $slide 'UI HEALTH' 88 1482 180 28 17 $muted $true 'Bahnschrift' | Out-Null
    Add-Text $slide 'Entry friction  DOWN' 365 1480 220 30 18 $green $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Mobile stability  UP' 650 1480 260 30 18 $green $true 'Segoe UI' | Out-Null
    Add-Text $slide 'License clarity  UP' 970 1480 290 30 18 $green $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Security confusion  DOWN' 1320 1480 360 30 18 $green $true 'Segoe UI' | Out-Null
    Add-Text $slide 'Dark Calendar / Homepage UX handoff board' 2180 1482 580 28 16 $muted $false 'Segoe UI' 3 | Out-Null

    $slide.Export($output, 'PNG', 3840, 2160)
}
finally {
    if ($presentation) { $presentation.Close() }
    if ($ppt) { $ppt.Quit() }
    if ($slide) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($slide) }
    if ($presentation) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) }
    if ($ppt) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

Write-Output $output
