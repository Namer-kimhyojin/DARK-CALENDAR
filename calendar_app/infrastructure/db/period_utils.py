"""일반업무 주기별 기간 계산 유틸리티.



DB나 UI에 의존하지 않는 순수 datetime 로직.

database_unified.py와 db_repository_unified.py 양쪽에서 import하여 사용한다.

"""

import calendar
from datetime import datetime, timedelta


def calculate_period_bounds(target_date_str, cycle_type):
    """

    일반업무 유형에 따라 기간의 시작일과 종료일을 계산합니다.



    Args:

        target_date_str: 'YYYY-MM-DD' 형식의 기준일

        cycle_type: 'weekly', 'monthly', 'quarterly', 'half_yearly', 'yearly'



    Returns:

        (period_start, period_end) 튜플 (YYYY-MM-DD 형식)

    """

    if not target_date_str or not cycle_type:
        return None, None

    try:
        target_date = datetime.strptime(target_date_str[:10], "%Y-%m-%d")

    except Exception:
        return None, None

    if cycle_type == "weekly":
        # 주간: 월요일 ~ 일요일

        weekday = target_date.weekday()  # 0=Monday, 6=Sunday

        period_start = target_date - timedelta(days=weekday)

        period_end = period_start + timedelta(days=6)

    elif cycle_type == "monthly":
        # 월간: 해당 월의 1일 ~ 마지막 날

        period_start = target_date.replace(day=1)

        last_day = calendar.monthrange(target_date.year, target_date.month)[1]

        period_end = target_date.replace(day=last_day)

    elif cycle_type == "quarterly":
        # 분기: 1~3월, 4~6월, 7~9월, 10~12월

        quarter = (target_date.month - 1) // 3

        start_month = quarter * 3 + 1

        end_month = start_month + 2

        period_start = target_date.replace(month=start_month, day=1)

        last_day = calendar.monthrange(target_date.year, end_month)[1]

        period_end = target_date.replace(month=end_month, day=last_day)

    elif cycle_type == "half_yearly":
        # 반기: 1~6월, 7~12월

        if target_date.month <= 6:
            period_start = target_date.replace(month=1, day=1)

            period_end = target_date.replace(month=6, day=30)

        else:
            period_start = target_date.replace(month=7, day=1)

            period_end = target_date.replace(month=12, day=31)

    elif cycle_type == "yearly":
        # 연간: 1월 1일 ~ 12월 31일

        period_start = target_date.replace(month=1, day=1)

        period_end = target_date.replace(month=12, day=31)

    else:
        # 기본값: 당일

        period_start = target_date

        period_end = target_date

    return period_start.strftime("%Y-%m-%d"), period_end.strftime("%Y-%m-%d")
