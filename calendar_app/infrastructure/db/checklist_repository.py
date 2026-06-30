"""

체크리스트 템플릿 및 항목 관리 전용 Repository

"""

from datetime import datetime

from calendar_app.infrastructure.db.database_unified import db_manager


def get_connection():
    """Singleton 데이터베이스 관리자를 통해 연결을 획득합니다."""

    return db_manager.get_connection()


# ==================== 체크리스트 템플릿 관리 ====================


def get_all_checklist_templates(active_only=False, category=None):
    """

    모든 체크리스트 템플릿 조회



    Args:

        active_only: True면 활성화된 템플릿만 조회

        category: 카테고리 필터 (선택사항)



    Returns:

        list of dict

    """

    conn = get_connection()

    if not conn:
        return []

    cur = conn.cursor()

    query = "SELECT * FROM checklist_template WHERE 1=1"

    params = []

    if active_only:
        query += " AND is_active=1"

    if category:
        query += " AND category=?"

        params.append(category)

    query += " ORDER BY category, name"

    cur.execute(query, params)

    rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_checklist_template(template_id):
    """특정 템플릿 조회"""

    conn = get_connection()

    if not conn:
        return None

    cur = conn.cursor()

    cur.execute("SELECT * FROM checklist_template WHERE id=?", (template_id,))

    row = cur.fetchone()

    return dict(row) if row else None


def create_checklist_template(name, description=None, category=None, checklist_type="list"):
    """

    체크리스트 템플릿 생성



    Args:

        name: 템플릿 이름

        description: 설명

        category: 카테고리 (예: '일정', '일반업무', '공통')



    Returns:

        생성된 템플릿 ID

    """

    conn = get_connection()

    if not conn:
        return None

    cur = conn.cursor()

    try:
        cur.execute(
            """

            INSERT INTO checklist_template (name, description, category, checklist_type)

            VALUES (?, ?, ?, ?)

        """,
            (name, description, category, checklist_type),
        )

        template_id = cur.lastrowid

        conn.commit()

        return template_id

    except Exception as e:
        print(f"Error creating checklist template: {e}")

        conn.rollback()

        return None

    try:
        pass

    finally:
        pass


def update_checklist_template(template_id, updates):
    """

    체크리스트 템플릿 수정



    Args:

        template_id: 템플릿 ID

        updates: 수정할 필드들의 dict



    Returns:

        성공 여부 (bool)

    """

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    # updated_at 자동 업데이트

    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 동적 UPDATE 쿼리 생성

    set_clause = ", ".join([f"{k}=?" for k in updates])

    values = list(updates.values()) + [template_id]

    try:
        cur.execute(f"UPDATE checklist_template SET {set_clause} WHERE id=?", values)

        if cur.rowcount == 0:
            print(f"Warning: No rows updated for template_id {template_id}")

        conn.commit()

        return True

    except Exception as e:
        print(f"Error updating checklist template: {e}")

        conn.rollback()

        return False

    try:
        pass

    finally:
        pass


def delete_checklist_template(template_id):
    """

    체크리스트 템플릿 삭제 (관련 항목도 함께 삭제)



    Args:

        template_id: 템플릿 ID



    Returns:

        성공 여부 (bool)

    """

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    try:
        # checklist_item은 FOREIGN KEY CASCADE로 자동 삭제됨

        cur.execute("DELETE FROM checklist_template WHERE id=?", (template_id,))

        conn.commit()

        return True

    except Exception as e:
        print(f"Error deleting checklist template: {e}")

        conn.rollback()

        return False

    try:
        pass

    finally:
        pass


def toggle_checklist_template_active(template_id):
    """템플릿 활성화/비활성화 토글"""

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    try:
        cur.execute(
            """

            UPDATE checklist_template

            SET is_active = 1 - is_active,

                updated_at = datetime('now', 'localtime')

            WHERE id=?

        """,
            (template_id,),
        )

        conn.commit()

        return True

    except Exception as e:
        print(f"Error toggling template active: {e}")

        conn.rollback()

        return False

    try:
        pass

    # ==================== 체크리스트 항목 관리 ====================

    finally:
        pass


def get_checklist_items(template_id):
    """

    특정 템플릿의 모든 항목 조회



    Returns:

        list of dict

    """

    conn = get_connection()

    if not conn:
        return []

    cur = conn.cursor()

    cur.execute(
        """

        SELECT * FROM checklist_item

        WHERE checklist_id=?

        ORDER BY item_order, id

    """,
        (template_id,),
    )

    rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_checklist_item(item_id):
    """특정 항목 조회"""

    conn = get_connection()

    if not conn:
        return None

    cur = conn.cursor()

    cur.execute("SELECT * FROM checklist_item WHERE id=?", (item_id,))

    row = cur.fetchone()

    return dict(row) if row else None


