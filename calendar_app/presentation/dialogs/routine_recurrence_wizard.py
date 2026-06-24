from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from calendar_app.application import routine_advanced_service as routine_service
from calendar_app.domain.policies.routine_policy import parse_recurrence_rule
from calendar_app.domain.routine_cycle import cycle_display_name
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    get_dialog_theme_tokens,
)

WIZARD_STYLE = """
    QLabel { color: #8c8c9a; font-size: 14px; border: none; background: transparent; }
    QLabel.title { color: #ffffff; font-size: 22px; font-weight: 700; margin-bottom: 10px; }
    QLabel.section_title { color: #4da6ff; font-weight: 700; font-size: 14px; margin-top: 15px; }

    QFrame.card {
        background-color: #1e1e24;
        border: 1px solid #2d2d35;
        border-radius: 10px;
        padding: 15px;
    }

    QFrame.preview_card {
        background-color: rgba(77, 166, 255, 0.1);
        border: 1px solid rgba(77, 166, 255, 0.25);
        border-radius: 10px;
    }

    QComboBox {
        background-color: #15151a; color: #ffffff;
        border: 1px solid #33333d;
        border-radius: 8px; padding: 4px 12px; font-size: 14px; min-height: 34px;
    }
    QComboBox:focus { border: 1px solid #4a4a56; background-color: #101015; }
    QComboBox::drop-down { border: none; width: 30px; }

    QPushButton {
        background-color: #2d2d35; color: #e1e1e6; font-weight: 600;
        padding: 5px 20px; border-radius: 8px; font-size: 14px; min-height: 34px;
        border: 1px solid #3d3d47;
    }
    QPushButton:hover { background-color: #383842; border-color: #4a4a56; }
    QPushButton.primary {
        background-color: #4da6ff; color: #0d0d0f; border: none; font-weight: 700;
    }
    QPushButton.primary:hover { background-color: #6eb6ff; }

    QRadioButton { color: #cacedb; font-size: 14px; spacing: 10px; }
    QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #3d3d47; background: #23232b; }
    QRadioButton::indicator:checked { border: 2px solid #35d06e; background: #35d06e; }
"""


def _apply_wizard_theme_tokens(css: str) -> str:
    tokens = get_dialog_theme_tokens()
    accent = tokens.get("accent", "#4da6ff")
    accent_hover = tokens.get("accent_hover", accent)
    surface_alt = tokens.get("surface_alt", "#1e1e24")
    surface_item = tokens.get("surface_item", "#15151a")
    surface_top = tokens.get("surface_top", "#23232b")
    surface_hover = tokens.get("surface_hover", "#101015")
    text_primary = tokens.get("text_primary", "#ffffff")
    text_secondary = tokens.get("text_secondary", "#cacedb")
    text_muted = tokens.get("text_muted", "#9aa8b8")
    border = tokens.get("border", "#3d3d47")
    border_soft = tokens.get("border_soft", "#2d2d35")
    success = tokens.get("success_hex", "#35d06e")

    replacements = {
        "#4da6ff": accent,
        "#6eb6ff": accent_hover,
        "#1e1e24": surface_alt,
        "#2d2d35": border_soft,
        "#15151a": surface_item,
        "#101015": surface_hover,
        "#3d3d47": border,
        "#23232b": surface_top,
        "#35d06e": success,
        "#9fe2a3": success,
        "#ffffff": text_primary,
        "#cacedb": text_secondary,
        "#8c8c9a": text_muted,
        "#9aa8b8": text_muted,
        "rgba(77, 166, 255, 0.1)": tokens.get("button_primary_bg", "rgba(77, 166, 255, 26)"),
        "rgba(77, 166, 255, 0.25)": tokens.get("button_primary_border", "rgba(77, 166, 255, 140)"),
    }
    for old, new in replacements.items():
        css = css.replace(old, new)
    return css


def get_cycle_labels():
    return {
        key: cycle_display_name(key, scope="recurrence")
        for key in ("weekly", "monthly", "quarterly", "half_yearly", "yearly")
    }


def get_weekday_names():
    return [
        t("weekday.mon"),
        t("weekday.tue"),
        t("weekday.wed"),
        t("weekday.thu"),
        t("weekday.fri"),
        t("weekday.sat"),
        t("weekday.sun"),
    ]


def _ordinal_name(number):
    if number == "last":
        return t("recurrence.last_week")
    return t(f"recurrence.ordinal_{number}")


