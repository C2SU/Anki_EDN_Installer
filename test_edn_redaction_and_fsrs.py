# -*- coding: utf-8 -*-
"""
Tests for EDN Redaction tools (Symbols Importer, Editor Bullet Guide, Quick Tagger)
and improved FSRS notifications (configurable timer, optimal 1-week logic).
"""
import os
import sys
import time
import pytest
from unittest.mock import MagicMock, patch

# Ensure addon directory is in sys.path
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

from Anki_EDN_Installer.symbols_importer import (
    load_edn_symbols_from_csv,
    get_raccourcis_csv_path,
    import_edn_symbols,
    is_symbols_addon_installed,
)
from Anki_EDN_Installer.editor_bullet_guide import (
    is_edn_notetype_for_bullets,
    is_field_empty,
    apply_initial_bullet_to_note,
    clean_empty_bullets_from_note,
    _on_add_cards_will_add_note,
    BULLET_TARGET_FIELDS,
    DEFAULT_INITIAL_BULLET,
)
from Anki_EDN_Installer.quick_tagger import (
    clean_tag_name,
    get_quick_tag_shortcut,
    DEFAULT_TAG_SHORTCUT,
)
from Anki_EDN_Installer.fsrs import (
    get_effective_interval_days,
    record_optimization,
    format_timestamp,
    get_last_fsrs_optimization_timestamp,
    OPTIMAL_DETECTED_INTERVAL_DAYS,
)
from Anki_EDN_Installer.setup_assistant import (
    detect_edn_symbols_status,
    apply_edn_symbols_import,
)


# =============================================================================
# 1. Tests Symbols Importer & raccourcis.csv
# =============================================================================

def test_raccourcis_csv_exists_and_loads():
    """Verify that raccourcis.csv is properly bundled and parses > 100 entries."""
    path = get_raccourcis_csv_path()
    assert os.path.isfile(path), f"raccourcis.csv not found at {path}"
    symbols = load_edn_symbols_from_csv()
    assert len(symbols) >= 150
    # Verify key medical abbreviations
    keys = {k: v for k, v in symbols}
    assert "-->" in keys
    assert "//>" in keys
    assert "+/-" in keys or ":+/-:" in keys


def test_symbols_import_into_database():
    """Verify importing into an in-memory or mock collection database."""
    class MockDb:
        def __init__(self):
            self.tables = set()
            self.rows = []

        def execute(self, query, *args):
            q = query.strip().upper()
            if "CREATE TABLE" in q:
                self.tables.add("ins_symbols")
            elif "INSERT INTO" in q:
                self.rows.append((args[0], args[1]))
            elif "UPDATE" in q:
                val, key = args[0], args[1]
                self.rows = [(k, val if k == key else v) for k, v in self.rows]

        def all(self, query):
            return list(self.rows)

        def first(self, query):
            if "ins_symbols" in self.tables:
                return ("ins_symbols",)
            return None

    mock_mw = MagicMock()
    mock_mw.col.db = MockDb()

    with patch("Anki_EDN_Installer.symbols_importer.mw", mock_mw), \
         patch("Anki_EDN_Installer.symbols_importer.save_config"):
        ok, msg, changed = import_edn_symbols(force=True)
        assert ok is True
        assert changed >= 150
        assert "ins_symbols" in mock_mw.col.db.tables


# =============================================================================
# 2. Tests Editor Bullet Guide
# =============================================================================

class DummyNote:
    def __init__(self, notetype_name: str, fields: dict, tags=None):
        self._notetype_name = notetype_name
        self.fields_dict = dict(fields)
        self.tags = tags or []

    def note_type(self):
        return {"name": self._notetype_name}

    def keys(self):
        return list(self.fields_dict.keys())

    def items(self):
        return list(self.fields_dict.items())

    def __getitem__(self, key):
        return self.fields_dict.get(key, "")

    def __setitem__(self, key, value):
        self.fields_dict[key] = value


