# -*- coding: utf-8 -*-
"""Expanded KeyDeck themes remain valid and preserve user-authored content."""

from collections import Counter
from copy import deepcopy
from dataclasses import fields

import pytest

from calendar_app.presentation.widgets.keydeck import model as m

LEGACY_RECIPES = {
    "crystal_night": (
        "anodized",
        "#171b23",
        "#5ab8ff",
        "crystal",
        "cylindrical",
        "#e8f0ff",
        "tactile",
        "reactive",
        ("#5ab8ff",),
        "#f5f8ff",
        "bold",
        "pattern",
        (("#233a63", "#0b1322"), ("#2c2458", "#0f0b24"), ("#12454f", "#071a1f")),
        "",
        "",
    ),
    "frost_paper": (
        "silver",
        "#c9ced6",
        "#ff8a5b",
        "frosted",
        "spherical",
        "#ffffff",
        "linear",
        "static",
        ("#fff1e0",),
        "#2b2f38",
        "bold",
        "gradient",
        (
            ("#fde2e4", "#f6c1c7"),
            ("#dff0ea", "#b8e0dc"),
            ("#fff1e2", "#fbd9b8"),
            ("#e8e3f6", "#cdc2ee"),
        ),
        "#ff8a5b",
        "#ffffff",
    ),
    "smoke_neon": (
        "anodized",
        "#0b0d12",
        "#ff3df0",
        "smoke",
        "cylindrical",
        "#1a1d24",
        "clicky",
        "static",
        ("#ff3df0", "#3dd9ff"),
        "#ffffff",
        "bold",
        "pattern",
        (("#2a0f3d", "#07040f"), ("#062e38", "#02090c")),
        "",
        "",
    ),
    "pudding_pop": (
        "acrylic",
        "#e7ecf5",
        "#7c5cff",
        "pudding",
        "spherical",
        "#f7f4ff",
        "linear",
        "reactive",
        ("#ff5f7e", "#ffb35c", "#ffe45c", "#5cf29a", "#5cc8ff", "#9b7bff"),
        "#2a2340",
        "bold",
        "color",
        (
            ("#fff0f3", "#ffd6de"),
            ("#fff6e8", "#ffe2bd"),
            ("#eefcf4", "#c9f5dc"),
            ("#eef4ff", "#cfe0ff"),
        ),
        "",
        "",
    ),
    "graphite_pbt": (
        "anodized",
        "#2a2d33",
        "#ff7a1a",
        "solid",
        "cylindrical",
        "#3b3f46",
        "tactile",
        "off",
        ("#ff7a1a",),
        "#eceef2",
        "medium",
        "none",
        (),
        "#ff7a1a",
        "#1d1f23",
    ),
    "walnut_studio": (
        "walnut",
        "#6b4226",
        "#d98c3f",
        "solid",
        "spherical",
        "#efe6d2",
        "linear",
        "off",
        ("#ffcf8a",),
        "#3b2a1a",
        "bold",
        "none",
        (),
        "#d98c3f",
        "#fffaf0",
    ),
    "floating_glass": (
        "floating",
        "#10141c",
        "#7cc4ff",
        "crystal",
        "flat",
        "#eef6ff",
        "silent",
        "reactive",
        ("#7cc4ff",),
        "#ffffff",
        "bold",
        "gradient",
        (
            ("#3a7bd5", "#00d2ff"),
            ("#6a3093", "#a044ff"),
            ("#11998e", "#38ef7d"),
            ("#ee0979", "#ff6a00"),
        ),
        "",
        "",
    ),
}
RECIPE_FIELDS = tuple(field.name for field in fields(m.DeckTheme))[3:18]
THEME_IDS = [theme.theme_id for theme in m.THEMES]


def test_catalog_has_six_balanced_categories_and_unique_search_metadata():
    categories = [category_id for category_id, *_rest in m.THEME_CATEGORIES]
    assert categories == ["glass", "minimal", "pastel", "nature", "neon", "retro"]
    assert len(m.THEMES) == len(set(THEME_IDS)) == 24
    assert Counter(theme.category for theme in m.THEMES) == dict.fromkeys(categories, 4)
    for category_id, key, fallback in m.THEME_CATEGORIES:
        assert key == f"widget.launcher.theme_category.{category_id}"
        assert fallback
    for theme in m.THEMES:
        assert theme.label_key == f"widget.launcher.theme.{theme.theme_id}"
        assert theme.description_key == f"widget.launcher.theme_description.{theme.theme_id}"
        assert theme.label_default and theme.description_default


def test_original_theme_ids_default_and_visual_recipes_are_unchanged():
    assert m.DEFAULT_THEME_ID == "crystal_night"
    assert tuple(THEME_IDS[:7]) == tuple(LEGACY_RECIPES)
    for theme_id, expected in LEGACY_RECIPES.items():
        theme = m.deck_theme(theme_id)
        assert tuple(getattr(theme, name) for name in RECIPE_FIELDS) == expected
    assert m.deck_theme("unrecognized") is m.deck_theme(m.DEFAULT_THEME_ID)


