# -*- coding: utf-8 -*-
"""Weather resizing and design changes at the instance/settings boundary."""

from copy import deepcopy
import re
from unittest.mock import Mock, patch

from PyQt6.QtCore import QSettings, QSize
from PyQt6.QtWidgets import QApplication, QDialog, QPushButton, QTabWidget, QWidget
import pytest

from calendar_app.presentation.widgets.overlay_weather import OverlayWeatherWidget
from calendar_app.presentation.widgets.weather_template import (
    render_weather_template,
    scale_weather_preview_images,
    weather_icon_size,
)


@pytest.fixture
def widget(tmp_path):
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.settings = QSettings(str(tmp_path / "weather.ini"), QSettings.Format.IniFormat)
    network = Mock()
    with patch(
        "calendar_app.presentation.widgets.overlay_weather.get_network_manager",
        return_value=network,
    ):
        weather = OverlayWeatherWidget(owner)
        weather._weather_data.update(
            city="서울",
            temp="18.2",
            humidity="71",
            wind="2.4",
            desc="흐림",
            _wmo=2,
            _day_period="night",
        )
        weather._refresh_minutes()
        yield weather, owner, network
        weather._set_runtime_active(False)
        weather.close()
        owner.close()
        app.processEvents()


def snapshot(owner):
    return {key: owner.settings.value(key) for key in owner.settings.allKeys()}


def image_width(html):
    return int(re.search(r'width="(\d+)"', html).group(1))


def test_picture_temperature_and_implicit_unit_share_resize_factor(widget):
    weather, _, _ = widget
    values = []
    for font_size in (24, 48, 96):
        weather._set("font_size", font_size)
        weather._set(
            "weather_template", "{icon|size=64}\n{temp|size=28|bold}{unit}\n{city|size=12}"
        )
        weather._apply_appearance()
        html = weather._template_label.text()
        assert f"font-size:{font_size}pt" in html  # The previously tiny implicit unit.
        assert f"font-size:{round(28 * font_size / 24)}pt" in html
        values.append(image_width(html))
    assert values == [64, 128, 256]


def test_real_widget_resize_grows_illustration_and_text_together(widget):
    weather, _, _ = widget
    weather._set("weather_template", weather._DEFAULT_TEMPLATE)
    weather._apply_and_resize()
    measured = []
    for width, height in ((240, 300), (600, 660)):
        weather._set("fixed_w", width)
        weather._set("fixed_h", height)
        weather._fit_font_to_size(width, height)
        font_size = weather.font_size()
        measured.append((font_size, image_width(weather._template_label.text())))
        assert image_width(weather._template_label.text()) == max(16, round(64 * font_size / 24))
        assert weather.size() == QSize(width, height)
    assert measured[1][0] > measured[0][0]
    assert measured[1][1] > measured[0][1] * 1.7


@pytest.mark.parametrize(
    "hint,expected", [("64", 128), ("2x", 96), ("150%", 72), ("base", 48), ("+12", 60)]
)
def test_image_size_forms_follow_text_reference(hint, expected):
    assert weather_icon_size([f"size={hint}"], 48) == expected


@pytest.mark.parametrize("hint", ["oops", "nan", "inf", "-999", "0", "1e900"])
def test_invalid_sizes_do_not_break_resize(hint, widget):
    weather, _, _ = widget
    html = render_weather_template(
        f"{{icon|size={hint}}}{{temp|size={hint}}}{{unit}}", weather._weather_data
    )
    assert 16 <= image_width(html) <= 1536
    assert "TMPLREF" not in html
    assert "18.2" in html


def test_external_city_and_weather_description_cannot_inject_html(widget):
    weather, _, _ = widget
    data = dict(
        weather._weather_data, city='<img src="file:///secret.png">', desc="<b>wrong</b>", _wmo=None
    )
    html = render_weather_template("{city}\n{desc}\n{icon}", data)
    assert "&lt;img" in html
    assert "&lt;b&gt;wrong&lt;/b&gt;" in html
    assert '<img src="file:' not in html
    assert "data:image/png" in html


@pytest.mark.parametrize(
    "template", ["{temp|lh=inf}", "{temp|line=nan}", "{lh=infpt}{temp}", "{lh=1e999pt}{temp}"]
)
def test_invalid_line_heights_do_not_break_saved_weather_template(template, widget):
    weather, _, _ = widget
    html = render_weather_template(template, weather._weather_data)
    assert "18.2" in html
    assert "inf" not in html
    weather._set("weather_template", template)
    weather._apply_and_resize()
    assert "18.2" in weather._template_label.text()


def test_metric_units_use_the_same_size_as_their_values(widget):
    weather, _, _ = widget
    html = render_weather_template(
        "{humidity|size=10}% · {wind|size=10} m/s", weather._weather_data, base_font_size=48
    )
    assert re.search(r"font-size:20pt[^>]*>%</span>", html)
    assert re.search(r"font-size:20pt[^>]*> m/s</span>", html)


