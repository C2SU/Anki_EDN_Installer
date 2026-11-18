# -*- coding: utf-8 -*-
"""
Tests unitaires pour l'assistant d'installation et de configuration EDN (incluant anki_edn_setup).
Vérifie la création du préréglage de révision FSRS 88%, l'assignation aux paquets EDN,
la suspension ciblée des cartes taggées EDN, la détection des étapes déjà appliquées,
la persistance d'état du profil (anki_edn_setup), la détection des extensions requises
et la synchronisation préalable.
"""
import os
import time
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
    detect_required_addons_status,
    detect_all_setup_statuses,
    EDNSetupAssistantDialog,
    check_startup_assistant,
    get_state,
    set_state,
    missing_addons,
    finalize,
    sync_first_then,
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
    assert "FSRS" in msg

    # FSRS doit être activé au niveau de la collection
    assert col.get_config("fsrs") is True

    # Le préréglage "Anki EDN" doit exister avec les paramètres recommandés
    edn_conf = None
    for c in col.decks.all_config():
        if c.get("name") == "Anki EDN":
            edn_conf = c
            break

    assert edn_conf is not None
    assert edn_conf["new"]["perDay"] == 50
    assert edn_conf["new"]["bury"] is True
    assert edn_conf["rev"]["perDay"] == 9999
    assert edn_conf["rev"]["bury"] is True
    assert edn_conf["lapse"]["leechFails"] == 12
    assert edn_conf["lapse"]["leechAction"] == 0  # Suspendre
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


def test_detect_suspension_status_with_active_pool(temp_anki_col, monkeypatch):
    """Vérifie que detect_initial_suspension_status considère le deck déjà configuré si la majorité est suspendue ou apprise."""
    col, edn_did, other_did = temp_anki_col

    def fake_find_cards(query):
        if "is:new -is:suspended" in query:
            return list(range(2027))
        elif "is:suspended" in query:
            return list(range(15000))
        elif "-is:new" in query:
            return list(range(2973))
        elif "tag:EDN*" in query:
            return list(range(20000))
        return []

    monkeypatch.setattr(col, "find_cards", fake_find_cards)
    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.get_config", lambda: {})

    status = detect_initial_suspension_status(col=col)
    assert status["done"] is True
    assert status["badge"] == "Déjà configuré"
    assert "2027 actives" in status["details"] or "15000" in status["details"]


def test_state_persistence_and_missing_addons(monkeypatch):
    """Vérifie get_state/set_state et la détection des add-ons requis avec alias locaux."""
    profile_dict = {}
    fake_mw = MagicMock()
    fake_mw.pm.profile = profile_dict
    fake_mw.addonManager.getConfig.return_value = None
    fake_mw.addonManager.allAddons.return_value = [
        "1957538407",
        "1052724801",
        "1762336370",
        "2110939339",
        "24411424",
        "2040501954",
        "Anki_EDN_NID",             # Alias local pour 2135076010
        "Anki_EDN_Stats",           # Alias local pour 1674438508
        "Anki_EDN_Lier_les_cartes", # Alias local pour 445658251
    ]
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    state = get_state()
    assert state["stage"] == "start"
    assert state["already_studied"] is False

    set_state(stage="done", already_studied=True)
    updated = get_state()
    assert updated["stage"] == "done"
    assert updated["already_studied"] is True

    # Tous les add-ons requis sont installés (via ID ou alias local)
    assert missing_addons() == []
    status = detect_required_addons_status()
    assert status["done"] is True
    assert status["badge"] == "Déjà configuré"


def test_finalize_distinguishes_already_studied(temp_anki_col, monkeypatch):
    """Vérifie que finalize() ne suspend pas les cartes d'un ancien utilisateur (already_studied=True)."""
    col, edn_did, other_did = temp_anki_col

    profile_dict = {
        "anki_edn_setup": {
            "stage": "ankicollab",
            "already_studied": True,
        }
    }
    fake_mw = MagicMock()
    fake_mw.col = col
    fake_mw.pm.profile = profile_dict
    fake_mw.addonManager.allAddons.return_value = []
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.showInfo", lambda *a, **kw: None)

    finalize(col=col)

    # Stage passé à done
    assert get_state()["stage"] == "done"
    # Les cartes EDN ne sont PAS suspendues car already_studied=True
    for cid in col.find_cards('"deck:Anki EDN"'):
        assert col.get_card(cid).queue == 0


def test_sync_first_then_without_login(monkeypatch):
    """Vérifie que sync_first_then exécute directement le callback si non connecté à AnkiWeb."""
    fake_mw = MagicMock()
    fake_mw.pm.sync_auth.return_value = None
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    called = []
    sync_first_then(lambda: called.append(True))
    assert called == [True]


