# Air Calendar Design QA

> 문서 역할: 설계·감사 기록입니다. 당시 진단과 검증 결과는 현재 상태를 보장하지 않습니다. 현재 진행 상태는 TASKS.md, 구현 규칙은 rules/를 우선 확인합니다.

## 최신 공통 UI 검증 — 2026-11-06

[공통 UI 후속 개선·검증 기록](docs/ux-audit/unified-ui-followup-20261106.md)에 글자 계층·24pt 모양 설정, palette·외곽 그림자, 제목 입력 경고, 중첩 모달 owner, 시간 입력 간격, 요일 4모드, 위젯 테마·종일 문구의 최신 근거를 모았다. [글자·크기 가이드](docs/design/typography-and-sizing.md)를 공통 기준으로 사용한다.

채택한 native 모달 증거는 light100 32상태와 navy125 31상태다. 큰 글자 24pt·125% 7상태, 중첩 모달 100%·125% 각 10개 check, 최신 light/navy 위젯의 실제 진입·복귀를 별도 확인했다. `.show()` fixture 실패, mixed-DPI 위젯 배치 실패, 외부 창에 가린 피드백 캡처는 완료 결과에 합치지 않는다. 후속 표에서 확인 완료와 재촬영 예정 경로를 구분한다.

[루프덱 · 4트랙 안내](docs/ux-audit/keydeck-loopdeck-20261106.md)는 별도 기능 기록이다. 최신 루프 UI 재배치의 native 검토와 오디오 청취 결과는 해당 기능의 근거로 추가하며, 아래의 과거 `passed` 기록으로 대체하지 않는다.

## Daily Summary Modal Design QA — 이전 기록


## Evidence

