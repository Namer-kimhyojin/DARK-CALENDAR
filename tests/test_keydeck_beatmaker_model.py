# -*- coding: utf-8 -*-
"""Beatmaker banks preserve their sound-only contract through normal deck workflows."""

from copy import deepcopy
import json

from calendar_app.presentation.widgets.keydeck import layout_library as library
from calendar_app.presentation.widgets.keydeck import model as m
from calendar_app.presentation.widgets.keydeck.beatmaker import (
    BEATMAKER_KITS,
    BEATMAKER_SHORTCUTS,
    BEATMAKER_TEMPLATE_ID,
    BEATMAKER_TEMPLATE_KITS,
    apply_beatmaker_preset,
    beatmaker_keys,
    beatmaker_state,
)
from calendar_app.presentation.widgets.launcher_keycap_sounds import keycap_sound_ids


def test_template_has_two_playable_banks_and_round_trips():
    deck = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    assert len(deck["pages"]) == 2
    assert [beatmaker_state(page) for page in deck["pages"]] == [
        {"kit": "lofi", "bank": "drums"},
        {"kit": "lofi", "bank": "melody"},
    ]
    for page in deck["pages"]:
        assert len(page["keys"]) == 16
        assert not m.has_overlaps(page["keys"])
        assert m.layout_bounds(page["keys"]) == (0.0, 0.0, 4.0, 4.0)
        assert "".join(key["sublabel"] for key in page["keys"]) == BEATMAKER_SHORTCUTS
        assert all(
            key["action"] == {"type": "sound", "target": "", "paste": False} for key in page["keys"]
        )
        assert all(key["hold_action"]["type"] == "none" for key in page["keys"])
    assert m.deck_from_json(m.deck_to_json(deck)) == deck


def test_every_kit_and_bank_resolves_bundled_instruments():
    available = keycap_sound_ids()
    for kit, *_label in BEATMAKER_KITS:
        for bank in ("drums", "melody"):
            sounds = [key["sound"] for key in beatmaker_keys(kit, bank)]
            assert len(set(sounds)) == 16
            assert set(sounds) <= available
            assert all(
                m.normalize_key(key)["sound"] == key["sound"] for key in beatmaker_keys(kit, bank)
            )


def test_kit_layout_cards_build_matching_drums_and_melody_banks():
    assert BEATMAKER_TEMPLATE_KITS[BEATMAKER_TEMPLATE_ID] == "lofi"
    expected_names = {kit_id: label for kit_id, _key, label in BEATMAKER_KITS}
    entries = {entry[0]: entry for entry in m.TEMPLATES}
    for template_id, kit in BEATMAKER_TEMPLATE_KITS.items():
        assert entries[template_id][1] == f"widget.launcher.template.{template_id}"
        assert entries[template_id][2].endswith(expected_names[kit])
        template_keys = m.template_keys(template_id)
        assert len(template_keys) == 16
        assert all(key["sound"].startswith(f"beat_{kit}_") for key in template_keys)
        deck = m.build_template_deck(template_id)
        assert deck["name"] == expected_names[kit]
        assert [beatmaker_state(page) for page in deck["pages"]] == [
            {"kit": kit, "bank": "drums"},
            {"kit": kit, "bank": "melody"},
        ]
        assert all(
            key["sound"].startswith(f"beat_{kit}_")
            for page in deck["pages"]
            for key in page["keys"]
        )
        assert m.deck_from_json(m.deck_to_json(deck)) == deck


def test_melody_uses_pentatonic_notes_with_low_notes_at_bottom():
    keys = beatmaker_keys(bank="melody")
    assert [key["label"] for key in keys[12:]] == ["C3", "D3", "E3", "G3"]
    assert keys[3]["label"] == "C6"
    assert all(key["label"][0] in "CDEGA" for key in keys)


def test_preset_updates_only_requested_page():
    deck = m.build_template_deck("macro_3x3")
    deck["pages"].append({**m.new_page("개인 도구"), "keys": m.template_keys("command_bar")})
    untouched = deepcopy(deck["pages"][1])
    page_id = deck["pages"][0]["id"]
    apply_beatmaker_preset(deck, kit="neon", bank="melody")
    assert deck["pages"][0]["id"] == page_id
    assert beatmaker_state(deck["pages"][0]) == {"kit": "neon", "bank": "melody"}
    assert all(key["sound"].startswith("beat_neon_") for key in deck["pages"][0]["keys"])
    assert deck["pages"][1] == untouched


def test_template_adds_melody_once_and_keeps_existing_pages():
    deck = m.build_template_deck("macro_3x3")
    deck["pages"].append({**m.new_page("원래 페이지"), "keys": m.template_keys("command_bar")})
    existing = deepcopy(deck["pages"][1])
    m.apply_template_to_page(deck, 0, BEATMAKER_TEMPLATE_ID)
    assert len(deck["pages"]) == 3
    assert deck["pages"][1] == existing
    melody = deepcopy(deck["pages"][2])
    m.apply_template_to_page(deck, 0, BEATMAKER_TEMPLATE_ID)
    assert len(deck["pages"]) == 3
    assert deck["pages"][2] == melody