def create_checklist_item(
    checklist_id, item_text, item_description=None, item_guide=None, item_order=0, is_required=0
):
    """

    체크리스트 항목 생성



    Args:

        checklist_id: 템플릿 ID

        item_text: 항목 텍스트 (필수)

        item_description: 항목 설명

        item_guide: 안내 가이드

        item_order: 정렬 순서

        is_required: 필수 항목 여부 (0 or 1)



    Returns:

        생성된 항목 ID

    """

    conn = get_connection()

    if not conn:
        return None

    cur = conn.cursor()

    try:
        cur.execute(
            """

            INSERT INTO checklist_item

            (checklist_id, item_text, item_description, item_guide, item_order, is_required)

            VALUES (?, ?, ?, ?, ?, ?)

        """,
            (checklist_id, item_text, item_description, item_guide, item_order, is_required),
        )

        item_id = cur.lastrowid

        conn.commit()

        # 템플릿의 updated_at 갱신

        cur = conn.cursor()

        cur.execute(
            """

            UPDATE checklist_template

            SET updated_at = datetime('now', 'localtime')

            WHERE id=?

        """,
            (checklist_id,),
        )

        conn.commit()

        return item_id

    except Exception as e:
        print(f"Error creating checklist item: {e}")

        conn.rollback()

        return None

    try:
        pass

    finally:
        pass


def update_checklist_item(item_id, updates):
    """

    체크리스트 항목 수정



    Args:

        item_id: 항목 ID

        updates: 수정할 필드들의 dict



    Returns:

        성공 여부 (bool)

    """

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    # 동적 UPDATE 쿼리 생성

    set_clause = ", ".join([f"{k}=?" for k in updates])

    values = list(updates.values()) + [item_id]

    try:
        # 항목 업데이트

        cur.execute(f"UPDATE checklist_item SET {set_clause} WHERE id=?", values)

        # 템플릿의 updated_at 갱신

        cur.execute(
            """

            UPDATE checklist_template

            SET updated_at = datetime('now', 'localtime')

            WHERE id = (SELECT checklist_id FROM checklist_item WHERE id=?)

        """,
            (item_id,),
        )

        conn.commit()

        return True

    except Exception as e:
        print(f"Error updating checklist item: {e}")

        conn.rollback()

        return False

    try:
        pass

    finally:
        pass


def delete_checklist_item(item_id):
    """

    체크리스트 항목 삭제



    Args:

        item_id: 항목 ID



    Returns:

        성공 여부 (bool)

    """

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    try:
        # 템플릿 ID 조회

        cur.execute("SELECT checklist_id FROM checklist_item WHERE id=?", (item_id,))

        row = cur.fetchone()

        if not row:
            return False

        checklist_id = row["checklist_id"]

        # 항목 삭제

        cur.execute("DELETE FROM checklist_item WHERE id=?", (item_id,))

        # 템플릿의 updated_at 갱신

        cur.execute(
            """

            UPDATE checklist_template

            SET updated_at = datetime('now', 'localtime')

            WHERE id=?

        """,
            (checklist_id,),
        )

        conn.commit()

        return True

    except Exception as e:
        print(f"Error deleting checklist item: {e}")

        conn.rollback()

        return False

    try:
        pass

    finally:
        pass


def reorder_checklist_items(template_id, item_ids_ordered):
    """

    체크리스트 항목 순서 재정렬



    Args:

        template_id: 템플릿 ID

        item_ids_ordered: 순서대로 정렬된 항목 ID 리스트



    Returns:

        성공 여부 (bool)

    """

    conn = get_connection()

    if not conn:
        return False

    cur = conn.cursor()

    try:
        # 일관성을 위해 한 트랜잭션으로 처리

        for order, item_id in enumerate(item_ids_ordered):
            cur.execute(
                """

                UPDATE checklist_item

                SET item_order=?

                WHERE id=? AND checklist_id=?

            """,
                (order, item_id, template_id),
            )

        # 템플릿의 updated_at 갱신

        cur.execute(
            """

            UPDATE checklist_template

            SET updated_at = datetime('now', 'localtime')

            WHERE id=?

        """,
            (template_id,),
        )

        conn.commit()

        return True

    except Exception as e:
        print(f"Error reordering checklist items: {e}")

        conn.rollback()

        return False

    try:
        pass

    # ==================== 복사 및 복제 ====================

    finally:
        pass


