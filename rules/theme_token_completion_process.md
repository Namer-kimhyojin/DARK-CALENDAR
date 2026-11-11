# Theme Token Completion Process

## Goal
Finish theme/UI-token rollout without reintroducing raw runtime style drift.

## Appearance Settings UX Contract

The appearance dialog exposes user goals first and implementation details second.

- Common settings use one continuous flow in the order Style → Accent → Readability → Font; users do not need to switch tabs to compare related choices.
- The live preview stays outside the settings scroll area. Wide screens use a side-by-side layout, while narrow screens place the preview above the scroll area.
- Style and Accent start expanded. Readability, Font, and background-detail controls start collapsed so the first viewport prioritizes common choices.
- Theme mode is explicit: System, Light, or Dark. System follows the operating-system appearance while preserving the selected style family.
- Style is selected from nine visual families. Each family owns one dark and one light preset.
- The active family uses both a check mark and color treatment, and arrow keys move between family choices.
- The complete preset catalog remains available through `Show all styles` for users who need it.
- Readability reports primary and secondary text contrast against the active background.
- Automatic contrast correction targets at least 4.5:1 for primary/secondary text and 3:1 for muted text.
- Accent and font controls remain independent so a style can be personalized without editing tokens.
- Raw dialog color and metric tokens are expert controls and stay collapsed by default.
- The footer reports the number of changed categories and disables Apply when the draft matches the opening state.

### Disclosure Pattern

Appearance sections use one reusable checkable-button pattern.

| Variant | Initial state | Use |
|---|---|---|
| Primary section | Expanded | Style and Accent choices used in most sessions |
| Supporting section | Collapsed | Readability and Font controls |
| Nested details | Collapsed | Complete preset catalog, custom background, and opacity controls |

- Collapsed and expanded states use both a directional marker and the button's checked state.
- Section toggles use strong keyboard focus and support Enter/Space through native button behavior.
- The initial focus lands on the active System/Light/Dark control and the settings scroll starts at the top.
- Family grids follow the actual editor width with three, two, or one compact columns; arrow-key movement follows the rendered column count. Family names appear once, with variant details in the accessible label and tooltip.
- Each section header exposes an icon-based revert action only when that section differs from the opening snapshot; reverting one section preserves changes in all others.
- The footer-level Revert All action restores Style, Accent, Readability, Font, and staged expert-token changes together, with at most one preview render.
- Reset boundaries follow the visible controls: Style includes background and opacity controls, while Readability owns the role-based text and input colors.

### Persistence Boundary

Appearance changes use a two-level draft model:

1. The advanced token editor stages color and metric overrides in the appearance dialog.
2. Cancelling the advanced editor preserves the previous appearance draft.
3. Cancelling the appearance dialog persists nothing.
4. Accepting the appearance dialog writes all appearance and token settings together, then refreshes the UI once.

This boundary prevents partially applied themes and keeps preview actions reversible.

### Runtime Performance Contract

- Rapid slider and text-color edits are coalesced into one preview refresh every 32 ms.
- A preset or automatic contrast correction updates all related color rows as one batch.
- Reapplying an identical preview state or stylesheet is a no-op.
- Theme-only sync status refreshes reuse the last issue count and do not query issue tables.
- Theme-triggered panel rendering does not notify data-only consumers such as unified widgets.

Reference offscreen measurements from July 2026:

| Interaction | Before | After |
|---|---:|---:|
| Preset switch, median | 145.85 ms | 27.30 ms |
| Changed preview, median | 17.40 ms | 12.10 ms |
| Unchanged preview, median | 17.40 ms | 0.002 ms |

These values are directional development measurements, not hard CI timing thresholds. Tests enforce
the batching, cache, and notification contracts by call count to avoid machine-dependent failures.

### Live System Appearance Contract

System appearance is resolved at runtime instead of rewriting the user's saved intent.

- `text_theme=auto` remains persisted as the user's mode choice. The current operating-system color scheme is converted to an effective `dark` or `light` value only while building UI tokens.
- A selected style family persists its dark/light base and accent pair. A system change switches to the paired family variant without changing the family selection.
- Explicit Light and Dark use the same family resolver as System. Menu and command-palette switches change only the requested mode; rendering never replaces saved base/accent colors.
- Direct background and accent choices have independent origins. A custom base must not be hidden by a family base, and choosing a custom base must not discard a family-linked accent. Accepting a newly selected style restores family base linkage.
- Family-linked accents and text colors follow the active family variant. User-customized accent and text colors remain unchanged across system changes.
- `QStyleHints.colorSchemeChanged` events are coalesced for 50 ms. A burst that settles on one mode causes at most one full theme application.
- Explicit Light or Dark mode does not restyle the application when the operating-system mode changes.
- An open appearance dialog in System mode receives the resolved mode immediately. The automatic variant switch does not count as a user edit and preserves custom draft values.
- Handling an operating-system appearance event performs no `QSettings` write. Persistence occurs only when the user accepts the appearance dialog or performs another explicit settings action.
- A runtime theme refresh redraws affected panels without notifying data-only consumers.


### Widget-Only Mode Readability Contract

The widget-only workspace inherits the main theme's identity (mode, base color, accent) but
floats over arbitrary wallpaper, so `widget_mode_theme.harden_widget_readability()` owns its
reading roles. Do not compare widget reading roles to main-window roles for equality.

- The shell keeps the main base RGB with at least `WIDGET_SHELL_MIN_ALPHA` (242) alpha. Main
  window opacity below that no longer shows wallpaper through the widget.
- Rows, buttons, the empty-state card and the selected chip use an opaque ladder derived from
  the base color (dark: toward white, light: toward ink); the selected chip and day tile use an
  accent tint so selection never depends on translucency.
- Text roles meet contrast floors against the shell over black and over white wallpaper:
  primary 7:1, secondary and button text 5.5:1, muted/faint, accent text and weekend labels
  4.5:1. Colors keep their hue and move toward white (dark) or ink (light) only as needed.
- Accent and input-border identity roles remain identical to the main theme.

## Scope Rules
- Typography and control sizing follow [the shared guide](../docs/design/typography-and-sizing.md). Use `shared.typography.get_typography_scale()` or shared `font_body`/`font_caption`/`font_section`/`font_title`/`font_display` tokens instead of screen-local sizes.
- `font_size` remains points. Legacy dialog `*_font_pt` metric values remain logical pixels for compatibility; never append `pt` to those values. Qt applies physical DPI scaling once.
- Metric defaults, editor bounds, reset and sparse persistence must use the same settings-aware resolver. A font change must not clamp an existing valid explicit size override or rewrite saved font preferences.
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
- App-owned modal tokens composite reading surfaces onto an opaque floating base,
  including explicit color overrides, so underlying window text cannot show through.
  This dialog contract preserves decorative main-window/widget opacity and the
  transparent outer corners of frameless cards.
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
