from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSlider, QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.main_window.dock_factory import setup_body_and_docks
from calendar_app.presentation.main_window.idle_lock_ui_builder import (
    setup_idle_lock_ui,  # noqa: F401
)
from calendar_app.presentation.main_window.top_bar_builder import setup_top_bar
from calendar_app.presentation.main_window.window_restore_helpers import (
    restore_window_and_bind_menu_state,
    setup_size_grip,
)
from calendar_app.presentation.theme.style_builder import (
    _hex_to_rgba,
    build_global_stylesheet,
    build_tooltip_stylesheet,
)
from calendar_app.shared.theme_settings import get_opacity_byte
from calendar_app.shared.theme_snapshot import build_theme_snapshot


def setup_main_ui(self):
    # 바탕화면 오버레이 창 설정 (항상 아래, 프레임 제거, 투명 배경)
    self.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.Tool
        | Qt.WindowType.WindowStaysOnBottomHint
    )
    self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    self.setWindowOpacity(1.0)

    # 저장된 폰트 설정 로드
    _family = self.settings.value("font_family", "Segoe UI")
    _size = self.settings.value("font_size", 10, type=int)
    if _size <= 0:
        _size = 10
        self.settings.setValue("font_size", _size)

    snapshot = build_theme_snapshot(self.settings, persist_opacity=True)
    _theme = snapshot.theme_color

    # rgba 변환 헬퍼 (alpha: 0~255 정수)
    def _ta(a):
        return _hex_to_rgba(_theme, round(a / 255, 3))

    # 전역 폰트 및 툴팁 스타일 설정 (애플리케이션 단위)
    from PyQt6.QtWidgets import QApplication

    app_instance = QApplication.instance()
    if app_instance:
        app_instance.setStyleSheet(
            build_tooltip_stylesheet(
                _size,
                snapshot.theme_color,
                snapshot.text_theme,
                snapshot.panel_base_color,
                snapshot.ui_palette,
            )
        )

    self.setStyleSheet(
        build_global_stylesheet(
            _family,
            _size,
            snapshot.theme_color,
            snapshot.text_theme,
            snapshot.panel_base_color,
            snapshot.ui_palette,
        )
    )

    self.slider = QSlider(Qt.Orientation.Horizontal)
    self.slider.setRange(0, 255)
    _raw_op = get_opacity_byte(self.settings, persist_normalized=True)
    self.slider.setValue(_raw_op)
    self.slider.setFixedWidth(80)
    self.slider.valueChanged.connect(self.set_opacity)
    self.slider.sliderReleased.connect(self.finalize_opacity_change)
    self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
    self.slider.setToolTip(t("topbar.opacity_tooltip"))
    self.slider.setStyleSheet(
        f"""
        QSlider {{
            background: transparent;
        }}
        QSlider::groove:horizontal {{
            height: 4px; background: rgba(255,255,255,25); border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {_theme}; border: 2px solid {_ta(204)};
            width: 12px; height: 12px; margin: -4px 0;
            border-radius: 7px;
        }}
        QSlider::handle:horizontal:hover {{
            background: white; border: 2px solid {_theme};
        }}
        QSlider::sub-page:horizontal {{
            background: {_ta(128)}; border-radius: 2px;
        }}
    """
    )

    setup_top_bar(self, _size, _theme, _ta)

    # top_bar_frame을 QMainWindow 최상단에 고정.
    # 하단 패널과의 간격 3px를 위해 wrapper로 감쌈.
    from PyQt6.QtWidgets import QVBoxLayout as _VBox

    _menu_wrapper = QWidget()
    _vbox = _VBox(_menu_wrapper)
    _vbox.setContentsMargins(0, 0, 0, 3)
    _vbox.setSpacing(0)
    _vbox.addWidget(self.top_bar_frame)
    self._top_bar_menu_wrapper = _menu_wrapper
    self.setMenuWidget(_menu_wrapper)

    # 입력 차단용 투명 오버레이
    self.lock_overlay = QWidget(self)
    self.lock_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    self.lock_overlay.hide()

    setup_body_and_docks(self, _theme)
    restore_window_and_bind_menu_state(self)
    setup_size_grip(self)

    # 저장된 자석 모드 복원 (초기 복원 시 토스트 미표시)
    if hasattr(self, "magnet_btn"):
        self.toggle_magnet_mode(show_toast=False)

    # UI 빌드 완료 — 이후 set_opacity가 apply_theme_settings를 호출해도 안전
    self._ui_fully_initialized = True
    # 초기 투명도 설정은 하위 메뉴 포함 전체 적용
    self.set_opacity(self.slider.value())