def duplicate_checklist_template(template_id, new_name=None):
    """

    체크리스트 템플릿 복제 (항목도 함께 복제)



    Args:

        template_id: 원본 템플릿 ID

        new_name: 새 템플릿 이름 (None이면 "원본 이름 (복사)"로 생성)



    Returns:

        새 템플릿 ID

    """

    conn = get_connection()

    if not conn:
        return None

    cur = conn.cursor()

    try:
        # 원본 템플릿 조회

        cur.execute("SELECT * FROM checklist_template WHERE id=?", (template_id,))

        template = cur.fetchone()

        if not template:
            return None

        # 새 이름 설정

        if not new_name:
            new_name = f"{template['name']} (복사)"

        # 템플릿 복제

        cur.execute(
            """

            INSERT INTO checklist_template (name, description, category, checklist_type, is_active)

            VALUES (?, ?, ?, ?, ?)

        """,
            (
                new_name,
                template["description"],
                template["category"],
                template.get("checklist_type", "list"),
                template["is_active"],
            ),
        )

        new_template_id = cur.lastrowid

        # 항목들 복제

        cur.execute(
            """

            SELECT * FROM checklist_item WHERE checklist_id=? ORDER BY item_order

        """,
            (template_id,),
        )

        items = cur.fetchall()

        for item in items:
            cur.execute(
                """

                INSERT INTO checklist_item

                (checklist_id, item_text, item_description, item_guide, item_order, is_required)

                VALUES (?, ?, ?, ?, ?, ?)

            """,
                (
                    new_template_id,
                    item["item_text"],
                    item["item_description"],
                    item["item_guide"],
                    item["item_order"],
                    item["is_required"],
                ),
            )

        conn.commit()

        return new_template_id

    except Exception as e:
        print(f"Error duplicating checklist template: {e}")

        conn.rollback()

        return None

    try:
        pass

    # ==================== 통계 및 분석 ====================

    finally:
        pass


def get_checklist_usage_stats(template_id):
    """

    체크리스트 템플릿의 사용 통계



    Returns:

        {

            'total_tasks': int,  # 이 템플릿을 사용하는 총 task 수

            'schedule_count': int,  # 일정에서 사용 횟수

            'routine_count': int,  # 일반업무에서 사용 횟수

        }

    """

    conn = get_connection()

    if not conn:
        return {"total_tasks": 0, "schedule_count": 0, "routine_count": 0}

    cur = conn.cursor()

    # 템플릿 이름 조회

    cur.execute("SELECT name FROM checklist_template WHERE id=?", (template_id,))

    row = cur.fetchone()

    if not row:
        return {"total_tasks": 0, "schedule_count": 0, "routine_count": 0}

    template_name = row["name"]

    # unified_task에서 template_id 또는 이름으로 사용 횟수 조회

    cur.execute(
        """

        SELECT

            COUNT(*) as total,

            SUM(CASE WHEN type='schedule' THEN 1 ELSE 0 END) as schedule_count,

            SUM(CASE WHEN type='routine' THEN 1 ELSE 0 END) as routine_count

        FROM unified_task

        WHERE template_id=? OR name LIKE ?

    """,
        (template_id, f"%{template_name}%"),
    )

    row = cur.fetchone()

    return {
        "total_tasks": row["total"] or 0,
        "schedule_count": row["schedule_count"] or 0,
        "routine_count": row["routine_count"] or 0,
    }


def get_all_categories():
    """등록된 모든 카테고리 목록 조회"""

    conn = get_connection()

    if not conn:
        return []

    cur = conn.cursor()

    cur.execute("""

        SELECT DISTINCT category

        FROM checklist_template

        WHERE category IS NOT NULL AND category != ''

        ORDER BY category

    """)

    rows = cur.fetchall()

    return [row["category"] for row in rows]


