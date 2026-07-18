"""Idle-lock UI builder helpers."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.theme.style_builder import _scaled_pt


def setup_idle_lock_ui(self):
    # 자리비를 비웠을 때 활성화되는 잠금 화면 오버레이
    self._away_aux_overlays = []
    self.lock_frame = QFrame(self)
    self.lock_frame.setStyleSheet("background-color: rgba(10, 10, 10, 255);")
    self.lock_frame.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    self.lock_frame.hide()

    # 배경 이미지 레이어
    self.lock_bg_label = QLabel(self.lock_frame)
    self.lock_bg_label.setScaledContents(True)
    self.lock_bg_label.stackUnder(self.lock_frame)

    lock_lay = QVBoxLayout(self.lock_frame)
    lock_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lock_lay.setContentsMargins(24, 50, 24, 50)
    lock_lay.setSpacing(16)

    # 시계 레이블
    self.lock_clock_lbl = QLabel()
    self.lock_clock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.lock_clock_lbl.setStyleSheet(
        "color: white; font-family: 'Segoe UI Semibold', 'Malgun Gothic'; font-weight: bold;"
    )
    lock_lay.addWidget(self.lock_clock_lbl)

    # 상태 메시지 레이블
    self.lock_lbl = QLabel()
    self.lock_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.lock_lbl.setWordWrap(True)
    self.lock_lbl.setTextFormat(Qt.TextFormat.RichText)
    self.lock_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    self.lock_lbl.setMinimumWidth(320)
    lock_lay.addWidget(self.lock_lbl)

    # 비밀번호 해제 위젯 (password mode only, initially hidden)
    from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

    self.lock_pw_widget = QWidget()
    _pw_lay = QHBoxLayout(self.lock_pw_widget)
    _pw_lay.setContentsMargins(0, 0, 0, 0)
    _pw_lay.setSpacing(8)

    self.lock_pw_edit = QLineEdit()
    self.lock_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
    self.lock_pw_edit.setPlaceholderText(t("away_lock.placeholder_pw"))
    self.lock_pw_edit.setMinimumWidth(240)
    self.lock_pw_edit.setMaximumWidth(360)
    self.lock_pw_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    self.lock_pw_edit.setStyleSheet(
        "QLineEdit { background: rgba(255,255,255,0.15); color: white; "
        "border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; "
        "padding: 6px 10px; font-size: 14pt; }"
        "QLineEdit:focus { border: 1px solid #4da6ff; }"
    )
    _pw_lay.addWidget(self.lock_pw_edit)

    _lock_pw_btn = QPushButton(t("away_lock.unlock_btn"))
    _lock_pw_btn.setStyleSheet(
        "QPushButton { background: #4da6ff; color: white; border-radius: 4px; "
        "padding: 6px 18px; font-size: 14pt; font-weight: bold; border: none; }"
        "QPushButton:hover { background: #3d8fe0; }"
        "QPushButton:pressed { background: #2d7fca; }"
    )
    _pw_lay.addWidget(_lock_pw_btn)

    _lock_pw_btn.clicked.connect(lambda: self._perform_away_unlock(self.lock_pw_edit))
    self.lock_pw_edit.returnPressed.connect(lambda: self._perform_away_unlock(self.lock_pw_edit))

    self.lock_pw_widget.hide()
    lock_lay.addWidget(self.lock_pw_widget, alignment=Qt.AlignmentFlag.AlignCenter)

    # 초기 설정 반영
    if hasattr(self, "refresh_idle_lock_ui"):
        self.refresh_idle_lock_ui()
    else:
        self.lock_lbl.setText(
            self.settings.value("away_default_message", t("away_lock.default_msg"))
        )
        base_size = self.settings.value("font_size", 10, type=int)
        lock_pt = _scaled_pt(base_size, 8, 16)
        self.lock_lbl.setStyleSheet(f"color: #4da6ff; font-weight: bold; font-size: {lock_pt}pt;")

        clock_pt = _scaled_pt(base_size, 24, 48)
        self.lock_clock_lbl.setStyleSheet(
            f"color: white; font-weight: bold; font-size: {clock_pt}pt;"
        )