def test_selecting_another_kit_keeps_existing_banks_and_adds_matching_melody_once():
    deck = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    lofi_melody = deepcopy(deck["pages"][1])
    deck_name = deck["name"]
    m.apply_template_to_page(deck, 0, "beatmaker_neon_4x4")
    assert deck["name"] == deck_name
    assert deck["pages"][1] == lofi_melody
    assert beatmaker_state(deck["pages"][0]) == {"kit": "neon", "bank": "drums"}
    assert beatmaker_state(deck["pages"][2]) == {"kit": "neon", "bank": "melody"}
    neon_melody = deepcopy(deck["pages"][2])
    m.apply_template_to_page(deck, 0, "beatmaker_arcade_4x4")
    assert deck["pages"][1] == lofi_melody
    assert deck["pages"][2] == neon_melody
    assert beatmaker_state(deck["pages"][3]) == {"kit": "arcade", "bank": "melody"}
    arcade_melody = deepcopy(deck["pages"][3])
    m.apply_template_to_page(deck, 0, "beatmaker_arcade_4x4")
    assert len(deck["pages"]) == 4
    assert deck["pages"][3] == arcade_melody


def test_full_deck_replaces_only_selected_page_without_losing_other_pages():
    deck = m.build_template_deck("macro_3x3")
    deck["pages"].extend(m.new_page(str(index)) for index in range(m.MAX_PAGES - 1))
    others = deepcopy(deck["pages"][1:])
    m.apply_template_to_page(deck, 0, BEATMAKER_TEMPLATE_ID)
    assert len(deck["pages"]) == m.MAX_PAGES
    assert deck["pages"][1:] == others
    assert beatmaker_state(deck["pages"][0]) == {"kit": "lofi", "bank": "drums"}
    m.apply_template_to_page(deck, 0, "beatmaker_neon_4x4")
    assert len(deck["pages"]) == m.MAX_PAGES
    assert deck["pages"][1:] == others
    assert beatmaker_state(deck["pages"][0]) == {"kit": "neon", "bank": "drums"}


def test_theme_preserves_performance_legends_colors_and_custom_sounds():
    deck = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    key = deck["pages"][0]["keys"][0]
    key["label"] = "나의 크래시"
    key["sound"] = "custom"
    key["sound_path"] = "C:/sounds/custom.wav"
    pages = deepcopy(deck["pages"])
    m.apply_theme(deck, "walnut_studio")
    assert deck["pages"] == pages
    assert deck["case"]["style"] == "walnut"


def test_normal_template_clears_performance_metadata():
    deck = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    m.apply_template_to_page(deck, 0, "command_bar")
    assert beatmaker_state(deck["pages"][0]) is None
    assert beatmaker_state(m.normalize_deck(deck)["pages"][0]) is None


def test_malformed_metadata_does_not_enable_performance_mode():
    deck = m.build_template_deck("macro_3x3")
    for invalid in (
        True,
        [],
        {"kit": "missing", "bank": "drums"},
        {"kit": "lofi", "bank": "bad"},
        {"kit": ["lofi"], "bank": "drums"},
        {"kit": "lofi", "bank": {"drums": True}},
    ):
        deck["pages"][0]["beatmaker"] = invalid
        assert beatmaker_state(m.normalize_deck(deck)["pages"][0]) is None
    assert m.normalize_action({"type": "sound", "target": "C:/wrong.exe", "paste": True}) == {
        "type": "sound",
        "target": "",
        "paste": False,
    }


def test_shared_page_round_trip_keeps_performance_metadata_and_sound_ids(tmp_path):
    source = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    apply_beatmaker_preset(source, kit="arcade", bank="melody")
    document, skipped = library.build_document(source, kind="page", name="나의 비트")
    assert not skipped
    loaded = library.parse_document(json.dumps(document).encode("utf-8", errors="strict"))
    content = library.materialize(loaded, asset_root=tmp_path)
    target = library.apply_content(m.build_template_deck("macro_3x3"), content, "new_page")
    page = target["pages"][target["page"]]
    assert beatmaker_state(page) == {"kit": "arcade", "bank": "melody"}
    assert [key["sound"] for key in page["keys"]] == [
        key["sound"] for key in source["pages"][0]["keys"]
    ]
    normal, _ = library.build_document(
        m.build_template_deck("command_bar"), kind="page", name="도구"
    )
    normal_content = library.materialize(normal, asset_root=tmp_path)
    replaced = library.apply_content(target, normal_content)
    assert beatmaker_state(replaced["pages"][replaced["page"]]) is None


def test_pad_volume_is_clamped_defaults_to_full_and_round_trips():
    for raw, expected in (
        (0, 0),
        (37, 37),
        (100, 100),
        (-4, 0),
        (999, 100),
        ("broken", 100),
        (None, 100),
    ):
        assert m.normalize_key({"sound_volume": raw})["sound_volume"] == expected
    assert m.normalize_key({})["sound_volume"] == 100
    deck = m.build_template_deck(BEATMAKER_TEMPLATE_ID)
    for key, volume in zip(deck["pages"][0]["keys"], (0, 37, 100), strict=False):
        key["sound_volume"] = volume
    restored = m.deck_from_json(m.deck_to_json(deck))
    assert [key["sound_volume"] for key in restored["pages"][0]["keys"][:3]] == [0, 37, 100]
