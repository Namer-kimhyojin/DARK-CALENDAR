# -*- coding: utf-8 -*-
"""Batch C (misc) i18n fixes: checklist seeds, text-widget presets and small dialog texts.

The new keys reach locales/*.json only in the integration step, so these tests pass
with the Korean defaults today and after the keys are added: they check that each
text is looked up through t() and that no Hangul literal bypasses it.
"""

import re
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from PyQt6.QtWidgets import QApplication, QFrame, QToolButton
import pytest

from calendar_app.infrastructure.db import checklist_template_repo as repo
from calendar_app.infrastructure.i18n import i18n, t
from calendar_app.presentation.dialogs import checklist_manager_dialog_advanced as checklist_ui
from calendar_app.presentation.dialogs import directive_dialog, management_dialogs
from calendar_app.presentation.dialogs import widget_style_editor_dialog as style_editor
from calendar_app.presentation.widgets import overlay_base
from calendar_app.presentation.widgets.overlay_template_validation import (
    validate_widget_template,
)
from tests.support import TemporaryDatabaseTestCase

HANGUL = re.compile(r"[가-힣]")

# Today's first-run templates (name, description, internal category, items).
EXPECTED_KO_SEED = [
    (
        "주간 업무 보고",
        "매주 금요일 정기적으로 실행하는 주간 보고 절차",
        "일반업무",
        (
            ("전주 업무 실적 요약", "완료된 과업 및 성과 정리", 1),
            ("금주 업무 계획 작성", "차주 주요 마일스톤 및 일정 수립", 1),
            ("주요 이슈 및 건의사항 정리", "병목 현상이나 지원 필요 사항 기술", 0),
            ("팀원 공유 및 피드백 반영", "최종 제출 전 팀 내 리뷰", 1),
        ),
    ),
    (
        "회의 준비 및 세팅",
        "성공적인 회의를 위한 사전 준비 체크리스트",
        "일정",
        (
            ("회의 목적 및 안건 확정", "Agenda 명확화 및 참석자 공유", 1),
            ("참석자 일정 확인 및 초대 전송", "캘린더 초대장 발송 확인", 1),
            ("회의실 예약 및 환경 점검", "빔프로젝터, 마이크, 다과 등 준비", 1),
            ("회의 자료 인쇄 및 사전 배포", "참석자 숙지용 자료 전달", 0),
        ),
    ),
    (
        "출장 정산 및 보고",
        "출장 복귀 후 진행하는 행정 처리 절차",
        "일정",
        (
            ("영수증 수집 및 정리", "교통비, 숙박비, 식비 등 증빙 확보", 1),
            ("출장 결과 보고서 작성", "방문 목적 달성 여부 및 핵심 정보 요약", 1),
            ("ERP/경비 시스템 입력", "비용 지급 신청 완료", 1),
            ("증빙 서류 제출", "회계팀 실물 영수증 전달(해당 시)", 0),
        ),
    ),
    (
        "신규 입사자 온보딩 가이드",
        "팀에 합류한 신규 멤버를 위한 초기 셋팅",
        "일반업무",
        (
            ("IT 장비 지급 및 계정 생성", "PC, 이메일, 사내망 권한 확인", 1),
            ("부서원 인사 및 자리 안내", "팀 내 문화 및 주변 환경 소개", 1),
            ("협업 툴(메신저, 위키) 초대", "Slack, Notion, Jira 등 접근 권한 부여", 1),
            ("필수 보안/윤리 교육 이수 안내", "사내 규정 및 법정 필수 교육 가이드", 1),
        ),
    ),
    (
        "월간 결산 업무",
        "매월 말 진행되는 마감 및 분석 작업",
        "일반업무",
        (
            ("법인카드 사용 내역 검토", "불일치 내역 확인 및 사유 작성", 1),
            ("지출 결의서 최종 상신", "전자결재 승인 완료", 1),
            ("예산 대비 집행 현황 분석", "과지출 또는 미집행 항목 파악", 0),
            ("차월 예산 계획 수립", "다음 달 주요 활동 예산 배분", 1),
        ),
    ),
]


