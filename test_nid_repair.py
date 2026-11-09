# -*- coding: utf-8 -*-
"""
Tests unitaires pour le module de réparation et d'alignement des NIDs (nid_repair.py).
Vérifie la mise à jour transactionnelle des notes et cartes, la gestion des collisions,
l'interception automatique post-téléchargement AnkiCollab, et le retrait de la proposition
de téléchargement de l'ancien greffon 2135076010.
"""
import json
import os
import sys
import tempfile
import types
from unittest.mock import MagicMock, patch
import pytest

from anki.storage import Collection
from aqt import mw

from Anki_EDN_Installer.nid_repair import (
    migrate_nids,
    detect_nid_repair_status,
    install_ankicollab_deck_hook,
    get_nid_mapping_path,
)
from Anki_EDN_Installer.settings_dialog import RECOMMENDED_ADDONS_CATALOG
from Anki_EDN_Installer.setup_assistant import missing_addons


@pytest.fixture
def temp_col():
    tmpdir = tempfile.mkdtemp()
    col_path = os.path.join(tmpdir, "test_nid.anki2")
    col = Collection(col_path)

    edn_res = col.decks.add_normal_deck_with_name("Anki EDN")
    edn_did = edn_res.id

    notetype = col.models.by_name("Basic")

    # Création de 2 notes
    for i in range(2):
        n = col.new_note(notetype)
        n.fields[0] = f"Question {i}"
        n.fields[1] = f"Réponse {i}"
        col.add_note(n, edn_did)

    yield col
    col.close()


def test_migrate_nids_successful_update(temp_col, tmp_path):
    """Vérifie la mise à jour synchronisée de notes.id et cards.nid."""
    col = temp_col
    notes = col.db.all("SELECT guid, id FROM notes ORDER BY id ASC")
    guid1, old_id1 = notes[0]
    target_id1 = old_id1 + 50000

    map_file = tmp_path / "nid_mapping.txt"
    map_file.write_text(f"{guid1},{target_id1}\n", encoding="utf-8")

    updated, msg = migrate_nids(
        col=col,
        auto=False,
        silent=True,
        trigger_sync=False,
        mapping_file=str(map_file),
    )

    assert updated == 1
    assert "1 notes" in msg

    # Vérification dans la base SQLite
    new_nid = col.db.scalar(f"SELECT id FROM notes WHERE guid = '{guid1}'")
    assert new_nid == target_id1

    # Vérification que cards.nid a suivi
    card_nids = col.db.list(f"SELECT nid FROM cards WHERE nid = {target_id1}")
    assert len(card_nids) == 1
    assert card_nids[0] == target_id1


def test_migrate_nids_collision_avoidance(temp_col, tmp_path):
    """Vérifie qu'en cas de collision d'ID avec une note existante, la note en conflit est ignorée."""
    col = temp_col
    notes = col.db.all("SELECT guid, id FROM notes ORDER BY id ASC")
    guid1, id1 = notes[0]
    guid2, id2 = notes[1]

    # Essai de donner à note1 le même id que note2 (collision)
    map_file = tmp_path / "nid_mapping.txt"
    map_file.write_text(f"{guid1},{id2}\n", encoding="utf-8")

    updated, msg = migrate_nids(
        col=col,
        auto=False,
        silent=True,
        trigger_sync=False,
        mapping_file=str(map_file),
    )

    assert updated == 0
    assert "déjà à jour" in msg

    # Les ID restent inchangés
    assert col.db.scalar(f"SELECT id FROM notes WHERE guid = '{guid1}'") == id1
    assert col.db.scalar(f"SELECT id FROM notes WHERE guid = '{guid2}'") == id2


def test_ankicollab_deck_hook_triggers_repair(temp_col, monkeypatch):
    """Vérifie que l'intercepteur AnkiCollab déclenche automatiquement migrate_nids à la fin du téléchargement."""
    col = temp_col
    fake_mod = types.ModuleType("1957538407.import_manager")

    call_records = []

    def fake_on_deck_installed(install_result, deck, subscription, input_hash=None, update_timestamp_after=False):
        call_records.append("orig_called")
        return "Anki EDN"

    fake_mod._on_deck_installed = fake_on_deck_installed
    sys.modules["1957538407.import_manager"] = fake_mod

    # Installer le hook
    install_ankicollab_deck_hook()

    assert hasattr(fake_mod, "_edn_orig_on_deck_installed")

    # Simuler l'arrivée du deck AnkiCollab
    mock_deck = MagicMock()
    mock_deck.anki_dict = {"name": "Anki EDN"}
    mock_sub = {"deck_hash": "abc123hash"}

    # Mock migrate_nids pour espionner l'appel
    with patch("Anki_EDN_Installer.nid_repair.migrate_nids") as mock_migrate:
        fake_mod._on_deck_installed(None, mock_deck, mock_sub)

        assert "orig_called" in call_records
        mock_migrate.assert_called_once()
        kwargs = mock_migrate.call_args[1]
        assert kwargs.get("auto") is True
        assert kwargs.get("trigger_sync") is True


def test_2135076010_not_proposed():
    """Vérifie que l'addon 2135076010 (Anki_EDN_nid) n'est plus proposé ni dans le catalogue ni dans config."""
    # 1. Non présent dans le catalogue des add-ons recommandés
    catalog_ids = [item["id"] for item in RECOMMENDED_ADDONS_CATALOG]
    assert "2135076010" not in catalog_ids

    # 2. Non présent dans config.json
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_file = os.path.join(cur_dir, "config.json")
    with open(cfg_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    assert 2135076010 not in cfg.get("addons", [])

    # 3. Non présent dans missing_addons par défaut
    with patch("Anki_EDN_Installer.setup_assistant.mw") as fake_mw:
        fake_mw.addonManager.allAddons.return_value = []
        fake_mw.addonManager.getConfig.return_value = cfg
        missing = missing_addons()
        assert 2135076010 not in missing

def test_nid_removed_from_shared_menu_and_present_in_preferences(qapp):
    """Vérifie que anki_edn_nid est exclu de shared_menu et que Réparer les NID est dans les préférences."""
    from Anki_EDN_Installer.shared_menu import register_module, _get_registry, _ensure_standard_menu_actions
    from aqt.qt import QMenu, QAction

    # 1. register_module refuse anki_edn_nid
    assert register_module("anki_edn_nid", "Anki EDN - nid", "Test") is False
    assert "anki_edn_nid" not in _get_registry()

    # 2. _ensure_standard_menu_actions retire toute action liée à Réparer les NID
    fake_menu = QMenu()
    act = QAction("Réparer les NID", fake_menu)
    act.setObjectName("EDN_Action_anki_edn_nid_Réparer les NID")
    fake_menu.addAction(act)
    assert len(fake_menu.actions()) == 1

    _ensure_standard_menu_actions(fake_menu)
    action_texts = [a.text() for a in fake_menu.actions()]
    assert "Réparer les NID" not in action_texts

    # 3. EDNSettingsDialog instancie btn_repair_nid
    from Anki_EDN_Installer.settings_dialog import EDNSettingsDialog
    with patch("aqt.mw") as fake_mw:
        fake_mw.addonManager = None
        fake_mw.col = None
        fake_mw.pm = None
        dialog = EDNSettingsDialog(parent=None)
        try:
            assert hasattr(dialog, "btn_repair_nid")
            assert dialog.btn_repair_nid.text() == "Réparer les NID"
            assert hasattr(dialog, "_on_repair_nid_clicked")
        finally:
            dialog.close()
