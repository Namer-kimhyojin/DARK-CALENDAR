# Release QA adapters

`native_final_smoke.py` is the entry point the release workflow runs. It wraps the
unchanged `scripts/native_release_smoke.py` with the adapters in this folder and
does not build or modify the payload.

`native_release_smoke_adapter.py` adapts two assumptions of the original helper:

- The helper expects `python<host major><host minor>.dll` for every process. The
  adapter locates exactly one versioned Python DLL and one Qt6Core DLL in each
  payload, reads their PE **ProductVersion** (CPython's fixed FileVersion uses a
  different encoding) and hashes those files. Only the smoke module's `sys`
  reference receives a contextual `version_info`; the host `sys`, platform,
  environment and hosted-runner guard are unchanged.
- The briefing selector hard-codes `Qt6102QWindow`. Qt builds the window class
  prefix from all three version components
  ([Qt window class registry](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/plugins/platforms/windows/qwindowswindowclassregistry.cpp)),
  so Qt 6.12.0 uses `Qt6120`.

The candidate and the pinned public 5.5.1 upgrade baseline both use Python 3.14 /
Qt 6.12.0. When the baseline moves to a newer public release, update
`BASELINE_PYTHON` / `BASELINE_QT` together with the hashes in
`scripts/prepare_native_smoke_baseline.py` and `scripts/native_release_smoke.py`.
The loaded DLL paths and hashes must match the PE-verified files. The briefing
selector still requires the same visible PID, main-window owner, exact title and
a unique exact Qt class.

The 3.14.10 faulthandler still emits the same exact Windows exception header and
continues to the next handler. Its new C-stack output does not require relaxing
the existing RPC/traceback gate. See
[CPython 3.14.10 source](https://raw.githubusercontent.com/python/cpython/v3.14.10/Modules/faulthandler.c).

## Feature evidence boundary

Source regression + exact source/PYZ/resource match + separate native waveOut
observation + six frozen EXE startup/restart cycles are complementary evidence.
The six cycles exercise main UI/DB/shutdown; they do not click the loopdeck or
exercise its dynamic resource/audio path inside the frozen executable. Do not
describe those cycles as a frozen loopdeck interaction or listening test.

A minimal additional frozen route on the disposable VM is:

1. Main **Widgets → Add Launcher Deck**, accept a named synthetic deck.
2. Identify its same-PID canvas by accessible name **KEYDECK** and the newly
   created native HWND, then open its context menu with actual input.
3. **Layouts → Beatmaker 4×4 · Lo-fi Desk**, acknowledge the exact owned layout
   replacement confirmation, then reopen that deck's context menu.
4. **Beatmaker → Loop deck · 4 tracks**. Require the exact owned dialog and
   accessible controls (`looperBpm`, `looperBank`, four `looperTrackSelect*`,
   `looperPadCanvas`, `looperPosition`, `looperStatus`).
5. Click **Record selected track**, focus the pad canvas and send actual Q/Z
   key presses; observe two hits and automatic loop mode after one bar. Repeat
   on track two, exercise mute/gain/Stop, then close normally. Inspect the
   disposable persisted deck JSON and reopen silently to verify the two layers.
6. Capture before/after UI and native logs, verify all created widgets/dialogs
   close, then continue the existing normal main Exit/restart gate.

This route uses public UI and a disposable profile; it does not expose a QA
command in the product or invoke private product methods. Canvas pads are
painted, so UIA identifies/focuses the canvas and normal keyboard input provides
pad events. Sound backend/asset availability can be observed separately; human
audibility remains a separate observation. This README describes the route;
the adapter itself does not add those feature interactions.