def test_new_recipes_are_distinct_and_use_supported_shapes_materials_and_lighting():
    option_fields = {
        "case_style": m.CASE_STYLES,
        "material": m.MATERIALS,
        "profile": m.PROFILES,
        "switch": m.SWITCHES,
        "led_mode": m.LED_MODES,
        "legend_weight": m.LEGEND_WEIGHTS,
        "insert_kind": m.INSERT_KINDS,
    }
    recipes = set()
    for theme in m.THEMES:
        for name, options in option_fields.items():
            assert getattr(theme, name) in m.option_ids(options), (theme.theme_id, name)
        assert theme.led_colors
        colors = (
            theme.case_color,
            theme.accent,
            theme.cap_color,
            theme.legend_color,
            *theme.led_colors,
            *(color for pair in theme.insert_palette for color in pair),
        )
        for color in colors:
            assert m.clean_color(color, "invalid") == color
        recipes.add(tuple(getattr(theme, name) for name in RECIPE_FIELDS))
    assert len(recipes) == len(m.THEMES)
    assert {theme.profile for theme in m.THEMES} == m.option_ids(m.PROFILES)
    assert {theme.led_mode for theme in m.THEMES} == m.option_ids(m.LED_MODES)


@pytest.mark.parametrize("theme_id", THEME_IDS)
def test_every_catalog_theme_round_trips_without_normalization_fallback(theme_id):
    deck = m.build_template_deck("creator_mixed", theme_id)
    theme = m.deck_theme(theme_id)
    restored = m.deck_from_json(m.deck_to_json(deck))
    assert restored == deck
    assert restored["theme"] == theme_id
    assert restored["case"]["style"] == theme.case_style
    assert not m.has_overlaps(restored["pages"][0]["keys"])
    for key in restored["pages"][0]["keys"]:
        assert key["cap"]["material"] == theme.material
        assert key["cap"]["profile"] == theme.profile
        assert key["led"]["mode"] == theme.led_mode


def _content_snapshot(deck):
    return {
        "deck": {
            name: deepcopy(value)
            for name, value in deck.items()
            if name not in {"theme", "case", "pages"}
        },
        "header": deck["case"]["header"],
        "pages": [
            {
                "id": page["id"],
                "name": page["name"],
                "keys": [
                    {
                        name: deepcopy(value)
                        for name, value in key.items()
                        if name not in {"cap", "led", "switch", "legend", "insert"}
                    }
                    for key in page["keys"]
                ],
            }
            for page in deck["pages"]
        ],
    }


@pytest.mark.parametrize("theme_id", THEME_IDS)
def test_theme_changes_preserve_actions_layout_art_and_custom_sound(theme_id):
    deck = m.build_template_deck("creator_mixed")
    deck.update(
        {
            "scale": 124,
            "sound_enabled": False,
            "sound_volume": 17,
            "reduce_motion": True,
            "led_brightness": 34,
        }
    )
    deck["panorama"].update({"path": "C:/user/wallpaper.png", "fit": "contain", "zoom": 125})
    keys = deck["pages"][0]["keys"]
    for index, key in enumerate(keys):
        key.update(
            {"label": f"내 키 {index}", "sound": "custom", "sound_path": "C:/user/click.wav"}
        )
        key["action"].update({"type": "text", "target": f"메모 {index}", "paste": True})
        key["hold_action"].update({"type": "url", "target": "https://example.org"})
    keys[0]["insert"].update({"kind": "image", "path": "C:/user/photo.png", "ox": 24, "zoom": 133})
    keys[1]["insert"]["kind"] = "panorama"
    art = [deepcopy(key["insert"]) for key in keys[:2]]
    before = _content_snapshot(deck)
    result = m.apply_theme(deck, theme_id)
    assert result is deck
    assert _content_snapshot(deck) == before
    assert [key["insert"] for key in keys[:2]] == art
    assert deck["theme"] == theme_id


def test_selection_scope_keeps_case_and_all_other_keys_unchanged():
    deck = m.build_template_deck("macro_3x3")
    deck["pages"].append({**m.new_page("두 번째"), "keys": m.template_keys("command_bar")})
    before = deepcopy(deck)
    target = deck["pages"][0]["keys"][0]
    m.apply_theme(deck, "cobalt_arcade", page_index=0, key_ids={target["id"]})
    assert deck["theme"] == before["theme"]
    assert deck["case"] == before["case"]
    assert deck["pages"][1] == before["pages"][1]
    assert deck["pages"][0]["keys"][1:] == before["pages"][0]["keys"][1:]
    assert target["cap"]["profile"] == "round"


def test_page_scope_preserves_other_pages_case_and_global_theme():
    deck = m.build_template_deck("macro_3x3")
    deck["pages"].append({**m.new_page("두 번째"), "keys": m.template_keys("command_bar")})
    before = deepcopy(deck)
    m.apply_theme(deck, "forest_sage", page_index=1)
    assert deck["theme"] == before["theme"]
    assert deck["case"] == before["case"]
    assert deck["pages"][0] == before["pages"][0]
    assert all(key["cap"]["profile"] == "xda" for key in deck["pages"][1]["keys"])


def test_explicit_art_replacement_still_obeys_existing_keep_art_option():
    deck = m.build_template_deck("macro_3x3")
    key = deck["pages"][0]["keys"][0]
    key["insert"].update({"kind": "image", "path": "C:/user/photo.png"})
    m.apply_theme(deck, "ocean_blue", keep_art=False)
    assert key["insert"]["kind"] == "gradient"


@pytest.mark.parametrize("theme_id", THEME_IDS[7:])
def test_new_themes_leave_keyboard_layouts_as_printed_keys(theme_id):
    deck = m.build_template_deck("keyboard_full", theme_id)
    keys = deck["pages"][0]["keys"]
    assert len(keys) == 104
    assert not m.has_overlaps(keys)
    assert all(key["action"]["type"] == "hotkey" for key in keys)
    assert all(key["insert"]["kind"] == "none" for key in keys)
    assert all(key["legend"]["glyph"] == "none" for key in keys)
    assert all(key["legend"]["layout"] == "corner" for key in keys)
