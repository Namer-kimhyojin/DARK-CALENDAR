# Theme Token Completion Process

## Goal
Finish theme/UI-token rollout without reintroducing raw runtime style drift.

## Scope Rules
- Runtime shell/style code must prefer shared semantic tokens and dialog metrics.
- Inline raw color/QSS is allowed only for:
  - token/template fixture data that intentionally encodes preset visuals
  - compatibility notes that describe explicit hex color support generically
  - parser/transform compatibility code that converts legacy values

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

Exit criteria:
- targeted regressions pass
- full `pytest` passes

## Current Exceptions
- Built-in preset/template examples should prefer semantic aliases such as `color=muted`, `color=accent`, and `color=warning`.
- Raw hex examples should be limited to backward-compatibility paths for user-authored templates and should not remain in built-in docs or preset examples.
- Literal `rgba(...)` values in `overlay_base.py` are allowed only inside preset/style fallback parameter tables such as `accent_bg_color`, `accent_border_color`, and `accent_text_color`.
- `_DLG_SS` in `overlay_base.py` may keep literal color placeholders because `_apply_widget_dialog_tokens()` rewrites them to live theme values at runtime.