def seed_default_templates():
    """기본 사무 업무 템플릿 샘플 데이터 추가"""

    conn = get_connection()

    if not conn:
        return

    cur = conn.cursor()

    # 이미 데이터가 있는지 확인

    cur.execute("SELECT COUNT(*) as cnt FROM checklist_template")

    if cur.fetchone()["cnt"] > 0:
        return

    # 샘플 데이터 정의

    samples = [
        {
            "name": "주간 업무 보고",
            "desc": "매주 금요일 정기적으로 실행하는 주간 보고 절차",
            "cat": "일반업무",
            "items": [
                {"text": "전주 업무 실적 요약", "desc": "완료된 과업 및 성과 정리", "req": 1},
                {
                    "text": "금주 업무 계획 작성",
                    "desc": "차주 주요 마일스톤 및 일정 수립",
                    "req": 1,
                },
                {
                    "text": "주요 이슈 및 건의사항 정리",
                    "desc": "병목 현상이나 지원 필요 사항 기술",
                    "req": 0,
                },
                {"text": "팀원 공유 및 피드백 반영", "desc": "최종 제출 전 팀 내 리뷰", "req": 1},
            ],
        },
        {
            "name": "회의 준비 및 세팅",
            "desc": "성공적인 회의를 위한 사전 준비 체크리스트",
            "cat": "일정",
            "items": [
                {
                    "text": "회의 목적 및 안건 확정",
                    "desc": "Agenda 명확화 및 참석자 공유",
                    "req": 1,
                },
                {
                    "text": "참석자 일정 확인 및 초대 전송",
                    "desc": "캘린더 초대장 발송 확인",
                    "req": 1,
                },
                {
                    "text": "회의실 예약 및 환경 점검",
                    "desc": "빔프로젝터, 마이크, 다과 등 준비",
                    "req": 1,
                },
                {
                    "text": "회의 자료 인쇄 및 사전 배포",
                    "desc": "참석자 숙지용 자료 전달",
                    "req": 0,
                },
            ],
        },
        {
            "name": "출장 정산 및 보고",
            "desc": "출장 복귀 후 진행하는 행정 처리 절차",
            "cat": "일정",
            "items": [
                {
                    "text": "영수증 수집 및 정리",
                    "desc": "교통비, 숙박비, 식비 등 증빙 확보",
                    "req": 1,
                },
                {
                    "text": "출장 결과 보고서 작성",
                    "desc": "방문 목적 달성 여부 및 핵심 정보 요약",
                    "req": 1,
                },
                {"text": "ERP/경비 시스템 입력", "desc": "비용 지급 신청 완료", "req": 1},
                {"text": "증빙 서류 제출", "desc": "회계팀 실물 영수증 전달(해당 시)", "req": 0},
            ],
        },
        {
            "name": "신규 입사자 온보딩 가이드",
            "desc": "팀에 합류한 신규 멤버를 위한 초기 셋팅",
            "cat": "일반업무",
            "items": [
                {
                    "text": "IT 장비 지급 및 계정 생성",
                    "desc": "PC, 이메일, 사내망 권한 확인",
                    "req": 1,
                },
                {
                    "text": "부서원 인사 및 자리 안내",
                    "desc": "팀 내 문화 및 주변 환경 소개",
                    "req": 1,
                },
                {
                    "text": "협업 툴(메신저, 위키) 초대",
                    "desc": "Slack, Notion, Jira 등 접근 권한 부여",
                    "req": 1,
                },
                {
                    "text": "필수 보안/윤리 교육 이수 안내",
                    "desc": "사내 규정 및 법정 필수 교육 가이드",
                    "req": 1,
                },
            ],
        },
        {
            "name": "월간 결산 업무",
            "desc": "매월 말 진행되는 마감 및 분석 작업",
            "cat": "일반업무",
            "items": [
                {
                    "text": "법인카드 사용 내역 검토",
                    "desc": "불일치 내역 확인 및 사유 작성",
                    "req": 1,
                },
                {"text": "지출 결의서 최종 상신", "desc": "전자결재 승인 완료", "req": 1},
                {
                    "text": "예산 대비 집행 현황 분석",
                    "desc": "과지출 또는 미집행 항목 파악",
                    "req": 0,
                },
                {"text": "차월 예산 계획 수립", "desc": "다음 달 주요 활동 예산 배분", "req": 1},
            ],
        },
    ]

    try:
        for s in samples:
            # 템플릿 생성

            cur.execute(
                """

                INSERT INTO checklist_template (name, description, category, checklist_type, is_active)

                VALUES (?, ?, ?, ?, 1)

            """,
                (s["name"], s["desc"], s["cat"], "list"),
            )

            tid = cur.lastrowid

            # 항목 생성

            for i, item in enumerate(s["items"]):
                cur.execute(
                    """

                    INSERT INTO checklist_item (checklist_id, item_text, item_description, item_order, is_required)

                    VALUES (?, ?, ?, ?, ?)

                """,
                    (tid, item["text"], item["desc"], i, item["req"]),
                )

        conn.commit()

    except Exception as e:
        print(f"Error seeding templates: {e}")

        conn.rollback()