- Source visual truth: `C:\Users\aplus\.codex\generated_images\01a0b20e-a96f-7ed0-8705-9849af24e6fe\exec-e8c46a02-d5f7-408c-a583-737baba5ee15.png`
- Source pixels: 1456 x 1080.
- Implemented expanded state: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-settings-expanded-final2.png`
- Implementation pixels / CSS window size: 960 x 501 at device pixel ratio 1.0.
- Implemented compact state: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-compact-final2.png` (560 x 500).
- Implemented narrow-screen layer state: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-settings-layer-final2.png` (560 x 501).
- Dark-theme state: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-settings-dark-final.png` (960 x 501).
- Full-view comparison: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-comparison-final.png`.
- Focused settings comparison: `C:\Users\aplus\.codex\visualizations\2026\09\18\01a0b20e-a96f-7ed0-8705-9849af24e6fe\daily-summary-settings-focus-comparison.png`.
- State: light theme, one all-day schedule, zero due tasks, settings open, both visibility modes set to content-aware, startup and daily display enabled, reminder time 09:00.
- Density normalization: the source was resized to 960 x 712 while preserving aspect ratio; the implementation remained at native 960 x 501. The height difference is intentional because the selected direction also incorporates the user's compact first reference and must remain a quick desktop briefing rather than a tall settings page.

## Full-view Comparison

The implementation preserves the selected split structure, removes the Windows title bar, and uses one rounded modal surface with a summary pane and an integrated settings pane. Header hierarchy, counters, content-aware visibility controls, reminder controls, footer actions, and the blue/neutral palette are visibly aligned with the source. The implementation is denser vertically than the generated source but remains unclipped and closer to the original compact popup requested by the user.

## Focused Region Comparison

The focused settings comparison verifies readable Korean typography, equal-width segmented choices, selected-state contrast, switch thumbs, the 09:00 time control, weekend exclusion, and cancel/save action hierarchy. Native `QTimeEdit` stepper arrows differ slightly from the generated visual but remain a standard Windows affordance and do not reduce clarity.

## Required Fidelity Surfaces

- Fonts and typography: Malgun Gothic with Segoe UI fallback renders Korean cleanly. Title, section labels, helper text, counts, and button weights maintain the source hierarchy without clipping or unexpected wrapping.
- Spacing and layout rhythm: 26 px summary and 28 px settings insets, compact section spacing, 10-14 px radii, and aligned footers create a consistent rhythm. The expanded 960 px layout and 560 px layer layout both retain persistent actions.
- Colors and visual tokens: the active theme supplies surface, text, border, and accent colors. Light mode matches the pale blue source treatment, while a separate dark-theme capture confirms readable tokens and icon colors.
- Image and asset fidelity: the screen contains no photographic or illustrative assets. Standard UI icons use the project's qtawesome icon library; no emoji, placeholder imagery, inline SVG, or raster approximation is used.
- Copy and content: the briefing title, date, schedule, empty due-task message, visibility labels, reminder controls, and actions match the approved Korean content and behavior.

## Findings

- No actionable P0, P1, or P2 mismatch remains.
- [P3] The native Windows time-stepper arrows are visually sharper and denser than the generated mockup. This is acceptable because they preserve platform familiarity and keyboard operation.
- [P3] The implemented modal is shorter than the generated mockup. This is intentional and follows the compact first reference; all content and persistent actions remain visible.

## Comparison History

1. Initial rendered pass: `daily-summary-settings-open-windows.png`.
   - P2: enabled switches appeared as solid blue pills without a visible thumb, weakening the on/off affordance.
   - P2: schedule and empty-state rows were nearly white, losing the source's pale-blue grouping.
2. Fixes applied:
   - Added a keyboard-accessible native PyQt switch control with an explicit white thumb and focus ring.
   - Applied the accent-soft theme token to summary rows and count chips.
   - Normalized rgba theme colors to hex before passing them to qtawesome so dark-theme icons remain legible.
   - Recomputed layout constraints before narrow-mode resizing so the settings layer remains 560 px wide.
3. Post-fix evidence: `daily-summary-settings-expanded-final2.png`, `daily-summary-settings-layer-final2.png`, and `daily-summary-settings-dark-final.png`.
   - No P0, P1, or P2 finding remains.

## Interactions Verified

- Open settings from the compact briefing.
- Expand to the right on a wide screen.
- Replace the briefing with a same-window settings layer on a narrow screen.
- Save schedule and due-task visibility modes.
- Save startup display, daily reminder, reminder time, and weekend exclusion.
- Disable both automatic entry points with “다시 알리지 않기”.
- Reopen the settings from **설정 > 오늘 브리핑·노출 설정...** after automatic display is disabled.
- Respect startup and daily trigger switches before creating the dialog.
- Preserve confirm, cancel, close, focus, and keyboard-accessible control behavior.

## Implementation Checklist

- [x] Borderless rounded modal shell.
- [x] Compact daily briefing state.
- [x] Wide-screen expansion and narrow-screen layer fallback.
- [x] Persistent visibility and reminder settings.
- [x] Light and dark theme rendering.
- [x] Focused regression, theme, accessibility, lint, JSON, and encoding checks.

## Follow-up Polish

- Consider a short width animation for the wide-screen expansion if motion is later desired; it is intentionally omitted now to keep modal opening immediate and dependable.

final result: passed

# Air Calendar Navy and Lilac Native UI QA - 2026-11-05

## Scope and visual evidence

The user selected the second generated concept and required the existing arbitrary colors, transparency, movable panels and independent widgets. This implementation updates the native PyQt calendar, task editor, navigation and compact recurring-event confirmation.

- Source visual truth is artifacts/navy-lilac-redesign-20261105/selected-reference.png, 1487 x 1058 pixels.
- The implemented main window is 1488 x 1058 at device pixel ratio 1.0, with a 580 x 1022 editor. The one-pixel source width difference needs no resampling.
- Full comparison is artifacts/navy-lilac-redesign-20261105/comparison-final.png, with the source and actual render together at 2975 x 1058.
- Focused editor comparison is artifacts/navy-lilac-redesign-20261105/editor-comparison-final.png. The source editor crop is scaled proportionally to the actual editor height for typography and spacing review.
- Actual states are navy-main-editor.png, light-main-editor.png, custom-main-editor.png, transparent-main.png and navy-compact.png in the same folder. The compact window is 900 x 760.
- The whole-window editor view combines unmodified native widget grabs at their actual window coordinates. The offscreen platform supplies client rendering without native desktop compositing.
- The capture uses isolated SQLite, INI settings, shared-storage path and synthetic events. Native preference snapshots were verified after each capture. The fixture blocks external network and registry writes.

## Comparison history and repairs

1. The first actual render is retained in iteration-1/.
   - P1. A queued common text-fit pass restored the old editor size after right alignment, clipping the editor against the window edge.
   - P2. Time-shortcut height constraints cropped the bottom of buttons.
   - P2. Small calendar typography and the selected-day toolbar consumed too much space at narrow widths.
2. Repairs set sheet size before common fitting and defer positioning until the fitter completes. Time controls use compatible minimum and maximum heights. Month/day typography now follows the user font with a clearer hierarchy. The agenda uses one checked view menu and a 216-pixel minimum. Event time and priority are optional prefixes so the actual title remains visible in narrow cells.
3. Final captures were inspected both beside the source and at editor detail scale. Essential controls, memo and footer fit the wide editor. The narrow month retains shortened readable event titles and the full selected-day details.
4. An intermittent SIP exception occurred during interpreter shutdown in the diagnostic fixture. Capturing and normal app cleanup had already finished. Rail-enabled and rail-disabled replays each exited successfully four times. Retaining QApplication through explicit DeferredDelete cleanup made final dark, light, custom-color and transparent captures exit normally. This repair belongs to the verification fixture.

## Required fidelity surfaces

- Typography uses the configured application family and size. A prominent month heading, readable dates and an emphasized event title establish hierarchy. Custom fonts and large-font widgets keep their size policies.
- Layout uses the selected direction's left icon rail, restrained app bar, month grid and right-side editor. Main actions remain fixed while secondary editor fields expand inside the scroll area.
- Colors come from existing semantic theme roles. Navy and Lilac is an additional family with dark and light variants. Arbitrary user base/accent colors and the existing opacity settings remain active. A renderer sample at 165/255 opacity has a cell alpha of 135 and toolbar alpha of 116, while the full-opacity capture has alpha 255.
- Existing brand identity and qtawesome icons supply application graphics. The controls remain native editable widgets.
- Copy and content retain actual calendar/time semantics, exact-minute editing, recurring options, continuous registration and the existing save action. The real calendar computes weekday/date pairs, correcting the generated concept's date-grid inaccuracies.

## Intentional native adaptations

The editor is a movable native dialog aligned to the main window. It overlays the underlying dock layout and preserves user arrangements. Existing time shortcuts, tag support, edit/delete flows and routine tabs remain available. Navigation buttons reuse the real checkable dock actions, whose checked state indicates panel visibility. The optional new palette is applied through the existing appearance dialog.

## Interaction and regression evidence

- Forty task-editor tests passed in fresh processes, covering create, edit, move, copy, exact minutes, midnight crossing, inclusive all-day periods, calendar ownership, continuous input and commit-before-toast.
- Nineteen final calendar and side-panel tests passed after the compact-title fix.
- Twenty-four localization, dialog and navigation checks passed.
- A 121-test dock/widget suite passed, including movable/floating docks, saved layouts, free widget geometry and opacity.
- The scoped appearance/navigation suite passed 154 tests and 43 subtests, including toolbar hide/move/state restore, lock handling, theme refresh and arbitrary color/opacity preservation.
- Ruff, diff whitespace checks and the global encoding guard passed.

## Remaining verification limits

Native Windows captions, physical desktop composition, multiple-monitor placement, screen readers and a full physical DPI matrix require their corresponding environment checks. The captured native client layouts and scoped behavioral regressions support this handoff.

## Final assessment

The earlier geometry, button clipping and narrow-layout findings are resolved in final evidence. Differences in native chrome, dense legacy metadata and user-customized palette/font are accepted product adaptations. No actionable P0, P1 or P2 issue remains in the reviewed client states.

final result: passed

# Air Calendar Shared Dialog Visual QA - 2026-11-05

The selected navy/lilac direction now reaches the shared native dialog base, custom modal wrappers, alarms, daily briefing, focus feedback and task detail actions. The palette remains derived from saved settings; light, arbitrary custom colors, opacity and explicitly selected independent widget skins remain supported.

## Reviewed evidence

- Source: `artifacts/navy-lilac-redesign-20261105/selected-reference.png`.
- Native main/editor regression: `artifacts/dialog-visual-system-20261105/main-regression/navy-main-editor.png`, compared with the source in the same review.
- Common confirmations, input, recurring scope and task detail: `artifacts/dialog-visual-system-20261105/{navy,light,custom,transparent}-dialogs.png`.
- Provider settings: 15 full-size native captures plus five 1024x768 screen cases under `artifacts/dialog-visual-system-20261105/providers/`.
- Widget manager, label settings, emoji and launcher: 12 captures under `artifacts/dialog-visual-system-20261105/long-tail/`.
- Alarm, focus completion, briefing/settings and phase toast: dark/light/custom and narrow captures under `artifacts/alarm-surfaces-20261105/`.

## Findings and resolution

Shared-style bypasses, doubled settings base styles and footer separators, stretched label settings cards, an unconfigured launcher using a light skin, provider primary icon contrast and disappearing phase-toast lifetime were corrected. Fixed dialog footers remain available while long content scrolls. The application show filter covers 59 dialog declarations, including derived classes, and standard Qt dialogs; source inventory is distinct from clicking every runtime state.

The reported duplicate detail action row now uses two persistent controls and publishes only fully prepared content. Repeated rebuilds preserve widget identity, status clicks emit once for the latest state, and each of four palette/opacity modes rendered one row after twenty expansions.

Two independent read-only reviews also found partial accent bundles leaving stale derived action colors and explicitly styled message boxes bypassing standard action roles. Both were fixed with regression coverage.

Scope-level test results, retained failures and final evidence are documented in `docs/ux-audit/dialog-visual-consistency-20261105.md`. Qt offscreen rendering does not establish native Windows desktop composition, physical monitor/DPI behavior or OS toast appearance. The currently running user app was not forcibly closed, and Store deployment is outside this source change.

No actionable P0, P1 or P2 issue remains in the reviewed client states.

final result: passed

# Fresh Shared Design Audit - 2026-11-05

The user's follow-up requested a deeper consistency review. New actual Qt captures exposed states missed by the earlier representative checks: unreadable alternate table rows, unsafe color-override derivation, auto-family surfaces resolved from stale dark settings, clipped valid alarm text, stale font previews, empty initial token presets, recurrence summary/date issues, light help keycaps, print viewport gaps, compact action clipping and inconsistent true footers.

Confirmed issues were corrected and re-rendered with separate before/after evidence. A real bootstrap and router modal run also verified the FocusLog system-theme transition while preserving rows and selection. Root shared-style changes were independently probed after the fixes. Final checklist and label modal footer heights are 44/44 in five profiles; ordinary cycle selection follows the current accent.

The audit report `docs/ux-audit/common-design-verification-20261105.md` lists each finding, resolution, flow step, accepted screenshots and test evidence. Evidence resides under `artifacts/dialog-consistency-audit-20261105/`; previous captures were not reused as current-run audit proof or overwritten to hide failures.

Windows app connection timed out, so this remains an isolated native Qt client audit. Platform spin arrows, physical DPI/multiple-monitor composition, OS toast chrome and assistive technology require their respective live environment checks. Generic retained dialogs still follow their explicit refresh contract; the confirmed FocusLog call path was fixed, rather than asserting that every open special dialog has been tested through an OS transition.

final result: reviewed client defects resolved; live Windows limits documented

# Physical Windows Modal and Brand QA - 2026-11-05

Implemented the selected navy/lilac modal composition with one internal title/close row, scrollable content, retained footer actions and screen-aware initial sizing. Appearance presets now fit their thumbnails and reflow beside/above a compact preview. Ordinary feedback uses one reusable Air Calendar toast. The feather symbol follows the active accent and reading surface across the top bar, common modal header, toast and splash; exported shell/package assets share the same master.

Accepted native evidence: 92 dialog/control/appearance/feedback/splash states across physical 96/120 DPI and dark/light/custom opacity profiles, plus eight real bootstrap month/week states at 100% and 125%. All accepted reports record zero capture/bounds errors and preserved native preferences. Transparent windows use actual desktop compositor pixels, not QWidget rendering. Initial black captures and failed monitor matching remain retained as rejected evidence.

Actual Windows input confirmed header motion at 100% and 125%, resize from 700x660 to 650x620 at 125%, retained footer actions, internal close, ESC and Alt+F4. Windows manual move/resize paths were added after native operations reported success without changing the window. OS Snap and mixed-DPI boundary dragging are outside that input check.

The audit also reproduced and fixed two real Qt fatal lifetime errors: an event filter called during Python GC and a delayed editor feedback callback accessing a deleted QLabel. Final common regression: 80 passed and 18 subtests, normal exit. Task create/modify/move/copy regression: 40 passed and 15 subtests, normal exit. Brand/appearance/calendar regression: 256 passed and 31 subtests. Source asset audit verified 114 generated files; Pillow generator tests, encoding and relevant Ruff checks passed.

Full scoped findings, rejected evidence, accepted screenshots and test reports: `docs/ux-audit/native-windows-modal-system-20261105.md`. This validates source and disposable Windows execution, not deployment or an installed Store update. The user's existing running app was preserved.

final result: reviewed native defects resolved; evidence boundaries documented

---

# Window Usability and Pearl Lilac Follow-up - 2026-11-05

The follow-up fixes the transparent dock-tab gap, application-wide wheel value changes, modal reading opacity, management header/tab/close ownership, Widget Manager subtab surfaces, Help search Enter and checklist shortcut/timer scope. Accepted current-run Windows evidence covers 24 dark states at 100% and 24 custom low-opacity states at 125%, with native wheel input and management close events. Full findings and retained failures are in `docs/ux-audit/ui-usability-followup-20261105.md`.

A new generated Pearl Lilac design board guided the light palette, white reading cards, opaque slate text, mode-aware dividers and contrast-safe state colors. The main window and modal/subtab paths share semantic tokens. Explicit and system modes resolve family pairs without overwriting saved user colors; direct choices preserve their independent origins. Native follow-up also corrected white calendar selection hints, a narrow Google auth navigation button and the daily reminder label layout.

Accepted light evidence: 24 subtab states at physical 96 DPI, 25 at physical 120 DPI including the briefing bottom-scroll state, and four real-bootstrap month/week states at each DPI. Captures, bounds, process completion and native settings checks passed. The design board is a proposal and is separate from execution screenshots. The report `docs/ux-audit/light-mode-pearl-lilac-20261105.md` records palette, implementation, test groups and evidence limits.

User databases, live account settings, installed packages and the running user application were preserved. This is source and disposable Windows execution validation; Store deployment, real remote sync, every color combination and complete accessibility certification are outside the evidence.

final result: reviewed follow-up defects resolved; light design implemented and native scope documented
