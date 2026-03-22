"""Manual patch helper script.

This file is intentionally executable as a script and should not run at import
time so pytest collection does not fail.
"""

from __future__ import annotations

from pathlib import Path


def apply_patch_detail_transform() -> None:
    target = Path("d:/Dark Calendar/calendar_app/presentation/calendar/month_renderer.py")
    content = target.read_text(encoding="utf-8", errors="strict")

    old1 = (
        '        "description": getattr(event, "description", "") or "",\r\n'
        '        "memo": getattr(event, "description", "") or "",\r\n'
    )
    new1 = (
        '        "_start_raw": str(getattr(event, "start_time", "") or "").strip(),\r\n'
        '        "_end_raw": str(getattr(event, "end_time", "") or "").strip(),\r\n'
        '        "description": getattr(event, "description", "") or "",\r\n'
        '        "memo": getattr(event, "description", "") or "",\r\n'
    )
    assert old1 in content, "PART1 not found"
    content = content.replace(old1, new1, 1)

    old2 = (
        '        "_subscription_summary": summary,\r\n'
        '        "_subscription_calendar_id": subscription_row.get("calendar_id") or "",\r\n'
        '    }'
    )
    new2 = (
        '        "_subscription_summary": summary,\r\n'
        '        "_subscription_calendar_id": subscription_row.get("calendar_id") or "",\r\n'
        '        "_gcal_event_id": getattr(event, "id", "") or "",\r\n'
        '        "_gcal_status": getattr(event, "status", "") or "",\r\n'
        '        "_gcal_updated": getattr(event, "updated_time", "") or "",\r\n'
        '    }'
    )
    assert old2 in content, "PART2 not found"
    content = content.replace(old2, new2, 1)
    print("PASS 1+2: normalize fields")

    target.write_text(content, encoding="utf-8", errors="strict")


if __name__ == "__main__":
    apply_patch_detail_transform()