def test_setup_assistant_uses_symbols_addon_and_pushes_shortcuts(monkeypatch):
    """Vérifie que l'assistant d'installation cible 2040501954 pour les symboles et injecte les raccourcis."""
    from Anki_EDN_Installer.setup_assistant import DEFAULT_SETUP_CONFIG, install_addons

    assert 2040501954 in DEFAULT_SETUP_CONFIG["addons"]
    assert 1762336370 not in DEFAULT_SETUP_CONFIG["addons"]

    fake_mw = MagicMock()
    fake_mw.pm.profile = {}
    fake_mw.addonManager.getConfig.return_value = None
    fake_mw.addonManager.allAddons.return_value = []
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.showInfo", lambda *a, **kw: None)

    download_addons_mock = MagicMock()
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.download_addons", download_addons_mock)

    import_symbols_mock = MagicMock(return_value=(True, "OK", 50))
    monkeypatch.setattr("Anki_EDN_Installer.symbols_importer.import_edn_symbols", import_symbols_mock)

    done_called = []
    install_addons(on_complete=lambda: done_called.append(True))

    assert download_addons_mock.called
    call_args = download_addons_mock.call_args[0]
    missing_ids = call_args[2]
    assert 2040501954 in missing_ids

    # Simuler fin du téléchargement
    on_done_cb = call_args[3]
    on_done_cb([])

    assert import_symbols_mock.called
    assert import_symbols_mock.call_args[1].get("force") is True
    assert done_called == [True]


def test_default_config_uses_updated_edn_stat_and_no_auto_sync():
    """Vérifie la liste des greffons auto-installés (1674438508 pour EDN Stat, sans Auto Sync 501542723)."""
    from Anki_EDN_Installer.setup_assistant import DEFAULT_SETUP_CONFIG

    assert DEFAULT_SETUP_CONFIG["addons"] == [1957538407, 1052724801, 2040501954, 1674438508, 445658251]
    assert 501542723 not in DEFAULT_SETUP_CONFIG["addons"]
    assert 1201122026 not in DEFAULT_SETUP_CONFIG["addons"]
    assert DEFAULT_SETUP_CONFIG["options"]["new_per_day"] == 50
    assert DEFAULT_SETUP_CONFIG["options"]["leech_threshold"] == 12


def test_subscribe_ankicollab_directly_registers_and_pulls(monkeypatch):
    """Vérifie l'abonnement direct et le pull AnkiCollab via l'API interne de 1957538407 sans UI manuelle."""
    import sys
    import types
    from Anki_EDN_Installer.setup_assistant import subscribe_ankicollab_directly

    stored = {"settings": {}}
    written_configs = []
    subscribed_codes = []
    pulled_codes = []

    pkg = types.ModuleType("1957538407")
    am_mod = types.ModuleType("1957538407.auth_manager")
    am_mod.auth_manager = MagicMock()
    am_mod.auth_manager.is_logged_in.return_value = True

    cm_mod = types.ModuleType("1957538407.config_manager")
    cm_mod.get_stored_config = lambda: dict(stored)
    cm_mod.write_config = lambda cfg: written_configs.append(cfg)

    id_mod = types.ModuleType("1957538407.identifier")
    id_mod.subscribe_to_deck = lambda code: subscribed_codes.append(code) or True

    im_mod = types.ModuleType("1957538407.import_manager")
    im_mod.handle_pull = lambda code, silent=False: pulled_codes.append(code)

    vd_mod = types.ModuleType("1957538407.var_defs")
    vd_mod.DEFAULT_PROTECTED_TAGS = ["leech", "marked", "missing-media"]

    for name, mod in [
        ("1957538407", pkg),
        ("1957538407.auth_manager", am_mod),
        ("1957538407.config_manager", cm_mod),
        ("1957538407.identifier", id_mod),
        ("1957538407.import_manager", im_mod),
        ("1957538407.var_defs", vd_mod),
    ]:
        monkeypatch.setitem(sys.modules, name, mod)

    fake_mw = MagicMock()
    fake_mw.pm.profile = {}
    fake_mw.addonManager.getConfig.return_value = None
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    ok, status = subscribe_ankicollab_directly()
    assert ok is True
    assert status == "subscribed_and_pulled"
    assert subscribed_codes == ["mango-may-georgia-eleven-moon-orange"]
    assert pulled_codes == ["mango-may-georgia-eleven-moon-orange"]
    assert any("mango-may-georgia-eleven-moon-orange" in cfg for cfg in written_configs)