def _recording_t(calls):
    def recording_t(key, default=None, **kwargs):
        calls.append((key, default))
        return f"<{key}>"

    return recording_t


def _seeded_rows():
    conn = repo.get_connection()
    templates = conn.execute(
        "SELECT id, name, description, category, checklist_type FROM checklist_template ORDER BY id"
    ).fetchall()
    rows = []
    for template in templates:
        items = conn.execute(
            "SELECT item_text, item_description, is_required FROM checklist_item "
            "WHERE checklist_id=? ORDER BY item_order",
            (template["id"],),
        ).fetchall()
        rows.append(
            (
                template["name"],
                template["description"],
                template["category"],
                tuple((item[0], item[1], item[2]) for item in items),
            )
        )
    return rows


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


# --- M2: checklist seeds and import name --------------------------------------------


class TestChecklistSeed(TemporaryDatabaseTestCase):
    def test_korean_seed_matches_todays_templates(self):
        repo.seed_default_templates()

        assert _seeded_rows() == EXPECTED_KO_SEED
        conn = repo.get_connection()
        types = {row[0] for row in conn.execute("SELECT checklist_type FROM checklist_template")}
        assert types == {"list"}

    def test_every_visible_seed_text_comes_from_a_seed_key(self):
        calls = []
        with patch.object(repo, "t", _recording_t(calls)):
            samples = repo._default_template_samples()

        keys = [key for key, _default in calls]
        assert len(keys) == len(set(keys)) == 50
        assert all(key.startswith("checklist_mgr.seed.") for key in keys)
        # The Korean defaults are exactly today's literals, in order.
        expected_defaults = []
        for name, desc, _category, items in EXPECTED_KO_SEED:
            expected_defaults += [name, desc]
            for text, detail, _required in items:
                expected_defaults += [text, detail]
        assert [default for _key, default in calls] == expected_defaults
        for sample in samples:
            visible = [sample["name"], sample["desc"]]
            visible += [part for item in sample["items"] for part in (item["text"], item["desc"])]
            assert all(text.startswith("<checklist_mgr.seed.") for text in visible)

    def test_seed_with_english_translations_has_no_hangul(self):
        calls = []
        with patch.object(repo, "t", _recording_t(calls)):
            repo._default_template_samples()
        english = {key: f"English sample {index}" for index, (key, _d) in enumerate(calls)}

        with patch.dict(i18n.translations, english):
            repo.seed_default_templates()

        rows = _seeded_rows()
        assert len(rows) == 5
        for name, desc, _category, items in rows:
            visible = [name, desc] + [part for item in items for part in item[:2]]
            assert not any(HANGUL.search(text) for text in visible), visible
        # Categories are internal identifiers (never displayed) and stay unchanged.
        assert [row[2] for row in rows] == [row[2] for row in EXPECTED_KO_SEED]

    def test_seed_leaves_existing_user_rows_alone(self):
        template_id = repo.create_checklist_template("내 목록", category="공통")

        repo.seed_default_templates()

        templates = repo.get_all_checklist_templates()
        assert [row["id"] for row in templates] == [template_id]
        assert templates[0]["name"] == "내 목록"

    def test_import_without_a_name_stores_the_translated_default(self):
        payload = {"template": {"checklist_type": "list"}, "items": [{"item_text": "A"}]}

        template_id = repo.import_checklist_template(payload)

        assert repo.get_checklist_template(template_id)["name"] == "가져온 체크리스트"
        with patch.dict(i18n.translations, {"checklist_mgr.import_default_name": "Imported"}):
            other_id = repo.import_checklist_template(payload)
        assert repo.get_checklist_template(other_id)["name"] == "Imported"

    def test_import_message_names_the_stored_default(self):
        filename = self._tmpdir.name + "/import.json"
        with open(filename, "w", encoding="utf-8", errors="strict") as stream:
            stream.write('{"template": {"checklist_type": "list"}, "items": []}')
        owner = SimpleNamespace(
            current_template_id=None,
            load_templates=Mock(),
            _select_template_in_list=Mock(),
            checklist_changed=SimpleNamespace(emit=Mock()),
        )
        with (
            patch.object(checklist_ui.QFileDialog, "getOpenFileName", return_value=(filename, "")),
            patch.object(checklist_ui.QMessageBox, "information") as success,
            patch.object(checklist_ui.QMessageBox, "critical") as error,
        ):
            checklist_ui.ChecklistManagerDialog._import_template(owner)

        error.assert_not_called()
        stored = repo.get_checklist_template(owner.current_template_id)["name"]
        assert stored == "가져온 체크리스트"
        assert success.call_args.args[2] == t("checklist_mgr.import_done_msg", name=stored)