def test_is_edn_notetype_for_bullets():
    """Check detection of notetypes needing bullet list guidance."""
    n_basic_edn = DummyNote("Basique-EDN-Picat-8b691", {"Recto": "", "Verso": ""})
    assert is_edn_notetype_for_bullets(n_basic_edn) is True

    n_syndrome = DummyNote("Syndrome-EDN-Picat-a47eb", {"Nom": "", "Description": ""})
    assert is_edn_notetype_for_bullets(n_syndrome) is True

    n_semio = DummyNote("Sémiologie-EDN-Picat-f482c", {"Nom": "", "Description": ""})
    assert is_edn_notetype_for_bullets(n_semio) is True

    n_generic = DummyNote("Basic", {"Front": "", "Back": ""})
    assert is_edn_notetype_for_bullets(n_generic) is False


def test_apply_initial_bullet_to_note():
    """Verify pre-populating empty target fields (Verso, Description) with bullets."""
    note = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "Question text", "Verso": "", "Erreurs faites": ""}
    )
    changed = apply_initial_bullet_to_note(note)
    assert changed is True
    assert note["Verso"] == DEFAULT_INITIAL_BULLET
    # Recto should not be modified
    assert note["Recto"] == "Question text"
    # Personal field should not be modified
    assert note["Erreurs faites"] == ""


def test_clean_empty_bullets_from_note():
    """Verify stripping empty bullet markup before saving."""
    note = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "Test", "Verso": "<ul><li><br></li></ul>"}
    )
    changed = clean_empty_bullets_from_note(note)
    assert changed is True
    assert note["Verso"] == ""

    # If user actually wrote content, it must not be stripped
    note_with_text = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "Test", "Verso": "<ul><li>Ratio < 1.2</li></ul>"}
    )
    changed = clean_empty_bullets_from_note(note_with_text)
    assert changed is False
    assert "Ratio < 1.2" in note_with_text["Verso"]


def test_is_field_empty_preserves_media():
    """Verify that images and sounds are not treated as empty fields."""
    assert is_field_empty('<img src="paste-12345.png">') is False
    assert is_field_empty('<div><img src="scan.jpg"></div>') is False
    assert is_field_empty('[sound:rec123.mp3]') is False
    assert is_field_empty('<ul><li><img src="radio.png"></li></ul>') is False
    assert is_field_empty('   ') is True
    assert is_field_empty('<div><br></div>') is True


def test_on_add_cards_will_add_note_anki_filter_signature():
    """Verify Anki gui_hooks.add_cards_will_add_note compatibility (problem, note)."""
    # 1. Normal addition: problem is None, empty bullets cleaned, returns None
    note = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "Question", "Verso": "<ul><li><br></li></ul>"}
    )
    result = _on_add_cards_will_add_note(None, note)
    assert result is None  # Must NOT return note object, as truthy value signals rejection in Anki
    assert note["Verso"] == ""  # Empty bullets cleaned

    # 2. Existing rejection: problem is a string, preserved without change
    note2 = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "", "Verso": "Content"}
    )
    result2 = _on_add_cards_will_add_note("Premier champ vide", note2)
    assert result2 == "Premier champ vide"

    # 3. Media in Verso: must not be wiped out
    note_media = DummyNote(
        "Basique-EDN-Picat-8b691",
        {"Recto": "Question", "Verso": '<img src="radio.png">'}
    )
    result3 = _on_add_cards_will_add_note(None, note_media)
    assert result3 is None
    assert note_media["Verso"] == '<img src="radio.png">'


# =============================================================================
# 3. Tests Quick Tagger
# =============================================================================

def test_clean_tag_name():
    """Verify tag name sanitation for Anki."""
    assert clean_tag_name("tag with spaces") == "tag_with_spaces"
    assert clean_tag_name('tag<bad>"chars"') == "tagbadchars"
    assert clean_tag_name("EDN::item-020") == "EDN::item-020"


def test_get_quick_tag_shortcut():
    """Verify shortcut configuration and fallback."""
    with patch("Anki_EDN_Installer.quick_tagger.get_config", return_value={"shortcuts": {"quick_tagger": "Ctrl+T"}}):
        assert get_quick_tag_shortcut() == "Ctrl+T"

    with patch("Anki_EDN_Installer.quick_tagger.get_config", return_value={}):
        assert get_quick_tag_shortcut() == DEFAULT_TAG_SHORTCUT


