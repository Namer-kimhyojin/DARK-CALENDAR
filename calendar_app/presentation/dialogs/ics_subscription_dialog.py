# -*- coding: utf-8 -*-
"""Address-first, read-only calendar subscription setup."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from calendar_app.infrastructure.i18n import t
from calendar_app.infrastructure.ics.subscriptions import normalize_subscription_url
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_collapsible_section,
    build_dialog_footer,
)


class IcsSubscriptionDialog(QDialog):
    def __init__(self, parent=None, *, calendar=None):
        super().__init__(parent)
        self._editing = bool(calendar)
        self._name_error = False
        self.subscription_name = self.subscription_url = ""
        title = (
            t("sync_redesign.subscription_edit_title", "구독 주소 · 이름 수정")
            if self._editing
            else t("sync_redesign.subscription_add_title", "주소로 캘린더 구독")
        )
        apply_dialog_title(self, title)
        self.setAccessibleName(title)
        self.setObjectName("IcsSubscriptionDialog")
        settings = getattr(parent, "settings", None)
        if settings is None:
            settings = getattr(getattr(parent, "app", None), "settings", None)
        theme_options = {}
        if settings is not None:
            theme_options = {
                "theme_color": settings.value("theme_color", "#4da6ff", type=str),
                "text_theme": settings.value("text_theme", "dark", type=str),
                "panel_base_color": settings.value("panel_base_color", "#0d1b2e", type=str),
            }
        apply_common_dialog_style(self, minimum_width=600, size=(640, 540), **theme_options)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        heading = self._label(title, role="dialogTitle")
        root.addWidget(heading)
        intro = self._label(
            t(
                "sync_redesign.subscription_intro",
                "캘린더 서비스에서 복사한 iCal · ICS 주소로 일정을 가져옵니다.",
            ),
            role="dialogSubtitle",
        )
        root.addWidget(intro)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setAutoFillBackground(False)
        self.scroll_area.setMinimumHeight(340)
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(12)
        self.scroll_area.setWidget(body)
        body.setAutoFillBackground(False)
        root.addWidget(self.scroll_area, 1)
        behavior = self._label(
            t(
                "sync_redesign.subscription_behavior",
                "읽기 전용 · Google 로그인 불필요\n자동 동기화를 켜면 앱 실행 중 1시간마다 새 일정을 확인합니다.",
            ),
            role="syncSubscriptionInfo",
        )
        form.addWidget(behavior)
        if self._editing:
            form.addWidget(
                self._label(
                    t(
                        "sync_redesign.subscription_edit_hint",
                        "주소를 바꿔도 기존 일정·색상·표시 설정을 유지합니다. 새 주소를 성공적으로 가져오면 일정이 갱신됩니다.",
                    ),
                    role="field_hint",
                )
            )

        url_label = self._label(
            t("sync_redesign.subscription_address_label", "1. 구독 주소 (필수)")
        )
        self.url = QLineEdit()
        self.url.setMaxLength(8192)
        self.url.setObjectName("subscription_url")
        self.url.setPlaceholderText(
            t(
                "sync_redesign.subscription_address_placeholder",
                "https://… 또는 webcal://… 구독 주소",
            )
        )
        self.url.setAccessibleName(url_label.text())
        self.url.setAccessibleDescription(
            t(
                "sync_redesign.subscription_address_help",
                "캘린더 웹페이지가 아닌 iCal · ICS 구독 주소를 입력하세요. HTTP · HTTPS · webcal 주소를 지원합니다.",
            )
        )
        url_label.setBuddy(self.url)
        form.addWidget(url_label)
        address_row = QHBoxLayout()
        address_row.setSpacing(8)
        address_row.addWidget(self.url, 1)
        self.paste_button = QPushButton(t("sync_redesign.subscription_paste", "붙여넣기"))
        self.paste_button.setObjectName("ghost_btn")
        self.paste_button.setAutoDefault(False)
        self.paste_button.setAccessibleName(
            t("sync_redesign.subscription_paste_accessible", "복사한 구독 주소 붙여넣기")
        )
        self.paste_button.clicked.connect(self._paste_url)
        address_row.addWidget(self.paste_button)
        form.addLayout(address_row)
        self.feedback = self._label("", role="field_hint")
        self.feedback.setObjectName("subscription_feedback")
        form.addWidget(self.feedback)

        name_label = self._label(
            t("sync_redesign.subscription_name_label", "2. 캘린더 이름 (필수)")
        )
        self.name = QLineEdit()
        self.name.setMaxLength(200)
        self.name.setObjectName("subscription_name")
        self.name.setPlaceholderText(
            t("sync_redesign.subscription_name_placeholder", "예: 가족 일정, 회사 휴일")
        )
        self.name.setAccessibleName(name_label.text())
        name_hint = t(
            "sync_redesign.subscription_name_help",
            "Air Calendar에서 구분하기 쉬운 이름을 정하세요. 나중에 바꿀 수 있습니다.",
        )
        self.name.setAccessibleDescription(name_hint)
        name_label.setBuddy(self.name)
        form.addWidget(name_label)
        form.addWidget(self.name)
        self.name_feedback = self._label("", role="field_error")
        self.name_feedback.setObjectName("subscription_name_feedback")
        self.name_feedback.hide()
        form.addWidget(self.name_feedback)
        form.addWidget(self._label(name_hint, role="field_hint"))

        self.guide_content = self._build_address_guide()
        guide, self.guide_toggle = build_collapsible_section(
            t("sync_redesign.subscription_find_address", "구독 주소는 어디에서 찾나요?"),
            self.guide_content,
            expanded=False,
        )
        self.guide_toggle.setAutoDefault(False)
        self.guide_toggle.setAccessibleName(
            t("sync_redesign.subscription_find_address", "구독 주소는 어디에서 찾나요?")
        )
        form.addLayout(guide)
        form.addStretch(1)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(separator)
        footer, self.submit_button, self.cancel_button = build_dialog_footer(
            ok_label=(
                t("sync_redesign.subscription_save", "변경 저장")
                if self._editing
                else t("sync_redesign.subscription_add", "구독 추가")
            ),
            cancel_label=t("common.cancel", "취소"),
        )
        self.submit_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        root.addLayout(footer)

        if calendar:
            self.name.setText(calendar.get("name") or "")
            self.url.setText(calendar.get("ics_url") or "")
        self.url.textChanged.connect(self._validate_address)
        self.name.textChanged.connect(self._name_changed)
        self._validate_address()
        self.setTabOrder(self.url, self.paste_button)
        self.setTabOrder(self.paste_button, self.name)
        self.setTabOrder(self.name, self.guide_toggle)
        self.setTabOrder(self.guide_toggle, self.cancel_button)
        self.setTabOrder(self.cancel_button, self.submit_button)
        self.url.setFocus()
        self.resize(640, 540)

    @staticmethod
    def _label(text, *, role=None):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if role:
            label.setProperty("role", role)
        return label

    def _build_address_guide(self):
        guide = QWidget()
        guide.setObjectName("subscription_address_guide")
        layout = QVBoxLayout(guide)
        layout.setContentsMargins(12, 8, 12, 4)
        layout.setSpacing(10)
        entries = (
            (
                t("sync_ui.google", "Google Calendar"),
                t(
                    "sync_redesign.subscription_guide_google",
                    "웹 캘린더 설정 → 내 캘린더 선택 → 캘린더 통합 → iCal 형식의 비공개 주소를 복사하세요. 공개 캘린더는 iCal 형식의 공개 주소를 사용할 수 있습니다.",
                ),
            ),
            (
                t("sync_ui.outlook", "Outlook"),
                t(
                    "sync_redesign.subscription_guide_outlook",
                    "Outlook 웹 설정 → 캘린더 → 공유 캘린더 → 캘린더 게시에서 ICS 링크를 복사하세요. 조직 정책에 따라 게시 기능이 없을 수 있습니다.",
                ),
            ),
            (
                t("sync_ui.icloud", "iCloud"),
                t(
                    "sync_redesign.subscription_guide_icloud",
                    "iCloud 웹 캘린더에서 캘린더 공유 → 공개 캘린더 → 링크 복사를 선택하세요. webcal 주소도 사용할 수 있습니다.",
                ),
            ),
        )
        for provider, instructions in entries:
            layout.addWidget(self._label(provider, role="syncSubscriptionGuideTitle"))
            layout.addWidget(self._label(instructions, role="field_hint"))
        layout.addWidget(
            self._label(
                t(
                    "sync_redesign.subscription_private_address",
                    "비공개 구독 주소를 아는 사람은 일정을 볼 수 있습니다. 본인의 주소를 다른 사람에게 공유하지 마세요.",
                ),
                role="field_hint",
            )
        )
        return guide

    @staticmethod
    def _set_field_state(field, state):
        field.setProperty("state", state)
        field.style().unpolish(field)
        field.style().polish(field)
        field.update()

    def _set_feedback(self, text, state):
        self.feedback.setText(text)
        self.feedback.setProperty("validationState", state)
        self.feedback.setProperty("role", "field_error" if state == "invalid" else "field_hint")
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)

    def _validate_address(self, _text=None):
        value = self.url.text().strip()
        if not value:
            self._set_field_state(self.url, "")
            self._set_feedback(self.url.accessibleDescription(), "empty")
        else:
            try:
                normalize_subscription_url(value)
            except ValueError:
                self._set_field_state(self.url, "error")
                self._set_feedback(
                    t(
                        "sync_redesign.subscription_address_invalid",
                        "주소 형식을 확인하세요. HTTP · HTTPS · webcal로 시작하는 구독 주소가 필요합니다.",
                    ),
                    "invalid",
                )
            else:
                self._set_field_state(self.url, "success")
                self._set_feedback(
                    t(
                        "sync_redesign.subscription_address_valid",
                        "주소 형식이 올바릅니다. 실제 연결 결과는 구독을 가져온 뒤 확인할 수 있습니다.",
                    ),
                    "valid",
                )
        self._update_submit_state()

    def _name_changed(self, _text=None):
        if self._name_error and self.name.text().strip():
            self._name_error = False
            self.name_feedback.hide()
            self._set_field_state(self.name, "")
            self._validate_address()
        self._update_submit_state()

    def _update_submit_state(self):
        try:
            normalize_subscription_url(self.url.text())
            address_valid = True
        except ValueError:
            address_valid = False
        enabled = address_valid and bool(self.name.text().strip())
        self.submit_button.setEnabled(enabled)
        self.submit_button.setToolTip(
            ""
            if enabled
            else t(
                "sync_redesign.subscription_required_fields",
                "구독 주소와 캘린더 이름을 입력하면 계속할 수 있습니다.",
            )
        )

    def _paste_url(self):
        value = QApplication.clipboard().text().strip()
        if not value:
            self._set_feedback(
                t(
                    "sync_redesign.subscription_clipboard_empty",
                    "복사된 주소가 없습니다. 캘린더 서비스에서 구독 주소를 먼저 복사하세요.",
                ),
                "clipboard_empty",
            )
            self.url.setFocus()
            return
        if len(value) > self.url.maxLength():
            self._set_feedback(
                t(
                    "sync_redesign.subscription_address_too_long",
                    "주소가 너무 길어 붙여넣지 못했습니다. 캘린더 서비스에서 구독 주소를 다시 복사하세요.",
                ),
                "paste_rejected",
            )
            self.url.setFocus()
            return
        self.url.setText(value)
        self.url.setCursorPosition(0)
        self.url.setFocus()
        self._validate_address()

    def accept(self):
        name = self.name.text().strip()
        if not name:
            message = t("sync_unified.name_required", "캘린더 이름을 입력하세요.")
            self._name_error = True
            self.name_feedback.setText(message)
            self.name_feedback.show()
            self._set_field_state(self.name, "error")
            self._set_feedback(message, "invalid")
            self.name.setFocus()
            return
        try:
            url = normalize_subscription_url(self.url.text())
        except ValueError:
            self._set_field_state(self.url, "error")
            self._set_feedback(
                t(
                    "sync_unified.invalid_ics",
                    "HTTP · HTTPS · webcal 캘린더 구독 주소를 입력하세요.",
                ),
                "invalid",
            )
            self.url.setFocus()
            return
        self.subscription_name, self.subscription_url = name, url
        super().accept()