# --- L11: file-dialog filters ---------------------------------------------------------


def test_checklist_file_filters_are_translated_and_keep_the_pattern():
    owner = SimpleNamespace()
    calls = []
    with (
        patch.object(checklist_ui, "t", _recording_t(calls)),
        patch.object(checklist_ui.QFileDialog, "getOpenFileName", return_value=("", "")) as dialog,
    ):
        checklist_ui.ChecklistManagerDialog._import_template(owner)

    assert dialog.call_args.args[3] == "<common.file_filter_json>"
    assert ("common.file_filter_json", "JSON 파일 (*.json)") in calls
    assert t("common.file_filter_json", "JSON 파일 (*.json)").endswith("(*.json)")


# --- L33: text-widget presets ---------------------------------------------------------


def _text_presets(translate):
    return dict(overlay_base._get_widget_presets("text", translate))


def test_text_preset_bodies_are_looked_up_through_t(monkeypatch):
    monkeypatch.setattr(overlay_base, "_text_engine_has_tz_label", lambda: False)
    monkeypatch.setattr(overlay_base, "_local_timezone_label", lambda: "ZZT")
    seen = []

    def translate(key, fallback):
        seen.append(key)
        return f"<{key}>"

    presets = _text_presets(translate)

    assert {
        "widget_text.preset_body.tasks",
        "widget_text.preset_body.no_tasks_today",
        "widget_text.preset_body.ending_soon",
    } <= set(seen)
    conditional = presets["<widget_text.preset_conditional_task>"]
    assert "<widget_text.preset_body.tasks> {task_count" in conditional
    assert "{else}<widget_text.preset_body.no_tasks_today>{/if}" in conditional
    assert (
        "\n<widget_text.preset_body.tasks> {task_count" in presets["<widget_text.preset_dashboard>"]
    )
    assert "[[ending_soon]]" not in presets["<widget_text.preset_countdown_alert>"]
    assert (
        "<widget_text.preset_body.ending_soon>" in presets["<widget_text.preset_countdown_alert>"]
    )
    world = presets["<widget_text.preset_world_time>"]
    assert world.startswith("{time:%H:%M|size=28|bold}  ZZT\n")
    for template in presets.values():
        assert "[[" not in template
        assert not validate_widget_template("text", template)


def test_text_presets_use_korean_defaults_and_no_fixed_english_or_kst(monkeypatch):
    # A machine in Korea may report "KST" as its real abbreviation; only a fixed one is wrong.
    monkeypatch.setattr(overlay_base, "_local_timezone_label", lambda: "ZZT")
    presets = _text_presets(lambda _key, fallback: fallback)
    joined = "\n".join(presets.values())

    assert "{if task_count > 0}할 일 {task_count" in joined
    assert "{else}오늘 할 일 없음{/if}" in joined
    assert "{if countdown:countdown_0 < 1h}곧 종료!{else}" in joined
    for literal in ("Tasks ", "No tasks today", "KST"):
        assert literal not in joined
    for entry in overlay_base._PRESET_FALLBACK["text"]:
        assert "KST" not in entry["template"]
        assert not HANGUL.search(entry["template"])