# =============================================================================
# 4. Tests Improved FSRS Notification Logic
# =============================================================================

def test_effective_interval_normal_vs_optimal():
    """
    Test the critical user requirement:
    - Default reminder: 3 weeks (21 days).
    - If 'optimal settings detected last time': reminder is shortened to 1 week (7 days).
    """
    # 1. Standard config: 3 weeks
    with patch("Anki_EDN_Installer.fsrs.get_config", return_value={"fsrs_reminder_interval_weeks": 3, "fsrs_last_was_optimal": False}):
        days, label = get_effective_interval_days()
        assert days == 21
        assert "3 semaines" in label

    # 2. Optimal detected: 1 week
    with patch("Anki_EDN_Installer.fsrs.get_config", return_value={"fsrs_reminder_interval_weeks": 3, "fsrs_last_was_optimal": True}):
        days, label = get_effective_interval_days()
        assert days == 7
        assert "1 semaine" in label


def test_record_optimization():
    """Verify saving optimization timestamp and optimal state."""
    mock_cfg = {}
    with patch("Anki_EDN_Installer.fsrs.get_config", return_value=mock_cfg), \
         patch("Anki_EDN_Installer.fsrs.save_config") as mock_save:
        record_optimization(was_optimal=True, custom_time=1700000000.0)
        assert mock_cfg["fsrs_last_was_optimal"] is True
        assert mock_cfg["fsrs_last_optimization_time"] == 1700000000.0
        assert mock_cfg["fsrs_snooze_until"] == 0
        mock_save.assert_called_once()


def test_format_timestamp():
    """Verify date formatting without emoji."""
    formatted = format_timestamp(1700000000.0)
    assert "/" in formatted
    assert "a" in formatted or ":" in formatted
    assert format_timestamp(None) == "Aucune date enregistree"


# =============================================================================
# 5. Tests Setup Assistant Integration
# =============================================================================

def test_setup_assistant_detects_symbols_status():
    """Verify setup assistant detects symbol status correctly."""
    class MockCol:
        def __init__(self, has_symbols=False):
            self.has_symbols = has_symbols
            self.db = MagicMock()
            if has_symbols:
                self.db.first.return_value = ("ins_symbols",)
                self.db.all.return_value = [("-->",), ("//>",)]
            else:
                self.db.first.return_value = None
                self.db.all.return_value = []

    # Case 1: not imported yet
    status_missing = detect_edn_symbols_status(col=MockCol(has_symbols=False))
    assert status_missing["done"] is False
    assert "importer" in status_missing["badge"].lower()

    # Case 2: already imported
    with patch("Anki_EDN_Installer.symbols_importer.load_edn_symbols_from_csv", return_value=[("-->", "arr"), ("//>", "arr2")]):
        status_ok = detect_edn_symbols_status(col=MockCol(has_symbols=True))
        assert status_ok["done"] is True
        assert "configuré" in status_ok["badge"] or "jour" in status_ok["badge"]


def test_shared_menu_register_action_shortcut_key():
    """Verify register_action supports custom shortcut_key for 1762336370 scanner."""
    from aqt.qt import QApplication, QMenu
    app = QApplication.instance() or QApplication([])
    from Anki_EDN_Installer.shared_menu import register_module, register_action, _get_registry
    mock_menu = QMenu()
    with patch("Anki_EDN_Installer.shared_menu.get_edn_menu", return_value=mock_menu), \
         patch("Anki_EDN_Installer.shared_menu.is_module_enabled", return_value=True):
        register_module("test_scanner_mod", "Test Scanner Mod")
        dummy_cb = lambda: None
        act = register_action(
            "test_scanner_mod",
            "Action Test (Revision)",
            dummy_cb,
            shortcut="T",
            shortcut_key="test_scanner_action_reviewer"
        )
        assert act is not None
        reg = _get_registry()
        assert "test_scanner_mod" in reg
        actions = reg["test_scanner_mod"]["actions"]
        found = [a for a in actions if a.get("label") == "Action Test (Revision)"]
        assert len(found) == 1
        assert found[0]["shortcut_key"] == "test_scanner_action_reviewer"



