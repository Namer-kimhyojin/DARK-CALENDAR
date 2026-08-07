# -*- coding: utf-8 -*-
"""Calendar print setup, preview, native printing, and PDF export."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtPrintSupport import (
    QPrintDialog,
    QPrinter,
    QPrintPreviewDialog,
    QPrintPreviewWidget,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from calendar_app.application.calendar_print_service import (
    CalendarPrintRequest,
    build_calendar_print_document,
)
from calendar_app.infrastructure.db.calendar_print_repository import (
    load_calendar_print_source,
)
from calendar_app.infrastructure.db.calendar_repo import list_calendars
from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.dialogs.dialog_emoji import apply_dialog_title
from calendar_app.presentation.dialogs.dialog_styles import (
    apply_common_dialog_style,
    build_dialog_footer,
)
from calendar_app.presentation.printing.calendar_print_renderer import (
    CalendarPrintRenderOptions,
    configure_printer,
    render_calendar_document,
)


def _color_icon(color_value: str, size: int = 12) -> QIcon:
    color = QColor(str(color_value or "#4d7cff"))
    if not color.isValid():
        color = QColor("#4d7cff")
    pixmap = QPixmap(size, size)
    pixmap.fill(color)
    return QIcon(pixmap)


def _qdate_to_date(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def _date_to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _start_of_week(value: date, start_monday: bool) -> date:
    offset = value.weekday() if start_monday else (value.weekday() + 1) % 7
    return value - timedelta(days=offset)


class CalendarPrintDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.settings = app.settings
        self._calendar_rows = list_calendars(include_inactive=False)
        self._last_preview_error = ""
        self._applying_output_preset = False
        self._loading_settings = False
        apply_dialog_title(self, t("print.title", "캘린더 인쇄"))
        apply_common_dialog_style(self, minimum_width=760, size=(820, 720))
        self.setAccessibleName(t("print.accessible_name", "캘린더 인쇄 설정"))
        self._build_ui()
        self._load_settings()
        self._update_scope_state()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)

        title = QLabel(t("print.heading", "캘린더 출력 설정"))
        title.setObjectName("dialogTitle")
        title.setProperty("role", "dialogTitle")
        root.addWidget(title)

        subtitle = QLabel(
            t(
                "print.subtitle",
                "미리보기와 실제 출력은 같은 일정 스냅샷과 벡터 레이아웃을 사용합니다.",
            )
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setProperty("role", "dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self.content_scroll = QScrollArea()
        self.content_scroll.setObjectName("calendarPrintOptionsScroll")
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_scroll.setAccessibleName(
            t("print.content_options_name", "인쇄 범위 및 출력 옵션")
        )
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 4, 6, 0)
        content_layout.setSpacing(10)

        scope_group = QGroupBox(t("print.group_scope", "출력 범위"))
        scope_form = QFormLayout(scope_group)
        scope_form.setContentsMargins(14, 18, 14, 14)
        scope_form.setSpacing(10)

        self.scope_combo = QComboBox()
        self.scope_combo.addItem(t("print.scope_current", "현재 보기"), "current")
        self.scope_combo.addItem(t("print.scope_custom", "사용자 지정 기간"), "range")
        self.scope_combo.currentIndexChanged.connect(self._update_scope_state)
        scope_form.addRow(t("print.label_scope", "범위"), self.scope_combo)

        date_row = QWidget()
        date_layout = QHBoxLayout(date_row)
        date_layout.setContentsMargins(0, 0, 0, 0)
        date_layout.setSpacing(8)
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.dateChanged.connect(self._keep_range_valid)
        date_layout.addWidget(self.start_date_edit)
        date_layout.addWidget(QLabel("~"))
        date_layout.addWidget(self.end_date_edit)
        scope_form.addRow(t("print.label_dates", "시작일 · 종료일"), date_row)

        self.page_unit_combo = QComboBox()
        self.page_unit_combo.addItem(t("print.unit_month", "월별 1페이지"), "month")
        self.page_unit_combo.addItem(t("print.unit_week", "주별 1페이지"), "week")
        scope_form.addRow(t("print.label_page_unit", "페이지 단위"), self.page_unit_combo)
        content_layout.addWidget(scope_group)

        middle = QHBoxLayout()
        middle.setSpacing(12)

        calendar_group = QGroupBox(t("print.group_calendars", "캘린더 선택"))
        calendar_layout = QVBoxLayout(calendar_group)
        calendar_layout.setContentsMargins(12, 18, 12, 12)
        self.calendar_list = QListWidget()
        self.calendar_list.setMinimumHeight(145)
        self.calendar_list.setAccessibleName(t("print.calendar_list", "출력할 캘린더"))
        for calendar in self._calendar_rows:
            name = str(calendar.get("name") or calendar.get("id") or "Calendar")
            cal_type = str(calendar.get("type") or "local").upper()
            item = QListWidgetItem(
                _color_icon(str(calendar.get("color") or "#4d7cff")),
                f"{name}  ·  {cal_type}",
            )
            item.setData(Qt.ItemDataRole.UserRole, str(calendar.get("id") or ""))
            item.setCheckState(
                Qt.CheckState.Checked
                if bool(calendar.get("is_visible", 1))
                else Qt.CheckState.Unchecked
            )
            self.calendar_list.addItem(item)
        calendar_layout.addWidget(self.calendar_list)
        self.select_all_btn = QPushButton(t("print.select_all", "전체 선택"))
        self.select_all_btn.setObjectName("ghost_btn")
        self.select_all_btn.clicked.connect(self._select_all_calendars)
        calendar_layout.addWidget(self.select_all_btn)
        middle.addWidget(calendar_group, 1)

        output_group = QGroupBox(t("print.group_output", "용지와 표시"))
        output_form = QFormLayout(output_group)
        output_form.setContentsMargins(14, 18, 14, 14)
        output_form.setSpacing(10)
        self.output_preset_combo = QComboBox()
        self.output_preset_combo.addItem(
            t("print.preset_readable", "가독성 우선 (권장)"), "readable"
        )
        self.output_preset_combo.addItem(t("print.preset_balanced", "균형"), "balanced")
        self.output_preset_combo.addItem(t("print.preset_compact", "용지 절약"), "compact")
        self.output_preset_combo.addItem(t("print.preset_grayscale", "흑백 인쇄"), "grayscale")
        self.output_preset_combo.addItem(t("print.preset_custom", "사용자 지정"), "custom")
        self.output_preset_combo.currentIndexChanged.connect(self._apply_output_preset)
        output_form.addRow(t("print.label_output_preset", "출력 스타일"), self.output_preset_combo)

        self.paper_combo = QComboBox()
        self.paper_combo.addItem("A4", "A4")
        self.paper_combo.addItem("Letter", "LETTER")
        self.paper_combo.addItem("A3", "A3")
        output_form.addRow(t("print.label_paper", "용지"), self.paper_combo)

        self.orientation_combo = QComboBox()
        self.orientation_combo.addItem(t("print.landscape", "가로"), "landscape")
        self.orientation_combo.addItem(t("print.portrait", "세로"), "portrait")
        output_form.addRow(t("print.label_orientation", "방향"), self.orientation_combo)

        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(5, 30)
        self.margin_spin.setSuffix(" mm")
        output_form.addRow(t("print.label_margin", "여백"), self.margin_spin)

        self.detail_mode_combo = QComboBox()
        self.detail_mode_combo.addItem(t("print.details_always", "상세 일정 항상 포함"), "all")
        self.detail_mode_combo.addItem(
            t("print.details_overflow", "칸이 넘칠 때만 상세 페이지"), "overflow"
        )
        output_form.addRow(t("print.label_detail_pages", "상세 일정"), self.detail_mode_combo)

        self.show_weekends_check = QCheckBox(t("print.show_weekends", "주말 표시"))
        self.include_completed_check = QCheckBox(t("print.include_completed", "완료 일정 포함"))
        self.include_location_check = QCheckBox(
            t("print.include_location", "상세 페이지에 장소 표시")
        )
        self.grayscale_check = QCheckBox(t("print.grayscale", "흑백 최적화"))
        check_grid_widget = QWidget()
        check_grid = QGridLayout(check_grid_widget)
        check_grid.setContentsMargins(0, 2, 0, 0)
        check_grid.setHorizontalSpacing(10)
        check_grid.setVerticalSpacing(4)
        check_grid.addWidget(self.show_weekends_check, 0, 0)
        check_grid.addWidget(self.include_completed_check, 0, 1)
        check_grid.addWidget(self.include_location_check, 1, 0)
        check_grid.addWidget(self.grayscale_check, 1, 1)
        output_form.addRow(check_grid_widget)

        self.output_summary_label = QLabel()
        self.output_summary_label.setObjectName("printOutputSummary")
        self.output_summary_label.setProperty("role", "help")
        self.output_summary_label.setWordWrap(True)
        self.output_summary_label.setAccessibleName(
            t("print.output_summary_name", "선택한 출력 구성")
        )
        output_form.addRow(self.output_summary_label)

        self.margin_spin.valueChanged.connect(self._on_output_control_changed)
        self.detail_mode_combo.currentIndexChanged.connect(self._on_output_control_changed)
        self.grayscale_check.toggled.connect(self._on_output_control_changed)
        self.paper_combo.currentIndexChanged.connect(self._update_output_summary)
        self.orientation_combo.currentIndexChanged.connect(self._update_output_summary)
        self.page_unit_combo.currentIndexChanged.connect(self._update_output_summary)
        middle.addWidget(output_group, 1)
        content_layout.addLayout(middle)

        note = QLabel(
            t(
                "print.data_note",
                "Google·ICS 일정은 현재 로컬 DB에 저장된 마지막 동기화 상태를 기준으로 출력합니다. "
                "상세 일정은 선택한 방식에 따라 별도 페이지에 포함됩니다.",
            )
        )
        note.setWordWrap(True)
        note.setProperty("role", "dialogSubtitle")
        content_layout.addWidget(note)
        content_layout.addStretch(1)
        self.content_scroll.setWidget(content)
        root.addWidget(self.content_scroll, 1)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(separator)

        left_actions = QWidget()
        left_layout = QHBoxLayout(left_actions)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.pdf_btn = QPushButton(t("print.save_pdf", "PDF로 저장"))
        self.pdf_btn.setObjectName("ghost_btn")
        self.preview_btn = QPushButton(t("print.preview_all_pages", "전체 페이지 미리보기"))
        self.preview_btn.setObjectName("ghost_btn")
        left_layout.addWidget(self.pdf_btn)
        left_layout.addWidget(self.preview_btn)

        footer, self.print_btn, self.cancel_btn = build_dialog_footer(
            ok_label=t("print.print", "인쇄"),
            cancel_label=t("common.cancel", "취소"),
            extra_left_widget=left_actions,
        )
        self.pdf_btn.clicked.connect(self._save_pdf)
        self.preview_btn.clicked.connect(self._show_preview)
        self.print_btn.clicked.connect(self._print_native)
        self.cancel_btn.clicked.connect(self.reject)
        root.addLayout(footer)

    def _load_settings(self) -> None:
        has_saved_output_preset = self.settings.contains("print_output_preset")
        has_legacy_output_choices = any(
            self.settings.contains(key) for key in ("print_margin_mm", "print_grayscale")
        )
        self._loading_settings = True
        try:
            today = getattr(self.app, "current_date", None) or QDate.currentDate()
            self.start_date_edit.setDate(QDate(today.year(), today.month(), 1))
            self.end_date_edit.setDate(QDate(today.year(), today.month(), today.daysInMonth()))
            self._set_combo_data(
                self.scope_combo,
                self.settings.value("print_scope_mode", "current"),
            )
            self._set_combo_data(
                self.page_unit_combo,
                self.settings.value("print_page_unit", "month"),
            )
            self._set_combo_data(
                self.output_preset_combo,
                self.settings.value("print_output_preset", "readable"),
            )
            self._set_combo_data(
                self.paper_combo,
                self.settings.value("print_paper_size", "A4"),
            )
            self._set_combo_data(
                self.orientation_combo,
                self.settings.value("print_orientation", "landscape"),
            )
            self.margin_spin.setValue(self.settings.value("print_margin_mm", 12, type=int))
            self._set_combo_data(
                self.detail_mode_combo,
                self.settings.value("print_detail_page_mode", "all"),
            )
            self.show_weekends_check.setChecked(
                self.settings.value(
                    "print_show_weekends",
                    bool(getattr(self.app, "cal_show_weekends", True)),
                    type=bool,
                )
            )
            self.include_completed_check.setChecked(
                self.settings.value("print_include_completed", True, type=bool)
            )
            self.include_location_check.setChecked(
                self.settings.value("print_include_location", False, type=bool)
            )
            self.grayscale_check.setChecked(
                self.settings.value("print_grayscale", False, type=bool)
            )
        finally:
            self._loading_settings = False
        if not has_saved_output_preset and has_legacy_output_choices:
            self._set_combo_data(self.output_preset_combo, "custom")
        else:
            self._update_output_summary()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        index = combo.findData(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

    def _apply_output_preset(self, *_args) -> None:
        if self._loading_settings:
            return
        preset = str(self.output_preset_combo.currentData() or "readable")
        if preset == "custom":
            self._update_output_summary()
            return
        specifications = {
            "readable": (12, "all", False),
            "balanced": (10, "all", False),
            "compact": (7, "overflow", False),
            "grayscale": (10, "all", True),
        }
        margin_mm, detail_mode, grayscale = specifications.get(
            preset,
            specifications["readable"],
        )
        self._applying_output_preset = True
        try:
            self.margin_spin.setValue(margin_mm)
            self._set_combo_data(self.detail_mode_combo, detail_mode)
            self.grayscale_check.setChecked(grayscale)
        finally:
            self._applying_output_preset = False
        self._update_output_summary()

    def _on_output_control_changed(self, *_args) -> None:
        if self._loading_settings:
            return
        if not self._applying_output_preset:
            self._set_combo_data(self.output_preset_combo, "custom")
        self._update_output_summary()

    def _update_output_summary(self, *_args) -> None:
        if not hasattr(self, "output_summary_label"):
            return
        color_mode = (
            t("print.output_grayscale", "흑백")
            if self.grayscale_check.isChecked()
            else t("print.output_color", "컬러")
        )
        summary = t(
            "print.output_summary",
            "{unit} · {details} · {paper} {orientation} · 여백 {margin}mm · {color}",
            unit=self.page_unit_combo.currentText(),
            details=self.detail_mode_combo.currentText(),
            paper=self.paper_combo.currentText(),
            orientation=self.orientation_combo.currentText(),
            margin=self.margin_spin.value(),
            color=color_mode,
        )
        self.output_summary_label.setText(summary)
        self.output_summary_label.setAccessibleDescription(summary)

    def _save_settings(self) -> None:
        self.settings.setValue("print_scope_mode", self.scope_combo.currentData())
        self.settings.setValue("print_page_unit", self.page_unit_combo.currentData())
        self.settings.setValue(
            "print_output_preset",
            self.output_preset_combo.currentData(),
        )
        self.settings.setValue("print_paper_size", self.paper_combo.currentData())
        self.settings.setValue("print_orientation", self.orientation_combo.currentData())
        self.settings.setValue("print_margin_mm", self.margin_spin.value())
        self.settings.setValue(
            "print_detail_page_mode",
            self.detail_mode_combo.currentData(),
        )
        self.settings.setValue("print_show_weekends", self.show_weekends_check.isChecked())
        self.settings.setValue("print_include_completed", self.include_completed_check.isChecked())
        self.settings.setValue("print_include_location", self.include_location_check.isChecked())
        self.settings.setValue("print_grayscale", self.grayscale_check.isChecked())

    def _select_all_calendars(self) -> None:
        should_check = any(
            self.calendar_list.item(index).checkState() != Qt.CheckState.Checked
            for index in range(self.calendar_list.count())
        )
        state = Qt.CheckState.Checked if should_check else Qt.CheckState.Unchecked
        for index in range(self.calendar_list.count()):
            self.calendar_list.item(index).setCheckState(state)

    def _selected_calendar_ids(self) -> tuple[str, ...]:
        result = []
        for index in range(self.calendar_list.count()):
            item = self.calendar_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                calendar_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
                if calendar_id:
                    result.append(calendar_id)
        return tuple(result)

    def _keep_range_valid(self, value: QDate) -> None:
        if self.end_date_edit.date() < value:
            self.end_date_edit.setDate(value)

    def _current_view_range(self) -> tuple[date, date, str]:
        qdate = getattr(self.app, "current_date", None) or QDate.currentDate()
        current = _qdate_to_date(qdate)
        mode = str(getattr(self.app, "view_mode_state", "monthly") or "monthly")
        if mode == "monthly":
            month_start = current.replace(day=1)
            if month_start.month == 12:
                next_month = date(month_start.year + 1, 1, 1)
            else:
                next_month = date(month_start.year, month_start.month + 1, 1)
            return month_start, next_month - timedelta(days=1), "month"

        start = _start_of_week(
            current,
            bool(getattr(self.app, "cal_start_monday", True)),
        )
        span = 7
        if mode == "weekly_2":
            span = 14
        elif mode == "weekly_3":
            start -= timedelta(days=7)
            span = 21
        return start, start + timedelta(days=span - 1), "week"

    def _update_scope_state(self) -> None:
        custom = self.scope_combo.currentData() == "range"
        self.start_date_edit.setEnabled(custom)
        self.end_date_edit.setEnabled(custom)
        self.page_unit_combo.setEnabled(custom)
        if not custom:
            start, end, unit = self._current_view_range()
            self.start_date_edit.setDate(_date_to_qdate(start))
            self.end_date_edit.setDate(_date_to_qdate(end))
            self._set_combo_data(self.page_unit_combo, unit)
        self._update_output_summary()

    def _build_request(self) -> CalendarPrintRequest:
        selected = self._selected_calendar_ids()
        if not selected and self.calendar_list.count() > 0:
            raise ValueError(t("print.error_no_calendar", "출력할 캘린더를 하나 이상 선택하세요."))
        if self.scope_combo.currentData() == "current":
            start, end, unit = self._current_view_range()
        else:
            start = _qdate_to_date(self.start_date_edit.date())
            end = _qdate_to_date(self.end_date_edit.date())
            unit = str(self.page_unit_combo.currentData() or "month")
        return CalendarPrintRequest(
            start_date=start,
            end_date=end,
            page_unit=unit,
            show_weekends=self.show_weekends_check.isChecked(),
            start_monday=bool(getattr(self.app, "cal_start_monday", True)),
            selected_calendar_ids=selected,
            include_completed=self.include_completed_check.isChecked(),
            include_location=self.include_location_check.isChecked(),
            grayscale=self.grayscale_check.isChecked(),
            detail_page_mode=str(self.detail_mode_combo.currentData() or "all"),
        )

    def _build_document(self):
        request = self._build_request()
        request.validate()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            source = load_calendar_print_source(
                request.start_date.isoformat(),
                request.end_date.isoformat(),
                request.selected_calendar_ids,
            )
            return build_calendar_print_document(
                request,
                source.get("rows", []),
                source.get("calendars", []),
                warnings=(
                    t(
                        "print.warning_stored_data",
                        "Google·ICS 일정은 마지막으로 저장된 동기화 데이터 기준입니다.",
                    ),
                ),
            )
        finally:
            QApplication.restoreOverrideCursor()

    def _render_options(self) -> CalendarPrintRenderOptions:
        return CalendarPrintRenderOptions(
            paper_size=str(self.paper_combo.currentData() or "A4"),
            orientation=str(self.orientation_combo.currentData() or "landscape"),
            margin_mm=float(self.margin_spin.value()),
            document_title=t("print.document_name", "Dark Calendar 일정"),
        )

    def _new_printer(self, *, pdf_path: str | None = None) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if pdf_path:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(pdf_path)
        configure_printer(
            printer,
            self._render_options(),
            grayscale=self.grayscale_check.isChecked(),
        )
        return printer

    @staticmethod
    def _configure_preview_view(
        preview: QPrintPreviewDialog,
    ) -> QPrintPreviewWidget | None:
        """Show every generated sheet so overflow detail pages are discoverable."""
        preview_widget = preview.findChild(QPrintPreviewWidget)
        if preview_widget is None:
            return None
        preview_widget.setViewMode(QPrintPreviewWidget.ViewMode.AllPagesView)
        preview_widget.fitInView()
        return preview_widget

    def _show_error(self, error) -> None:
        QMessageBox.critical(
            self,
            t("print.error_title", "인쇄 오류"),
            str(error),
        )

    def _show_preview(self) -> None:
        try:
            self._save_settings()
            document = self._build_document()
            printer = self._new_printer()
            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle(
                f"{t('print.preview_title', '캘린더 인쇄 미리보기')} · "
                f"{self.detail_mode_combo.currentText()}"
            )
            preview.setAccessibleDescription(self.output_summary_label.text())
            preview.resize(QSize(1100, 760))
            self._configure_preview_view(preview)
            self._last_preview_error = ""

            def _paint(target_printer):
                try:
                    report = render_calendar_document(target_printer, document)
                    if report.missing_event_keys:
                        raise RuntimeError(
                            t(
                                "print.error_missing_events",
                                "출력에서 {count}개 일정이 누락되었습니다.",
                                count=len(report.missing_event_keys),
                            )
                        )
                except Exception as error:
                    self._last_preview_error = str(error)

            preview.paintRequested.connect(_paint)
            preview.exec()
            if self._last_preview_error:
                self._show_error(self._last_preview_error)
        except Exception as error:
            self._show_error(error)

    def _print_native(self) -> None:
        try:
            self._save_settings()
            document = self._build_document()
            printer = self._new_printer()
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle(t("print.native_title", "캘린더 인쇄"))
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            report = render_calendar_document(printer, document)
            if report.missing_event_keys:
                raise RuntimeError(
                    t(
                        "print.error_missing_events",
                        "출력에서 {count}개 일정이 누락되었습니다.",
                        count=len(report.missing_event_keys),
                    )
                )
        except Exception as error:
            self._show_error(error)

    def _save_pdf(self) -> None:
        try:
            self._save_settings()
            suggested = f"DarkCalendar_{self.start_date_edit.date().toString('yyyyMMdd')}.pdf"
            path, _ = QFileDialog.getSaveFileName(
                self,
                t("print.save_pdf_title", "캘린더 PDF 저장"),
                suggested,
                t("print.pdf_filter", "PDF 파일 (*.pdf)"),
            )
            if not path:
                return
            output = Path(path)
            if output.suffix.lower() != ".pdf":
                output = output.with_suffix(".pdf")
            document = self._build_document()
            printer = self._new_printer(pdf_path=str(output))
            report = render_calendar_document(printer, document)
            if report.missing_event_keys:
                raise RuntimeError(
                    t(
                        "print.error_missing_events",
                        "출력에서 {count}개 일정이 누락되었습니다.",
                        count=len(report.missing_event_keys),
                    )
                )
            if not output.exists() or output.stat().st_size <= 0:
                raise RuntimeError(t("print.error_pdf_missing", "PDF 파일이 생성되지 않았습니다."))
            QMessageBox.information(
                self,
                t("print.pdf_saved_title", "PDF 저장 완료"),
                t("print.pdf_saved", "PDF를 저장했습니다.\n{path}", path=str(output)),
            )
        except Exception as error:
            self._show_error(error)