def test_world_time_preset_uses_live_tz_token_once_the_text_engine_accepts_it(monkeypatch):
    from calendar_app.presentation.widgets import overlay_template_validation as validation

    text_rules = validation._VARIABLE_RULES["text"]
    monkeypatch.setitem(text_rules, "plain", text_rules["plain"] | {"tz_label"})
    monkeypatch.setattr(overlay_base, "_local_timezone_label", lambda: "ZZT")

    assert overlay_base._text_engine_has_tz_label()
    world = _text_presets(lambda key, _fallback: f"<{key}>")["<widget_text.preset_world_time>"]
    assert world.startswith("{time:%H:%M|size=28|bold}  {tz_label}\n")
    assert "ZZT" not in world
    assert not validate_widget_template("text", world)


def test_text_widget_resolves_tz_label_at_render_time(monkeypatch):
    from calendar_app.presentation.widgets import overlay_text
    from calendar_app.presentation.widgets.overlay_text import OverlayTextWidget

    assert overlay_base._text_engine_has_tz_label()
    assert "tz_label" in OverlayTextWidget._SLOW_VARS
    context = SimpleNamespace(
        _process_conditionals=overlay_base._BaseOverlayWidget._process_conditionals,
        _RE_UTC_OFFSET=OverlayTextWidget._RE_UTC_OFFSET,
    )
    for label in ("ZZT", "UTC-3"):
        monkeypatch.setattr(overlay_text, "_local_timezone_label", lambda value=label: value)
        rendered = OverlayTextWidget.resolve_template(
            context, override_text="{tz_label|size=12|color=muted}"
        )
        assert label in rendered
        assert "tz_label" not in rendered


def test_local_timezone_label_is_short():
    label = overlay_base._local_timezone_label()
    assert re.fullmatch(r"[A-Z]{2,5}|UTC[+-]\d{1,2}(:\d\d)?", label), label


def test_preset_slots_without_a_key_stay_visible_and_user_templates_are_untouched():
    fill = overlay_base._fill_preset_text_slots
    translate = Mock(side_effect=lambda key, fallback: fallback)

    assert fill("{time:%H:%M} Tasks", None, translate) == "{time:%H:%M} Tasks"
    assert fill("[[unknown]]", {}, translate) == "[[unknown]]"
    translate.assert_not_called()


# --- L11: "Hint" prefix ---------------------------------------------------------------


def test_hint_toggle_text_comes_only_from_t(app, monkeypatch):
    calls = []
    monkeypatch.setattr(overlay_base, "t", _recording_t(calls))
    fake = SimpleNamespace(_make_hint_box=lambda parent, text: QFrame(parent))

    container = overlay_base._BaseOverlayWidget._make_collapsible_hint(fake, None, "body")
    try:
        button = container.findChild(QToolButton)
        assert button.text() == "<widget.common.hint_label>  >"
        button.click()
        assert button.text() == "<widget.common.hint_label>  v"
        assert ("widget.common.hint_label", "문법 힌트") in calls
    finally:
        container.deleteLater()


# --- L13: trash back buttons ----------------------------------------------------------


def test_trash_back_buttons_use_one_key_per_dialog(monkeypatch):
    monkeypatch.setattr(management_dialogs, "t", _recording_t([]))
    texts = {}
    for name in ("DirectiveManagementDialog", "TaskManagementDialog", "RoutineManagementDialog"):
        owner = MagicMock()
        getattr(management_dialogs, name)._sync_trash_mode_ui(owner)
        texts[name] = owner._sync_common_trash_mode_ui.call_args.kwargs["toggle_text_trash"]

    assert texts == {
        "DirectiveManagementDialog": "<dialog.management.btn_toggle_trash_back_directive>",
        "TaskManagementDialog": "<dialog.management.btn_toggle_trash_back>",
        "RoutineManagementDialog": "<dialog.management.btn_toggle_trash_back_routine>",
    }


