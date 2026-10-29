# -*- coding: utf-8 -*-
"""
Tests unitaires pour l'assistant d'installation et de configuration EDN.
Vérifie la création du préréglage de révision FSRS 88%, l'assignation aux paquets EDN,
la suspension ciblée des cartes taggées EDN, la détection des étapes déjà appliquées
et la persistance au démarrage (une seule exécution à l'installation).
"""
import os
import tempfile
import shutil
from unittest.mock import MagicMock
import pytest

from anki.storage import Collection
from aqt import mw
from aqt.qt import QApplication

from Anki_EDN_Installer.setup_assistant import (
    apply_edn_deck_preset,
    suspend_initial_edn_cards,
    apply_global_ankicollab_settings,
    detect_global_settings_status,
    detect_nid_repair_status,
    detect_edn_preset_status,
    detect_initial_suspension_status,
    detect_all_setup_statuses,
    EDNSetupAssistantDialog,
    check_startup_assistant,
)


@pytest.fixture
def temp_anki_col():
    tmpdir = tempfile.mkdtemp()
    col_path = os.path.join(tmpdir, "setup_test.anki2")
    col = Collection(col_path)

    # Deck principal EDN
    edn_res = col.decks.add_normal_deck_with_name("Anki EDN")
    edn_did = edn_res.id

    # Autre deck sans rapport
    other_res = col.decks.add_normal_deck_with_name("Général")
    other_did = other_res.id

    notetype = col.models.by_name("Basic")

    # 3 notes EDN
    for i in range(3):
        n = col.new_note(notetype)
        n.fields[0] = f"EDN Question {i}"
        n.fields[1] = f"EDN Réponse {i}"
        n.tags = [f"EDN::item-{i}"]
        col.add_note(n, edn_did)

    # 2 notes non-EDN
    for i in range(2):
        n = col.new_note(notetype)
        n.fields[0] = f"Other Question {i}"
        n.fields[1] = f"Other Réponse {i}"
        col.add_note(n, other_did)

    yield col, edn_did, other_did

    col.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_apply_edn_deck_preset(temp_anki_col):
    """Vérifie la configuration du préréglage FSRS 88% et son affectation au deck Anki EDN."""
    col, edn_did, other_did = temp_anki_col

    ok, msg = apply_edn_deck_preset(col=col)
    assert ok is True
    assert "FSRS 88%" in msg

    # FSRS doit être activé au niveau de la collection
    assert col.get_config("fsrs") is True

    # Le préréglage "Anki EDN" doit exister avec les paramètres recommandés
    edn_conf = None
    for c in col.decks.all_config():
        if c.get("name") == "Anki EDN":
            edn_conf = c
            break

    assert edn_conf is not None
    assert edn_conf["new"]["perDay"] == 30
    assert edn_conf["new"]["bury"] is True
    assert edn_conf["rev"]["perDay"] == 9999
    assert edn_conf["rev"]["bury"] is True
    assert edn_conf["lapse"]["leechFails"] == 20
    assert edn_conf["lapse"]["leechAction"] == 1  # Suspend
    assert edn_conf["desiredRetention"] == 0.88

    # Le deck Anki EDN doit utiliser cette configuration
    edn_deck = col.decks.get(edn_did)
    assert edn_deck.get("conf") == edn_conf["id"]


def test_suspend_initial_edn_cards(temp_anki_col):
    """Vérifie la suspension ciblée des cartes taggées EDN."""
    col, edn_did, other_did = temp_anki_col

    # Avant suspension : toutes les cartes sont en file nouvelle (queue = 0)
    edn_cids = col.find_cards("tag:EDN*")
    assert len(edn_cids) == 3
    for cid in edn_cids:
        assert col.get_card(cid).queue == 0

    other_cids = col.find_cards('"deck:Général"')
    assert len(other_cids) == 2

    # Exécution de la suspension initiale
    ok, msg = suspend_initial_edn_cards(col=col)
    assert ok is True
    assert "3 carte(s) EDN suspendue(s)" in msg

    # Après suspension : les cartes EDN sont suspendues (queue = -1)
    for cid in edn_cids:
        assert col.get_card(cid).queue == -1

    # Les autres cartes ne doivent pas être affectées
    for cid in other_cids:
        assert col.get_card(cid).queue == 0


def test_detect_edn_preset_status(temp_anki_col):
    """Vérifie que la détection du préréglage passe de non configuré à déjà configuré sans imposer de taux strict."""
    col, edn_did, other_did = temp_anki_col

    # Au départ, FSRS non activé et aucun preset "Anki EDN"
    s1 = detect_edn_preset_status(col=col)
    assert s1["done"] is False
    assert s1["badge"] == "À activer"

    # Après application standard (88%)
    apply_edn_deck_preset(col=col)
    s2 = detect_edn_preset_status(col=col)
    assert s2["done"] is True
    assert s2["badge"] == "Déjà configuré"
    assert "FSRS 88%" in s2["details"]

    # Modification personnalisée du taux par l'utilisateur (ex: 92%)
    for c in col.decks.all_config():
        if c.get("name") == "Anki EDN":
            c["desiredRetention"] = 0.92
            col.decks.update_config(c)
            break

    # Tant que FSRS est actif, le taux n'invalide pas la détection
    s3 = detect_edn_preset_status(col=col)
    assert s3["done"] is True
    assert s3["badge"] == "Déjà configuré"
    assert "FSRS 92%" in s3["details"]


