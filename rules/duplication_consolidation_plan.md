# Duplication Consolidation Plan

## Goal
- Reduce duplicated logic without shrinking features or changing user-visible behavior.
- Prefer consolidation behind existing call paths so runtime behavior stays stable.
- Require targeted tests and full-suite verification after each consolidation step.

## Safety Rules
- Do not collapse logic when two paths only look similar but carry different side effects.
- Move shared calculations into helpers first, then switch callers one by one.
- Keep existing public function signatures unless tests or callers are updated in the same change.
- Treat behavioral drift as a regression, even if the code becomes shorter.

## Implemented In This Pass
### 1. Startup phase execution unified
- File: `calendar_app/bootstrap.py`
- Previous state:
  - Weighted phase ranges, phase texts, threaded/non-threaded behavior, and actual execution were spread across repeated calls and separate per-phase handling.
- Consolidation:
  - Declared startup phases once in `_STARTUP_PHASE_SPECS`.
  - Derived weighted ranges once through `_build_startup_phase_ranges()`.
  - Centralized phase creep/completion in the bootstrap orchestrator.
  - Simplified `SplashScreen` into a passive progress view instead of a second phase state machine.
- Result:
  - Startup progress weighting and execution order now come from one source of truth.
  - No feature was removed; the splash still reflects the same startup stages.

### 1-1. Google primary summary fallback unified
- File: `calendar_app/infrastructure/google_sync/common.py`
- Previous state:
  - The `"primary"` display-name fallback was repeated in both `build_calendar_source_summary_map()` and `resolve_calendar_source_summary()`.
- Consolidation:
  - Extracted one shared private helper for the fallback summary rule.
- Result:
  - The fallback rule now lives in one place, reducing drift risk without changing behavior.

## Verified In This Pass
- `tests/test_splash_screen.py`
- `tests/test_app_metadata.py`
- Full `pytest`

## Next Safe Candidates
### 2. Calendar writability/read-only rule convergence
- Files:
  - `calendar_app/infrastructure/db/calendar_repo.py`
  - `calendar_app/infrastructure/google_sync/engine.py`
  - `calendar_app/infrastructure/task_drop_service.py`
- Why duplicated:
  - Multiple paths reason about writable vs read-only calendars with overlapping but not identical criteria.
- Safe consolidation direction:
  - Keep `calendar_repo.is_calendar_row_read_only()` as the canonical predicate.
  - Route higher-level writable filtering through that predicate, after adding tests for active/inactive GCal, ICS, and access-role cases.

### 3. Google calendar identity normalization and summary resolution
- Files:
  - `calendar_app/infrastructure/google_sync/common.py`
  - `calendar_app/infrastructure/google_sync/helpers.py`
  - `calendar_app/infrastructure/google_sync/engine.py`
  - `calendar_app/infrastructure/google_sync/service.py`
- Why duplicated:
  - Calendar id normalization and fallback summary lookup are centralized partially, but higher-level orchestration still repeats candidate building and default handling patterns.
- Safe consolidation direction:
  - Extract one small shared helper at a time, starting with calendar-id fallback resolution.
  - Preserve existing public entrypoints and migrate callers incrementally.

### 4. Dialog/theme helper bundling overlap
- Files:
  - `calendar_app/presentation/dialogs/*`
  - `calendar_app/presentation/theme/*`
- Why duplicated:
  - Multiple dialog bundles build similar button, section, and shell styles with small per-dialog variations.
- Safe consolidation direction:
  - Consolidate repeated builder fragments only where token inputs and objectName contracts are already identical.
  - Leave dialog-specific layout and copy untouched.

## Recommended Order
1. Calendar read-only/writable rule convergence
2. Google sync calendar-id fallback consolidation
3. Dialog/theme helper fragment extraction

## Exit Criteria
- No feature loss
- Targeted regression tests added for each consolidation
- Full test suite passes after every step
