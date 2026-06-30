# Panel Widget Mode Split Plan

## Goal
- Reduce the maintenance and regression risk of `calendar_app/presentation/widgets/panel_widget_mode.py`.
- Keep external behavior and internal symbol names stable during the first split.
- Preserve the current widget-mode feature set while preparing later splits for renderer and repository layers.

## Current Problems
- One file mixes data formatting, theme/token logic, floating-shell behavior, calendar painting, list/card rendering, and controller orchestration.
- UI changes force retesting nearly the whole widget stack because responsibilities are tangled.
- Several helpers are already reused outside the file, but their ownership is not clear.
- There is legacy code in the controller that is easy to break while touching UI classes.

## First-Phase Target Structure

### `panel_widget_common.py`
- Pure helpers and shared value objects.
- Owns:
  - `_WidgetEntry`
  - text/date parsing helpers
  - locale/date formatting helpers
  - priority/status helpers
  - layout reference constants
  - `_parse_quick_add_text`

### `panel_widget_theme.py`
- Theme token and widget color-mode helpers.
- Owns:
  - widget color-mode constants
  - token resolution and background opacity helpers
  - stylesheet/palette wrapper functions used by widget UI classes

### `panel_widget_shell.py`
- Floating widget shell and launcher behavior.
- Owns:
  - `_FloatingWidgetBase`
  - `_WidgetModeLauncher`
- Also absorbs the old monkey-patched floating helper methods into the class itself.

### `panel_widget_views.py`
- Widget-specific UI classes built on top of shared helpers and shell behavior.
- Owns:
  - `_WidgetCalendar`
  - `_EntryListWidget`
  - `_QuickAddInput`
  - `_PanelWidget`

### `panel_widget_mode.py`
- Controller-focused compatibility module.
- Owns:
  - `PanelWidgetModeController`
- Re-exports moved symbols so current imports and tests keep working.

## Compatibility Rules
- Keep the existing public import surface of `panel_widget_mode.py` intact for internal callers and tests.
- Avoid renaming moved classes/functions in phase 1.
- Keep controller logic in place for now so cache behavior and widget lifecycle stay stable.

## Known Safety Adjustments Included In Phase 1
- Remove the undefined `_ScheduleWidget` branch from floating-shell sibling lookup and make it safe for the current single-panel architecture.
- Explicitly initialize controller refresh-worker state that was previously only created lazily.
- Add missing legacy imports used by the fallback async code path so the refactor does not preserve hidden runtime errors.

## Validation Plan
1. Run `py_compile` against the split widget modules.
2. Run focused widget and query tests:
   - `tests/test_panel_widget_mode_ui.py`
   - `tests/test_unified_widget_mode.py`
   - `tests/test_db_query_optimizations.py`
3. If a regression appears, fix it before moving to the next split phase.

## Next Phases
1. Trim or delete the unused legacy async DB path from the controller once the cache-only path is verified stable.
2. Apply the same split pattern to `side_panel_renderer.py`.
3. Split dialog and repository layers after the widget presentation layer is stable.