def test_aligned_weather_lines_do_not_add_empty_rows(widget):
    weather, _, _ = widget
    html = render_weather_template(
        "{align=left}{city}\n{align=left}{temp}{unit}\n{desc}", weather._weather_data
    )
    assert "</div><br>" not in html
    assert "text-align:left" in html
    assert "Seoul" not in html
    assert "서울" in html


def test_template_preview_resizes_images_with_its_text(widget):
    weather, _, _ = widget
    html = weather._resolve_weather_template(
        "{icon|size=64}{temp|size=28}", weather._weather_data, base_font_size=12
    )
    assert image_width(html) == 32
    assert image_width(scale_weather_preview_images(html, 24)) == 64
    preview = weather._wrap_preview_html(html, preview_size=QSize(324, 220))
    assert image_width(preview) == 48  # Preview font is 18pt.
    assert "font-size:21pt" in preview


def test_complete_design_keeps_location_units_cache_and_shadow(widget):
    from calendar_app.presentation.widgets.weather_designs import weather_designs

    weather, owner, network = widget
    weather._set("location", "Busan")
    weather._set("unit", "fahrenheit")
    weather._set("refresh_interval", 60)
    weather._set("met_cache_json", '{"sample":true}')
    weather._set("text_shadow_enabled", True)
    weather._set("fixed_w", 320)
    weather._set("fixed_h", 380)
    data = deepcopy(weather._weather_data)
    design = weather_designs()[0]
    weather._apply_weather_design(design.design_id)
    assert weather._get("location") == "Busan"
    assert weather._get("unit") == "fahrenheit"
    assert weather._get("refresh_interval") == 60
    assert weather._get("met_cache_json") == '{"sample":true}'
    assert weather._get("text_shadow_enabled", type_=bool)
    assert weather._weather_data == data
    assert weather._current_weather_design_id() == design.design_id
    assert not network.get.called
    weather._set("weather_template", "{temp}{unit}")
    assert weather._current_weather_design_id() == ""
    before = snapshot(owner)
    weather._apply_weather_design("unknown-design")
    assert snapshot(owner) == before


def test_gallery_cancel_does_not_save(widget):
    from calendar_app.presentation.widgets.weather_design_dialog import WeatherDesignGalleryDialog

    weather, owner, network = widget
    before = snapshot(owner)
    with patch.object(WeatherDesignGalleryDialog, "exec", return_value=QDialog.DialogCode.Rejected):
        weather._open_design_gallery()
    assert snapshot(owner) == before
    assert not network.get.called


@pytest.mark.parametrize("shape", ["circle", "capsule", "poster"])
def test_design_shape_uses_common_geometry_and_can_return_to_card(widget, shape):
    from calendar_app.presentation.widgets.weather_designs import weather_designs

    weather, _, _ = widget
    design = next(design for design in weather_designs() if design.shape == shape)
    weather._apply_weather_design(design.design_id)
    width, height = weather._get("fixed_w"), weather._get("fixed_h")
    if shape == "circle":
        assert width == height
    elif shape == "capsule":
        assert width >= height * 2
    else:
        assert height > width
    card = next(design for design in weather_designs() if design.shape == "card")
    weather._apply_weather_design(card.design_id)
    assert weather._get("fixed_w") is None
    assert weather._get("fixed_h") is None


def test_restored_circle_without_complete_size_is_repaired_when_design_applies(widget):
    from calendar_app.presentation.widgets.weather_designs import weather_designs

    weather, _, _ = widget
    weather._set("widget_shape", "circle")
    weather._set("fixed_w", None)
    weather._set("fixed_h", 140)
    design = next(design for design in weather_designs() if design.shape == "circle")
    weather._apply_weather_design(design.design_id)
    assert weather._get("fixed_w") == weather._get("fixed_h")


@pytest.mark.parametrize("save_settings", [False, True])
def test_nested_gallery_stays_in_settings_draft_until_save(widget, save_settings):
    from calendar_app.presentation.widgets.weather_design_dialog import WeatherDesignGalleryDialog
    from calendar_app.presentation.widgets.weather_designs import weather_designs

    weather, owner, network = widget
    before = snapshot(owner)
    design = weather_designs()[5]

    def exec_dialog(dialog):
        if isinstance(dialog, WeatherDesignGalleryDialog):
            dialog.selected_design = design
            return QDialog.DialogCode.Accepted
        assert dialog.findChild(QTabWidget).currentIndex() == 0
        button = next(
            button
            for button in dialog.findChildren(QPushButton)
            if button.property("weatherDesignGallery")
        )
        button.click()
        assert snapshot(owner) == before
        return QDialog.DialogCode.Accepted if save_settings else QDialog.DialogCode.Rejected

    with patch.object(QDialog, "exec", exec_dialog):
        weather._open_settings()
    if save_settings:
        assert weather._get("weather_template") == design.template
        assert weather._get("weather_asset_pack") == design.asset_pack_id
        assert weather.display_preset_id() == design.appearance_preset_id
    else:
        assert snapshot(owner) == before
    # The disabled instance never launches requests after a design/settings change.
    assert not network.get.called
