# 5.0.0 release QA compatibility adapter

`native_release_smoke_adapter.py` delegates to the reserved, unchanged
`scripts/native_release_smoke.py`. It does not build or modify the payload.
The release workflow changes only its native QA invocation path.

Two version-specific assumptions in the original helper are incompatible with
the new candidate and its pinned historical upgrade baseline:

- The original helper expects `python<host major><host minor>.dll` for every
  process. The QA host and candidate are Python 3.14.10; immutable 4.3.3 loads
  `python313.dll`. Prior verified baseline evidence confirms that loaded DLL.
- The briefing selector hard-codes `Qt6102QWindow`. The candidate uses Qt 6.12.0,
  whose Windows class prefix is `Qt6120`. Qt builds the prefix from all three
  version components in its
  [official window class registry](https://raw.githubusercontent.com/qt/qtbase/v6.12.0/src/plugins/platforms/windows/qwindowswindowclassregistry.cpp).

For each original launch call, the adapter locates exactly one versioned Python
DLL and one Qt6Core DLL in the payload. It reads PE **ProductVersion** (CPython's
fixed FileVersion has a different encoding), checks candidate Python 3.14.10 /
Qt 6.12.0 or baseline Python 3.13 / Qt 6.10.2, and hashes those exact files. Only
the smoke module's `sys` reference receives a contextual `version_info` for its
expected DLL-name check. The actual host `sys`, `sys.platform`, environment and
hosted-runner guard are unchanged. The original loaded path/hash results must
match those exact PE-verified files. The briefing selector still requires the
same visible PID, main-window owner, exact title and unique exact Qt class; the
original content/Confirm/foreground checks remain in place.

The baseline failure fallback cannot make the first mismatch harmless: the
original wrong-DLL exception happens before normal Exit, leaving no completed
shutdown/DB-close/native fault evidence. The legacy classifier accepts only the
pinned historical SIP teardown fault after the normal lifecycle, and remains
unchanged. Candidate failures remain strict.

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
