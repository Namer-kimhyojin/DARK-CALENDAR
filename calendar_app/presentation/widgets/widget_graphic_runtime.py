# -*- coding: utf-8 -*-
"""Opt-in collection routing without changing widget data or existing templates."""

from __future__ import annotations

import json

from PyQt6.QtCore import QDate, QDateTime, QLocale
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QWidget

from calendar_app.infrastructure.i18n import t
from calendar_app.presentation.widgets.moment_asset_packs import season_moment_id
from calendar_app.presentation.widgets.overlay_color_utils import _parse_rgba
from calendar_app.presentation.widgets.overlay_shadow import read_text_shadow
from calendar_app.presentation.widgets.widget_graphic_catalog import collection_for_kind
from calendar_app.presentation.widgets.widget_graphics import (
    WidgetGraphicSurface,
    graphic_collection,
)

_STYLE_KEYS = (
    "appearance_preset",
    "text_color_rgba",
    "bg_color_rgba",
    "border_color_rgba",
    "widget_shape",
)


class WidgetGraphicRuntimeMixin:
    def _init_graphic_collection_state(self) -> None:
        self._graphic_surface = None
        self._graphic_hidden_children = []
        self._graphic_face_active = False
        self._graphics_runtime_active = False

    def _graphic_kind(self) -> str:
        return self._settings_prefix().removeprefix("overlay_").replace("datecard", "date_card")

    def graphic_collection_id(self) -> str:
        value = str(self._get("graphic_collection", "") or "")
        if graphic_collection(value) is None:
            return ""
        if self._graphic_kind() != "launcher_deck" and self.widget_shape_id() != "card":
            return ""
        if self._graphic_kind() not in {"text", "launcher_deck"}:
            anchor = self._get("graphics_template", None)
            if anchor is not None and str(anchor) != self._widget_template():
                return ""
        return value

    def _set_graphics_runtime_active(self, active: bool) -> None:
        self._graphics_runtime_active = bool(active)
        if self._graphic_surface is not None:
            self._graphic_surface.set_runtime_active(active)

    def _detach_graphic_collection(self) -> None:
        for key in (
            "graphic_collection",
            "graphics_template",
            "graphics_backup",
            "graphics_applied",
            "graphics_font_reference",
            "graphics_keydeck_backup",
            "graphics_keydeck_applied",
        ):
            if self._setting_exists(key):
                self._s().remove(f"{self._pref()}_{key}")

    def _graphic_data(self, extra: dict | None = None) -> dict:
        kind = self._graphic_kind()
        data = dict(extra or {})
        if kind == "clock":
            now = self._now_tz()
            clock = now.time()
            twelve = "%I" in self._widget_template()
            hours = clock.hour() % 12 or 12 if twelve else clock.hour()
            show_seconds = (
                "%S" in self._widget_template()
                if self._widget_template()
                else self._display_format().endswith("ss")
            )
            data.update(
                title=t("widget_graphics.clock", "시계"),
                main=f"{hours:02d}:{clock.minute():02d}",
                minor=f":{clock.second():02d}" if show_seconds else "",
                detail=QLocale().toString(now.date(), QLocale.FormatType.LongFormat)
                + " "
                + self._tz_label(),
                hour=clock.hour() % 12 + clock.minute() / 60,
                minute=clock.minute() + clock.second() / 60,
                second=clock.second(),
                clock_second_of_day=clock.msecsSinceStartOfDay() // 1000,
                ampm=QLocale().toString(now, "AP") if twelve else "",
            )
        elif kind == "date_card":
            day = QDate.currentDate()
            data.update(
                title=QLocale().toString(day, "dddd"),
                main=str(day.day()),
                detail=QLocale().toString(day, "yyyy.MM"),
                art_pack=self._get("datecard_asset_pack", "air_moments"),
                moment=season_moment_id(day.month()),
            )
        elif kind == "dday":
            target = self._dd_target_date()
            data.update(
                title=t("widget_graphics.dday", "D-Day"),
                main=self._dd_display()[0],
                detail=str(self._get("dd_label", "") or ""),
                date=target.toString("yyyy.MM.dd")
                if target
                else t("widget.dday.no_target_hint", "날짜를 설정하세요"),
                art_pack=self._get("dday_asset_pack", "air_moments"),
                moment=self._get("dday_moment", "celebration"),
            )
        elif kind == "stopwatch":
            elapsed = data.get("elapsed_ms", self._sw_elapsed_ms())
            running = bool(data.get("running", self._sw_running()))
            seconds = max(0, float(elapsed)) / 1000
            h, rest = divmod(int(seconds), 3600)
            minute, second = divmod(rest, 60)
            data.update(
                title=t("widget_graphics.stopwatch", "스톱워치"),
                main=f"{h:02d}:{minute:02d}" if h else f"{minute:02d}:{second:02d}",
                minor=f".{int(seconds * 10) % 10}" if not h else f":{second:02d}",
                running=running,
                second=seconds % 60,
                detail=t("widget.stopwatch.status_run", "실행")
                if running
                else t("widget.stopwatch.status_stop", "정지"),
            )
        elif kind == "countdown":
            target = self._cd_target_dt()
            seconds = max(0, QDateTime.currentDateTime().secsTo(target)) if target else None
            remaining, detail = self._cd_remaining()
            progress = None
            try:
                total = float(self._get("cd_duration_seconds", 0))
                if (
                    target
                    and total > 0
                    and self._get("cd_duration_target", "") == self._get("cd_target_iso", "")
                ):
                    progress = max(0, min(1, seconds / total))
            except (TypeError, ValueError, OverflowError):
                pass
            data.update(
                title=t("widget_graphics.countdown", "카운트다운"),
                main=remaining.rsplit(":", 1)[0],
                minor=":" + remaining.rsplit(":", 1)[-1],
                detail=detail,
                progress=progress,
                urgent=seconds is not None and 0 < seconds <= 60,
                done=seconds == 0 if target else False,
            )
        elif kind == "text":
            raw = self.resolve_template() if self._is_template() else self._label_text()
            document = QTextDocument()
            document.setHtml(str(raw).replace("\n", "<br>"))
            plain = document.toPlainText()
            lines = plain.splitlines()
            data.update(
                title=lines[0] if lines else "",
                body="\n".join(lines[1:]),
                alignment=self._get("text_align", "left"),
                wrap=self._get("word_wrap", True, type_=bool),
            )
        data["accessible"] = " · ".join(
            str(data.get(key, ""))
            for key in ("title", "main", "minor", "ampm", "detail", "date", "body")
            if data.get(key) not in (None, "")
        )
        return data

    def _render_graphic_face(self, extra: dict | None = None, *, appearance=False) -> bool:
        if not hasattr(self, "face"):
            return False
        collection_id = self.graphic_collection_id()
        active = (
            bool(collection_id)
            and self._graphic_kind() not in {"weather", "launcher_deck"}
            and self.widget_shape_id() == "card"
        )
        if not active:
            if self._graphic_face_active:
                self._graphic_surface.hide()
                for child in self._graphic_hidden_children:
                    child.show()
                self._graphic_hidden_children = []
                self._graphic_face_active = False
                self._apply_base_appearance()
            return False
        if self._graphic_surface is None:
            self._graphic_surface = WidgetGraphicSurface(self.face)
            self._graphic_surface.setMouseTracking(True)
            self._graphic_surface.installEventFilter(self)
            self.face.layout().insertWidget(0, self._graphic_surface)
        entering = not self._graphic_face_active
        if entering:
            self._graphic_hidden_children = [
                child
                for child in self.face.findChildren(QWidget)
                if child.parent() is self.face
                and child is not self._graphic_surface
                and not child.isHidden()
            ]
            for child in self._graphic_hidden_children:
                child.hide()
            self._graphic_face_active = True
        if appearance or entering:
            self._apply_base_appearance()
            self.face.setStyleSheet(
                f"QFrame#{self.face.objectName()} {{background:transparent;border:none;}}"
            )
            self.face.layout().setContentsMargins(0, 0, 0, 0)
            self.face.layout().setSpacing(0)
        self._graphic_surface.show()
        foreground, text_alpha = _parse_rgba(self.text_color_rgba())
        background, background_alpha = _parse_rgba(self.bg_color_rgba())
        self._graphic_surface.configure(
            kind=self._graphic_kind(),
            collection_id=collection_id,
            data=self._graphic_data(extra),
            family=self.font_family(),
            foreground=foreground.name(),
            background=background.name(),
            background_alpha=background_alpha / 255,
            text_alpha=text_alpha / 255,
            shadow=read_text_shadow(self._get),
            motion=self._get("graphics_motion", True, type_=bool),
            auto_contrast=self._get("graphics_auto_contrast", True, type_=bool),
            text_scale=self.font_size()
            / max(1, self._get("graphics_font_reference", self.font_size(), type_=float)),
        )
        self._graphic_surface.set_runtime_active(self._graphics_runtime_active)
        return True

    def apply_graphic_collection(
        self, collection_id: str, *, motion=True, auto_contrast=True
    ) -> None:
        collection = collection_for_kind(collection_id, self._graphic_kind())
        if collection is not None:
            collection_id = collection.collection_id
        if (
            collection is None
            and not self._get("graphic_collection", "")
            and not self._get("graphics_backup", "")
        ):
            return
        if collection and self._get("graphic_collection", "") and not self.graphic_collection_id():
            self._detach_graphic_collection()
        keys = list(_STYLE_KEYS)
        if self._graphic_kind() == "weather":
            keys.append("weather_template")
        if collection is None:
            try:
                backup = json.loads(str(self._get("graphics_backup", "{}")))
                applied = json.loads(str(self._get("graphics_applied", "{}")))
                for key in keys:
                    if key in applied and self._get(key, None) == applied[key]:
                        if key in backup:
                            self._set(key, backup[key])
                        else:
                            self._s().remove(f"{self._pref()}_{key}")
            except (ValueError, TypeError, AttributeError):
                pass
            for key in (
                "graphic_collection",
                "graphics_template",
                "graphics_backup",
                "graphics_applied",
                "graphics_font_reference",
            ):
                self._s().remove(f"{self._pref()}_{key}")
        else:
            if not self._get("graphics_backup", ""):
                backup = {key: self._get(key) for key in keys if self._setting_exists(key)}
                self._set("graphics_backup", json.dumps(backup, ensure_ascii=False))
            self._set("graphic_collection", collection.collection_id)
            if not self._setting_exists("graphics_font_reference"):
                self._set("graphics_font_reference", self.font_size())
            family = self._get("font_family", None)
            has_family = self._setting_exists("font_family")
            opacity = self._get("widget_opacity", 100)
            if self._graphic_kind() != "launcher_deck":
                self._store_display_preset(collection.appearance)
                if collection.widget_kind:
                    self._set("text_color_rgba", "#ff" + collection.foreground[1:])
                    self._set("bg_color_rgba", "#f0" + collection.background[1:])
                    self._set("border_color_rgba", "#66" + collection.accent[1:])
                if has_family:
                    self._set("font_family", family)
                else:
                    self._s().remove(f"{self._pref()}_font_family")
                self._set("widget_opacity", opacity)
            self._set("graphics_motion", bool(motion))
            self._set("graphics_auto_contrast", bool(auto_contrast))
            if self._graphic_kind() == "weather":
                from calendar_app.presentation.widgets.weather_designs import weather_design

                recipe = weather_design(collection.weather_scene)
                self._set("weather_template", recipe.template)
            self._set("graphics_template", self._widget_template())
            if self._graphic_kind() != "launcher_deck" and self.widget_shape_id() != "card":
                fixed_w, fixed_h = self._get("fixed_w", None), self._get("fixed_h", None)
                self._set_widget_shape("card")
                self._set("fixed_w", fixed_w)
                self._set("fixed_h", fixed_h)
            self._set(
                "graphics_applied",
                json.dumps({key: self._get(key, None) for key in keys}, ensure_ascii=False),
            )
        self._graphic_face_active = (
            False if self._graphic_surface is None else self._graphic_face_active
        )
        if self._graphic_kind() == "launcher_deck":
            self._apply_deck_graphic_style(collection_id)
        self._apply_and_resize()

    def _open_graphic_collections(self) -> None:
        from calendar_app.presentation.widgets.widget_graphic_dialog import GraphicCollectionDialog

        apply_scope = getattr(self, "_overlay_manager_graphic_collection", None)
        dialog = GraphicCollectionDialog(self, allow_group=callable(apply_scope))
        try:
            if dialog.exec() == dialog.DialogCode.Accepted:
                if dialog.apply_group and callable(apply_scope):
                    apply_scope(dialog.collection_id, dialog.motion, dialog.auto_contrast)
                else:
                    self.apply_graphic_collection(
                        dialog.collection_id,
                        motion=dialog.motion,
                        auto_contrast=dialog.auto_contrast,
                    )
        finally:
            dialog.deleteLater()
