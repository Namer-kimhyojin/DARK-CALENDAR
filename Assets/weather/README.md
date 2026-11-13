# Air Calendar weather illustration packs

The three sprite sheets in this directory were generated as original project assets with the
built-in OpenAI image generation tool on 2026-09-19.

Each transparent sheet uses a 4 x 4 grid in this row-major order:

1. clear day
2. clear night
3. partly cloudy day
4. partly cloudy night
5. cloudy
6. fog
7. drizzle
8. rain
9. heavy rain
10. snow
11. heavy snow
12. thunderstorm
13. hail
14. unknown
15. empty
16. empty

Source prompts required a transparent background, no text, no logos, no watermark, consistent
scale, and readable silhouettes. The authored visual styles are soft 3D clay, layered paper cut,
and crisp minimal duotone.

The `animations/` directory contains 13 original looping coastal lighthouse GIFs for the
Animated Weather design. Generated with OpenAI image generation on 2026-11-11, they cover
all of the authored conditions above except `unknown`, which uses the regular fallback art.
The 4 x 4 source sheets are retained in `artifacts/weather-animations/sources/` and can be
encoded with `scripts/encode_weather_animations.ps1` (FFmpeg).