def test_detect_initial_suspension_status(temp_anki_col, monkeypatch):
    """Vérifie que la détection de suspension identifie les cartes nouvelles non suspendues."""
    col, edn_did, other_did = temp_anki_col
    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.get_config", lambda: {})

    # Au départ, 3 cartes EDN neuves non suspendues
    s1 = detect_initial_suspension_status(col=col)
    assert s1["done"] is False
    assert s1["badge"] == "À appliquer"
    assert "3" in s1["details"]

    # Après suspension
    suspend_initial_edn_cards(col=col)
    s2 = detect_initial_suspension_status(col=col)
    assert s2["done"] is True
    assert s2["badge"] == "Déjà configuré"


def test_detect_nid_repair_status(temp_anki_col, tmp_path, monkeypatch):
    """Vérifie la détection d'alignement des NID sur mapping simulé."""
    col, edn_did, other_did = temp_anki_col

    # 1. Aucun mapping -> considéré à jour
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant._get_nid_mapping_path", lambda: None)
    s1 = detect_nid_repair_status(col=col)
    assert s1["done"] is True
    assert s1["pending"] == 0

    # 2. Création d'un mapping avec un ID différent d'une note existante
    notes = col.db.all("SELECT guid, id FROM notes LIMIT 1")
    guid, nid = notes[0]
    map_file = tmp_path / "nid_mapping.txt"
    # Admin ID différent (nid + 9999)
    map_file.write_text(f"{guid},{nid + 9999}\n", encoding="utf-8")
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant._get_nid_mapping_path", lambda: str(map_file))

    s2 = detect_nid_repair_status(col=col)
    assert s2["done"] is False
    assert s2["pending"] == 1
    assert "1 à réparer" in s2["badge"]

    # 3. Mapping aligné avec le NID actuel
    map_file.write_text(f"{guid},{nid}\n", encoding="utf-8")
    s3 = detect_nid_repair_status(col=col)
    assert s3["done"] is True
    assert s3["pending"] == 0
    assert s3["badge"] == "Déjà synchronisé"


def test_detect_global_settings_status(monkeypatch):
    """Vérifie la détection des options globales AnkiCollab & AnkiWeb."""
    mock_mgr = MagicMock()
    mock_mgr.allAddons.return_value = ["1957538407"]
    mock_mgr.getConfig.return_value = {
        "settings": {"pull_on_startup": True, "suspend_new_cards": True}
    }

    mock_profile = {"autoSync": True, "syncMedia": True}
    mock_pm = MagicMock()
    mock_pm.profile = mock_profile

    fake_mw = MagicMock()
    fake_mw.addonManager = mock_mgr
    fake_mw.pm = mock_pm

    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    res = detect_global_settings_status()
    assert res["done"] is True
    assert res["badge"] == "Déjà configuré"

    # Si autoSync est inactif
    mock_profile["autoSync"] = False
    res2 = detect_global_settings_status()
    assert res2["done"] is False
    assert res2["badge"] == "Partiellement configuré"


def test_dialog_unchecks_done_moves(temp_anki_col, monkeypatch):
    """Vérifie que la boîte de dialogue décoche par défaut les actions déjà exécutées."""
    col, edn_did, other_did = temp_anki_col

    # Appliquer préréglage et suspension
    apply_edn_deck_preset(col=col)
    suspend_initial_edn_cards(col=col)

    fake_mw = MagicMock()
    fake_mw.col = col
    fake_mw.pm = MagicMock()
    fake_mw.pm.profile = {"autoSync": False, "syncMedia": False}
    fake_mw.addonManager = MagicMock()
    fake_mw.addonManager.allAddons.return_value = []
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    app = QApplication.instance() or QApplication([])

    dialog = EDNSetupAssistantDialog(parent=None, is_startup=False, col=col)

    # Preset et Suspend sont faits -> non cochés
    assert dialog.cb_preset.isChecked() is False
    assert dialog.cb_suspend.isChecked() is False

    # Options globales non faites -> cochées
    assert dialog.cb_options.isChecked() is True

    dialog.close()


def test_startup_persistence_only_once(monkeypatch):
    """Vérifie que l'assistant à l'installation enregistre son affichage et ne s'affiche plus aux sessions suivantes."""
    config_store = {}

    def fake_get_config():
        return config_store

    def fake_save_config(cfg):
        config_store.update(cfg)

    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.get_config", fake_get_config)
    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.save_config", fake_save_config)

    fake_mw = MagicMock()
    fake_mw.col = None
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    app = QApplication.instance() or QApplication([])

    # 1. Première exécution au démarrage
    dialog = EDNSetupAssistantDialog(parent=None, is_startup=True, col=None)
    assert config_store.get("setup_assistant_shown") is True
    dialog.close()

    # 2. Vérification startup check : doit retourner immédiatement sans ouvrir
    called = []
    monkeypatch.setattr(
        "Anki_EDN_Installer.setup_assistant.open_setup_assistant_dialog",
        lambda *args, **kwargs: called.append(True)
    )

    check_startup_assistant()
    assert len(called) == 0  # Ne s'affiche plus !
