import os
import sys

# ── Surface / High-DPI 최적화 ──
# PyQt6 는 기본적으로 HighDPI 를 지원하지만, Surface 등 고해상도 디바이스에서
# 태블릿⇔데스크톱 모드 전환 시에도 안정적으로 동작하도록 명시 선언.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

from calendar_app.infrastructure.runtime.crash_bootstrap import (
    setup_crash_logging,
    teardown_crash_logging,
)

_faulthandler_stream = setup_crash_logging()

if __name__ == "__main__":
    from calendar_app.bootstrap import run

    exit_code = 1
    try:
        exit_code = run()
    finally:
        teardown_crash_logging(_faulthandler_stream)

    sys.exit(exit_code)
