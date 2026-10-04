# Air Calendar 3.7.10

2026-10-04

Rebuilt the complete current development runtime used by `run.bat`, including KeyDeck schema v4, Studio, physical keycap rendering and layout library management. The new package is compared directly with the current source and assets, rather than relying on its version label.

Added `run-release.bat` to launch the finished `dist/x64/DarkCalendar/DarkCalendar.exe` and avoid accidentally launching the older intermediate executable under `build/`. Release builds preserve running Store installations and refuse to clean output that is still in use.

Validation: 239 compiled application modules and 114 resources match the development runtime. The release EXE's extracted KeyDeck code passes draft editing, keycap rendering and layout document creation in an isolated Qt fixture. User settings and databases are preserved.