def default_recurrence_config(target_date, cycle_type="monthly"):
    config = {
        "mode": "day_of_month",
        "slot": 1,
        "day": "last" if target_date.day() == target_date.daysInMonth() else target_date.day(),
        "nth": ((target_date.day() - 1) // 7) + 1,
        "weekday": target_date.dayOfWeek() - 1,
    }
    if cycle_type == "quarterly":
        config["slot"] = ((target_date.month() - 1) % 3) + 1
    elif cycle_type == "half_yearly":
        config["slot"] = ((target_date.month() - 1) % 6) + 1
    elif cycle_type == "yearly":
        config["slot"] = target_date.month()
    return config


def normalize_recurrence_config(target_date, cycle_type, recurrence):
    config = default_recurrence_config(target_date, cycle_type)
    parsed = parse_recurrence_rule(recurrence)
    if not parsed:
        return config
    config["mode"] = parsed.get("mode", config["mode"])
    if "slot" in parsed:
        config["slot"] = int(parsed["slot"])
    if "day" in parsed:
        config["day"] = int(parsed["day"]) if parsed["day"] != "last" else "last"
    if "nth" in parsed:
        config["nth"] = int(parsed["nth"]) if parsed["nth"] != "last" else "last"
    if "weekday" in parsed:
        config["weekday"] = int(parsed["weekday"])
    if cycle_type == "weekly":
        config["mode"] = "weekly"
    return config


def build_recurrence_rule(cycle_type, config):
    if cycle_type == "single":
        return "mode=single"
    if cycle_type == "weekly":
        return f"mode=weekly;weekday={config['weekday']}"
    if config["mode"] == "nth_weekday":
        return f"mode=nth_weekday;slot={config['slot']};nth={config['nth']};weekday={config['weekday']}"
    return f"mode=day_of_month;slot={config['slot']};day={config['day']}"


def cycle_slot_options(cycle_type):
    if cycle_type == "quarterly":
        return [
            (t("recurrence.quarter_1"), 1),
            (t("recurrence.quarter_2"), 2),
            (t("recurrence.quarter_3"), 3),
        ]
    if cycle_type == "half_yearly":
        return [(t("recurrence.suffix_day", n=i), i) for i in range(1, 7)]
    if cycle_type == "yearly":
        return [(t("recurrence.suffix_day", n=month), month) for month in range(1, 13)]
    return []


def recurrence_summary(target_date, cycle_type, recurrence):
    if cycle_type == "single":
        return t("recurrence.summary_single", date=target_date.toString("yyyy-MM-dd"))
    config = normalize_recurrence_config(target_date, cycle_type, recurrence)
    cycle_name = get_cycle_labels().get(cycle_type, cycle_type)
    wd_names = get_weekday_names()
    if cycle_type == "weekly":
        return t("recurrence.summary_weekly", cycle=cycle_name, weekday=wd_names[config["weekday"]])

    slot_map = dict(cycle_slot_options(cycle_type))
    slot_text = slot_map.get(config["slot"], "")
    slot_prefix = f"{slot_text} · " if slot_text else ""

    if config["mode"] == "nth_weekday":
        nth = _ordinal_name(config["nth"])
        return t(
            "recurrence.summary_nth",
            cycle=cycle_name,
            slot=slot_prefix,
            nth=nth,
            weekday=wd_names[config["weekday"]],
        )

    day_text = (
        t("recurrence.last_day")
        if config["day"] == "last"
        else t("recurrence.suffix_day", n=config["day"])
    )
    return t("recurrence.summary_day", cycle=cycle_name, slot=slot_prefix, day=day_text)


def next_occurrence_text(target_date, cycle_type, recurrence):
    if cycle_type == "single":
        return t("recurrence.no_auto")
    next_date = routine_service.calculate_next_period(
        target_date.toString("yyyy-MM-dd"), cycle_type, recurrence
    )
    return next_date or t("recurrence.cant_calc")


class RoutineRecurrenceWizard(QDialog):
    def __init__(self, target_date, cycle_type="monthly", recurrence=None, parent=None):
        super().__init__(parent)
        self.target_date = target_date or QDate.currentDate()
        self.selected_cycle_type = cycle_type or "monthly"
        self.config = normalize_recurrence_config(
            self.target_date, self.selected_cycle_type, recurrence
        )

        apply_dialog_title(self, t("recurrence.title"))
        apply_common_dialog_style(
            self,
            minimum_width=540,
            extra_stylesheet=_apply_wizard_theme_tokens(WIZARD_STYLE),
        )
        self.resize(540, 560)

        self._build_ui()
        self._apply_initial_state()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel(t("recurrence.title"))
        title.setProperty("class", "title")
        main_layout.addWidget(title)

        # 기준일 표시
        base_info = QLabel(t("recurrence.base_date", date=self.target_date.toString("yyyy-MM-dd")))
        base_info.setStyleSheet("color: #9aa8b8; font-size: 13px;")
        main_layout.addWidget(base_info)

        # 1. 반복 주기 선택 카드
        cycle_card = QFrame()
        cycle_card.setProperty("class", "card")
        cycle_layout = QVBoxLayout(cycle_card)

        sec1_title = QLabel(t("recurrence.sec_cycle"))
        sec1_title.setProperty("class", "section_title")
        cycle_layout.addWidget(sec1_title)

        self.cycle_group = QButtonGroup(self)
        cycle_row = QHBoxLayout()
        cycle_row.setContentsMargins(0, 5, 0, 5)
        for value, label in get_cycle_labels().items():
            radio = QRadioButton(label)
            radio.setProperty("cycle_value", value)
            if value == self.selected_cycle_type:
                radio.setChecked(True)
            self.cycle_group.addButton(radio)
            cycle_row.addWidget(radio)
        cycle_layout.addLayout(cycle_row)
        main_layout.addWidget(cycle_card)

        # 2. 세부 조건 설정 카드
        rule_card = QFrame()
        rule_card.setProperty("class", "card")
        rule_layout = QVBoxLayout(rule_card)

        sec2_title = QLabel(t("recurrence.sec_rule"))
        sec2_title.setProperty("class", "section_title")
        rule_layout.addWidget(sec2_title)

        form = QGridLayout()
        form.setVerticalSpacing(10)
        form.setContentsMargins(0, 5, 0, 5)

        self.rule_mode_combo = QComboBox()
        self.rule_mode_combo.addItem(t("recurrence.mode_day"), "day_of_month")
        self.rule_mode_combo.addItem(t("recurrence.mode_nth"), "nth_weekday")
        form.addWidget(QLabel(t("recurrence.label_mode")), 0, 0)
        form.addWidget(self.rule_mode_combo, 0, 1)

        self.slot_combo = QComboBox()
        self.lbl_slot = QLabel(t("recurrence.label_slot_month"))
        form.addWidget(self.lbl_slot, 1, 0)
        form.addWidget(self.slot_combo, 1, 1)

        self.day_combo = QComboBox()
        for day in range(1, 32):
            self.day_combo.addItem(t("recurrence.suffix_day", n=day), day)
        self.day_combo.addItem(t("recurrence.last_day"), "last")
        self.lbl_day = QLabel(t("recurrence.label_day"))
        form.addWidget(self.lbl_day, 2, 0)
        form.addWidget(self.day_combo, 2, 1)

        self.nth_combo = QComboBox()
        for text, value in [
            (t("recurrence.ordinal_1"), 1),
            (t("recurrence.ordinal_2"), 2),
            (t("recurrence.ordinal_3"), 3),
            (t("recurrence.ordinal_4"), 4),
            (t("recurrence.ordinal_5"), 5),
            (t("recurrence.last_week"), "last"),
        ]:
            self.nth_combo.addItem(text, value)
        self.lbl_nth = QLabel(t("recurrence.label_nth"))
        form.addWidget(self.lbl_nth, 3, 0)
        form.addWidget(self.nth_combo, 3, 1)

        self.weekday_combo = QComboBox()
        for idx, name in enumerate(get_weekday_names()):
            self.weekday_combo.addItem(name, idx)
        self.lbl_wkd = QLabel(t("recurrence.label_weekday"))
        form.addWidget(self.lbl_wkd, 4, 0)
        form.addWidget(self.weekday_combo, 4, 1)

        rule_layout.addLayout(form)
        main_layout.addWidget(rule_card)

        # 미리보기 카드
        preview_card = QFrame()
        preview_card.setProperty("class", "preview_card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(15, 12, 15, 12)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: white; font-weight: bold; font-size: 15px;")
        preview_layout.addWidget(self.summary_label)

        self.next_label = QLabel("")
        self.next_label.setStyleSheet("color: #9fe2a3; font-size: 13px;")
        preview_layout.addWidget(self.next_label)

        main_layout.addWidget(preview_card)
        main_layout.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        main_layout.addWidget(sep)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton(t("common.cancel"))
        cancel_btn.setObjectName("ghost_btn")
        cancel_btn.clicked.connect(self.reject)

        self.finish_btn = QPushButton(t("recurrence.finish"))
        self.finish_btn.setObjectName("primary_btn")
        self.finish_btn.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.finish_btn)
        main_layout.addLayout(btn_row)

        # 시그널 연결
        self.cycle_group.buttonClicked.connect(self._sync_from_controls)
        self.rule_mode_combo.currentIndexChanged.connect(self._sync_from_controls)
        self.slot_combo.currentIndexChanged.connect(self._sync_from_controls)
        self.day_combo.currentIndexChanged.connect(self._sync_from_controls)
        self.nth_combo.currentIndexChanged.connect(self._sync_from_controls)
        self.weekday_combo.currentIndexChanged.connect(self._sync_from_controls)

    def _apply_initial_state(self):
        self._populate_slot_combo()
        self._apply_config_to_controls()
        self._sync_from_controls()

    def _populate_slot_combo(self):
        options = cycle_slot_options(self.selected_cycle_type)
        current = self.slot_combo.currentData()
        self.slot_combo.blockSignals(True)
        self.slot_combo.clear()
        for text, value in options:
            self.slot_combo.addItem(text, value)
        idx = self.slot_combo.findData(current if current is not None else self.config.get("slot"))
        self.slot_combo.setCurrentIndex(idx if idx >= 0 else -1)
        self.slot_combo.blockSignals(False)

    def _apply_config_to_controls(self):
        for combo, key in [
            (self.rule_mode_combo, "mode"),
            (self.slot_combo, "slot"),
            (self.day_combo, "day"),
            (self.nth_combo, "nth"),
            (self.weekday_combo, "weekday"),
        ]:
            val = self.config.get(key)
            if key == "mode":
                val = "nth_weekday" if val == "nth_weekday" else "day_of_month"
            idx = combo.findData(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _sync_from_controls(self):
        btn = self.cycle_group.checkedButton()
        if btn:
            self.selected_cycle_type = btn.property("cycle_value")
        self._populate_slot_combo()

        self.config["mode"] = (
            "weekly" if self.selected_cycle_type == "weekly" else self.rule_mode_combo.currentData()
        )
        if self.slot_combo.count():
            self.config["slot"] = self.slot_combo.currentData()
        self.config["day"] = self.day_combo.currentData()
        self.config["nth"] = self.nth_combo.currentData()
        self.config["weekday"] = self.weekday_combo.currentData()

        # 가시성 조절
        is_weekly = self.selected_cycle_type == "weekly"
        has_slot = bool(cycle_slot_options(self.selected_cycle_type))
        is_nth = self.config["mode"] == "nth_weekday"

        self.rule_mode_combo.setEnabled(not is_weekly)
        self.lbl_slot.setVisible(has_slot)
        self.slot_combo.setVisible(has_slot)
        self.lbl_day.setVisible(not is_weekly and not is_nth)
        self.day_combo.setVisible(not is_weekly and not is_nth)
        self.lbl_nth.setVisible(not is_weekly and is_nth)
        self.nth_combo.setVisible(not is_weekly and is_nth)
        self.lbl_wkd.setVisible(is_weekly or is_nth)
        self.weekday_combo.setVisible(is_weekly or is_nth)

        recurrence = build_recurrence_rule(self.selected_cycle_type, self.config)
        self.summary_label.setText(
            recurrence_summary(self.target_date, self.selected_cycle_type, recurrence)
        )
        self.next_label.setText(
            t(
                "recurrence.next_occurrence_prefix",
                date=next_occurrence_text(self.target_date, self.selected_cycle_type, recurrence),
            )
        )

    def get_result(self):
        recurrence = build_recurrence_rule(self.selected_cycle_type, self.config)
        return {
            "cycle_type": self.selected_cycle_type,
            "recurrence": recurrence,
            "summary": recurrence_summary(self.target_date, self.selected_cycle_type, recurrence),
            "next_occurrence": next_occurrence_text(
                self.target_date, self.selected_cycle_type, recurrence
            ),
        }
