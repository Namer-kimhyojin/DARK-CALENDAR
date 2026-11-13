# Animated date postcards

Six original AI-generated illustration sequences created for Air Calendar:

| GIF | Scene |
| --- | --- |
| sakura.gif | Cherry blossoms and drifting petals |
| ocean.gif | Ocean waves and a sailboat |
| moon.gif | A sleeping fox on the moon with twinkling stars |
| forest.gif | A woodland cottage and fireflies |
| coffee.gif | Morning coffee with curling steam |
| cat.gif | A sleeping kitten on lavender clouds |

Artwork: OpenAI image generation, 2026-11-11. No third-party downloaded artwork.
Original 4-by-4 animation sheets are retained in the local QA folder
`artifacts/date-animations/sources/`. Re-encode with
`powershell -File scripts/encode_date_animations.ps1` (requires FFmpeg).

Each GIF loops indefinitely at 320 x 320 pixels. Air Calendar paints the current
date separately, so the artwork never contains a baked-in date. The native
player decodes frames without caching the full animation and pauses when hidden,
disabled, or blocked by the widget workspace/Windows motion policy.