def test_trash_back_buttons_name_their_own_items_in_korean():
    texts = []
    for name in ("DirectiveManagementDialog", "TaskManagementDialog", "RoutineManagementDialog"):
        owner = MagicMock()
        getattr(management_dialogs, name)._sync_trash_mode_ui(owner)
        texts.append(owner._sync_common_trash_mode_ui.call_args.kwargs["toggle_text_trash"])

    assert texts == ["지시/협조사항 보기", "일정 보기", "일반업무 보기"]


# --- L10: directive dialog init error ---------------------------------------------------


def test_directive_init_error_is_translated(app, monkeypatch):
    calls = []
    monkeypatch.setattr(directive_dialog, "t", _recording_t(calls))
    monkeypatch.setattr(
        directive_dialog.DirectiveDialog, "init_ui", Mock(side_effect=RuntimeError("boom"))
    )
    with patch.object(directive_dialog.QMessageBox, "critical") as critical:
        dialog = directive_dialog.DirectiveDialog()
    try:
        assert critical.call_args.args[2] == "<dialog.directive.msg_init_error>"
        assert (
            "dialog.directive.msg_init_error",
            "지시사항 다이얼로그 초기화 중 오류가 발생했습니다.",
        ) in calls
    finally:
        dialog.deleteLater()


# --- L12: empty widget style name -------------------------------------------------------


@pytest.mark.parametrize("tab, name", [(0, ""), (0, "   "), (1, "")])
def test_empty_style_name_shows_a_translated_message(app, monkeypatch, tab, name):
    create_skin = Mock()
    create_layout = Mock()
    monkeypatch.setattr(style_editor, "create_user_widget_skin", create_skin)
    monkeypatch.setattr(style_editor, "create_user_widget_layout", create_layout)
    dialog = style_editor.WidgetStyleEditorDialog()
    try:
        dialog.tabs.setCurrentIndex(tab)
        (dialog.skin_name if tab == 0 else dialog.layout_name).setText(name)
        english = {"widget_mode.editor_name_required": "Enter a name."}
        with (
            patch.dict(i18n.translations, english),
            patch.object(style_editor.QMessageBox, "warning") as warning,
        ):
            dialog._save()

        assert warning.call_args.args[2] == "Enter a name."
        create_skin.assert_not_called()
        create_layout.assert_not_called()
        assert dialog.result() == 0
    finally:
        dialog.deleteLater()


def test_empty_style_name_message_defaults_to_korean_not_the_model_error(app, monkeypatch):
    monkeypatch.setattr(style_editor, "create_user_widget_skin", Mock())
    dialog = style_editor.WidgetStyleEditorDialog()
    try:
        with patch.object(style_editor.QMessageBox, "warning") as warning:
            dialog._save()
        message = warning.call_args.args[2]
        assert message == t("widget_mode.editor_name_required", "이름을 입력하세요.")
        assert "required" not in message
    finally:
        dialog.deleteLater()


def test_other_style_save_errors_lead_with_a_translated_message(app, monkeypatch):
    monkeypatch.setattr(
        style_editor, "create_user_widget_skin", Mock(side_effect=OSError("disk full"))
    )
    dialog = style_editor.WidgetStyleEditorDialog()
    try:
        dialog.skin_name.setText("Mine")
        with patch.object(style_editor.QMessageBox, "warning") as warning:
            dialog._save()
        first_line, detail = warning.call_args.args[2].split("\n", 1)
        assert first_line == t(
            "widget_mode.save_failed", "저장하지 못했습니다. 다시 시도해 주세요."
        )
        assert detail == "disk full"
    finally:
        dialog.deleteLater()