def test_card_styles_symbol_tooltips_injection(monkeypatch):
    """Vérifie l'injection par défaut du script d'infobulles sur symboles et abréviations médicales."""
    from Anki_EDN_Installer import card_styles

    fake_card = MagicMock(reps=1, type=2, queue=2, lapses=0)
    monkeypatch.setattr(card_styles, "load_prefs", lambda: {**card_styles.DEFAULT_PREFS, "showSymbolTooltips": True})
    html_on = card_styles._on_card_will_show("<div>☐ Vérifier PDCB et ◊ bilan</div>", fake_card, "reviewAnswer")
    assert "edn-sym-tip" in html_on
    assert "_ednApplySymbolTooltips" in html_on
    assert "Il faut / toujours" in html_on
    assert "Parfois / il est possible" in html_on
    assert "Perte de conscience brève" in html_on

    monkeypatch.setattr(card_styles, "load_prefs", lambda: {**card_styles.DEFAULT_PREFS, "showSymbolTooltips": False})
    html_off = card_styles._on_card_will_show("<div>☐ Vérifier PDCB</div>", fake_card, "reviewAnswer")
    assert "_ednApplySymbolTooltips" not in html_off


def test_dialog_skips_addons_page_and_imports_symbols_when_preinstalled(temp_anki_col, monkeypatch):
    """Vérifie le saut en 2 étapes et l'import auto des symboles quand les extensions sont préinstallées."""
    col, edn_did, other_did = temp_anki_col

    fake_mw = MagicMock()
    fake_mw.col = col
    fake_mw.pm = MagicMock()
    fake_mw.pm.profile = {"autoSync": False, "syncMedia": False}
    fake_mw.addonManager = MagicMock()
    fake_mw.addonManager.getConfig.return_value = None
    fake_mw.addonManager.allAddons.return_value = [
        "1957538407",
        "1052724801",
        "2040501954",
        "1674438508",
        "445658251",
    ]
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.mw", fake_mw)

    imported = []

    def fake_import(force=False):
        imported.append(force)
        return True, "OK", 10

    monkeypatch.setattr("Anki_EDN_Installer.symbols_importer.import_edn_symbols", fake_import)
    monkeypatch.setattr("Anki_EDN_Installer.setup_assistant.deck_card_count", lambda *a, **kw: 0)

    app = QApplication.instance() or QApplication([])
    dialog = EDNSetupAssistantDialog(parent=None, is_startup=False, col=col)

    assert len(imported) == 1
    assert dialog.stack.currentIndex() == 1
    assert "Étape 1 sur 2" in dialog.header_title.text()

    dialog._switch_page(2)
    assert "Étape 2 sur 2" in dialog.header_title.text()
    dialog.close()


def test_startup_resumes_after_addons_installed(monkeypatch):
    """Vérifie que l'assistant se rouvre au redémarrage après l'installation des greffons."""
    from Anki_EDN_Installer import setup_assistant

    config_store = {"setup_assistant_shown": True, "setup_assistant_completed": False}
    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.get_config", lambda: config_store)
    monkeypatch.setattr("Anki_EDN_Installer.shared_menu.save_config", lambda cfg: config_store.update(cfg))
    monkeypatch.setattr(setup_assistant, "get_state", lambda: {"stage": "addons_installed", "already_studied": False})
    monkeypatch.setattr(setup_assistant, "deck_card_count", lambda *a, **kw: 0)
    monkeypatch.setattr(setup_assistant, "detect_required_addons_status", lambda: {"done": True, "missing": []})
    monkeypatch.setattr(setup_assistant, "_ensure_symbols_imported_when_ready", lambda *a, **kw: None)
    monkeypatch.setattr(setup_assistant, "detect_all_setup_statuses", lambda *a, **kw: {"step": {"done": False}})

    fake_mw = MagicMock()
    fake_mw.col = MagicMock()
    fake_mw.progress.busy.return_value = False
    monkeypatch.setattr(setup_assistant, "mw", fake_mw)

    timers = []

    class FakeTimer:
        def __init__(self, parent=None):
            self.timeout = MagicMock()
            self._cb = None

            def connect(fn):
                self._cb = fn

            self.timeout.connect = connect
            timers.append(self)

        def start(self, ms):
            if self._cb:
                self._cb()

        def stop(self):
            pass

    monkeypatch.setattr(setup_assistant, "QTimer", FakeTimer)
    FakeTimer.singleShot = staticmethod(lambda ms, fn: fn())

    opened = []
    monkeypatch.setattr(setup_assistant, "sync_first_then", lambda cb: cb())
    monkeypatch.setattr(setup_assistant, "open_setup_assistant_dialog", lambda *a, **kw: opened.append(True))

    setup_assistant.check_startup_assistant()
    assert opened == [True]


def test_cpam_and_sst_abbreviations_present():
    """Vérifie la présence de CPAM et SST dans les infobulles d'abréviations."""
    from Anki_EDN_Installer import card_styles

    assert card_styles.ABBR_TOOLTIPS_MAP.get("CPAM") == "Caisse primaire d'assurance maladie"
    assert card_styles.ABBR_TOOLTIPS_MAP.get("SST") == "Service de Santé au Travail"


