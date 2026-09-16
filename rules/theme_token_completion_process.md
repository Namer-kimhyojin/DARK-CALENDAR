# Theme Token Completion Process

## Goal
Finish theme/UI-token rollout without reintroducing raw runtime style drift.

## Scope Rules
- Runtime shell/style code must prefer shared semantic tokens and dialog metrics.
- Inline raw color/QSS is allowed only for:
  - token/template fixture data that intentionally encodes preset visuals
  - compatibility notes that describe explicit hex color support generically
  - parser/transform compatibility code that converts legacy values

## Light Mode Semantic Contract

- Appearance mode defines luminance and contrast. Style families define hue only.
- Light surfaces use a visible neutral hierarchy: shell, toolbar, item, hover, and input
  must not differ only by alpha because alpha-only layers collapse at full opacity and
  become unpredictable over desktop wallpaper.
- Light-mode text, borders, scrollbars, and neutral icons use dark semantic roles.
  Dark-mode roles use their light counterparts. Do not hardcode white translucent
  borders or handles in shared runtime styles.
- Navigation and action icons are rebuilt when the appearance mode changes. Active,
  warning, and danger icons use their semantic role colors.
- Calendar icons preserve the calendar identity color. If that color is below 3:1
  contrast against the active surface, adjust its lightness while preserving its hue.
  Calendar labels continue to use the normal text role rather than inheriting the
  identity color.
- A custom input background belongs only to the custom text theme. Light, dark, and
  system modes derive their input surface from the current mode so a stale dark input
  cannot leak into light mode.
- User opacity controls the decorative shell. Calendar and panel reading surfaces use
  `content_bg` with a minimum alpha, while tooltips and modal cards use `floating_bg`
  with a stronger minimum alpha so wallpaper never determines text contrast.
- Light-mode reading text uses opaque neutral roles. Do not use alpha-black for labels,
  task titles, empty-state instructions, or other text that users must read.
- Calendar task chips use neutral mode-aware text and a tinted identity-color surface.
  Calendar identity remains on the leading strip; task titles must not be fixed white.

## Stage 1. Baseline
- Identify hotspot files.
- Separate `runtime style code` from `preset/template data`.
- Record current hotspot counts in guard tests.

Exit criteria:
- hotspot files are listed in tests
- known exceptions are documented

## Stage 2. Runtime Tokenization
- Replace live `setStyleSheet(...)` raw literals with helper/bundle functions.
- Move menu/button/card/input styles to semantic token builders.
- Use dialog metric tokens for radius, padding, and sizing where possible.

Exit criteria:
- runtime shell paths use helper functions
- new UI work does not introduce direct raw style strings in hotspot files

## Stage 3. Long-tail Cleanup
- Clean remaining inline styles in helper-heavy files such as `overlay_base.py`.
- Normalize small style fragments:
  - hint links
  - preview card padding
  - quick-insert/group labels
  - color-picker buttons

Exit criteria:
- residual inline styles are helper-backed or explicitly exempted

## Stage 4. Guardrails
- Add tests that fail when hotspot counts increase unexpectedly.
- Add tests that fail when known legacy snippets reappear.
- Keep runtime helper entry points covered by contract tests.

Exit criteria:
- guard tests exist for hotspot files
- helper contract tests cover runtime style bundles

## Stage 5. Verification
- Run targeted UI-token regression tests.
- Run full `pytest`.
- Manually check major dialogs/widgets for dark/light/custom themes when needed.
- For light-mode menu changes, verify dynamically rebuilt submenus and theme-switched
  icons in addition to the root menu.

Exit criteria:
- targeted regressions pass
- full `pytest` passes

## Current Exceptions
- Built-in preset/template examples should prefer semantic aliases such as `color=muted`, `color=accent`, and `color=warning`.
- Raw hex examples should be limited to backward-compatibility paths for user-authored templates and should not remain in built-in docs or preset examples.
- Literal `rgba(...)` values in `overlay_base.py` are allowed only inside preset/style fallback parameter tables such as `accent_bg_color`, `accent_border_color`, and `accent_text_color`.
- `_DLG_SS` in `overlay_base.py` may keep literal color placeholders because `_apply_widget_dialog_tokens()` rewrites them to live theme values at runtime.
