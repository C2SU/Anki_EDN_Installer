# -*- coding: utf-8 -*-
"""
Tests unitaires pour le téléchargement d'add-ons depuis l'onglet Addons de EDNSettingsDialog.
Vérifie que le clic sur la case (checkbox ou carte) d'un add-on non installé déclenche
effectivement son téléchargement via download_addons d'AnkiWeb.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from aqt.qt import *

from Anki_EDN_Installer.settings_dialog import (
    EDNSettingsDialog,
    RECOMMENDED_ADDONS_CATALOG,
)


@pytest.fixture
def fake_mw(monkeypatch):
    mock_mw = MagicMock()
    mock_mw.addonManager.allAddons.return_value = ["1957538407"]  # AnkiCollab installé seulement
    mock_mw.addonManager.isEnabled.return_value = True
    mock_mw.pm.profile = {}
    mock_mw.pm.name = "TestProfile"
    mock_mw.col = MagicMock()
    mock_mw.progress = MagicMock()
    monkeypatch.setattr("Anki_EDN_Installer.settings_dialog.mw", mock_mw)
    return mock_mw


def test_catalog_all_ids_are_numeric_or_have_numeric_alt():
    """Vérifie que chaque entrée de RECOMMENDED_ADDONS_CATALOG dispose d'un ID numérique valide pour AnkiWeb."""
    for item in RECOMMENDED_ADDONS_CATALOG:
        aid_raw = item.get("id")
        has_numeric = aid_raw and str(aid_raw).isdigit()
        if not has_numeric:
            has_numeric = any(alt and str(alt).isdigit() for alt in item.get("alt_ids", []))
        assert has_numeric, f"L'add-on {item['name']} n'a aucun identifiant numérique AnkiWeb : {item}"


def test_click_checkbox_not_installed_triggers_download(fake_mw, monkeypatch, qtbot):
    """Vérifie que cocher/cliquer la case d'un add-on non installé lance download_addons."""
    download_addons_mock = MagicMock()
    monkeypatch.setattr("aqt.addons.download_addons", download_addons_mock)

    dialog = EDNSettingsDialog()
    qtbot.addWidget(dialog)

    # Trouver une ligne non installée (ex: 1052724801 ou 1674438508)
    uninstalled_row = None
    for row in dialog.addon_rows:
        if row["status"] == "not_installed":
            uninstalled_row = row
            break

    assert uninstalled_row is not None, "Aucun add-on non installé trouvé dans les lignes"
    item = uninstalled_row["item"]
    cb = uninstalled_row["checkbox"]

    # Simuler le clic utilisateur sur la case à cocher
    cb.setChecked(True)
    cb.clicked.emit(True)

    # Vérifier que download_addons a été appelé avec l'ID numérique attendu
    assert download_addons_mock.called
    call_args = download_addons_mock.call_args[0]
    # Signature: (parent, mgr, [aid_int], on_done)
    assert call_args[0] == dialog
    assert call_args[1] == fake_mw.addonManager
    expected_id = int(item["id"]) if str(item["id"]).isdigit() else [int(a) for a in item["alt_ids"] if str(a).isdigit()][0]
    assert call_args[2] == [expected_id]

    # Simuler la complétion du téléchargement
    on_done_callback = call_args[3]
    fake_ok = MagicMock()
    fake_ok.__class__.__name__ = "InstallOk"
    fake_ok.name = item["name"]

    with patch("aqt.utils.tooltip") as mock_tooltip:
        on_done_callback([(expected_id, fake_ok)])

    assert uninstalled_row["status"] == "installed_active"
    assert uninstalled_row["matched_id"] == str(expected_id)
    assert cb.isChecked() is True
    assert dialog.restart_needed is True
    assert mock_tooltip.called


def test_click_card_not_installed_triggers_download(fake_mw, monkeypatch, qtbot):
    """Vérifie que cliquer sur la carte d'un add-on non installé déclenche le téléchargement."""
    download_addons_mock = MagicMock()
    monkeypatch.setattr("aqt.addons.download_addons", download_addons_mock)

    dialog = EDNSettingsDialog()
    qtbot.addWidget(dialog)

    uninstalled_row = None
    for row in dialog.addon_rows:
        if row["status"] == "not_installed":
            uninstalled_row = row
            break

    assert uninstalled_row is not None
    cb = uninstalled_row["checkbox"]
    item = uninstalled_row["item"]

    # Trouver le card_frame parent de cb
    card_frame = cb.parentWidget()
    assert card_frame is not None

    # Simuler mousePressEvent sur le card_frame
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    card_frame.mousePressEvent(event)

    assert download_addons_mock.called
    assert cb.isChecked() is True


def test_download_failure_restores_checkbox(fake_mw, monkeypatch, qtbot):
    """Vérifie qu'en cas d'erreur de téléchargement, la case est décochée et l'état reste not_installed."""
    download_addons_mock = MagicMock()
    monkeypatch.setattr("aqt.addons.download_addons", download_addons_mock)

    dialog = EDNSettingsDialog()
    qtbot.addWidget(dialog)

    uninstalled_row = [r for r in dialog.addon_rows if r["status"] == "not_installed"][0]
    cb = uninstalled_row["checkbox"]

    cb.setChecked(True)
    cb.clicked.emit(True)

    call_args = download_addons_mock.call_args[0]
    on_done_callback = call_args[3]

    fake_err = Exception("Erreur de connexion réseau")
    with patch("aqt.addons.show_log_to_user"):
        on_done_callback([(12345, fake_err)])

    assert cb.isChecked() is False
    assert uninstalled_row["status"] == "not_installed"


def test_catalog_shortcuts_and_symbols_ids():
    """Vérifie que 353547840 est proposé pour les raccourcis (et non 1762336370), et que 2040501954 n'a pas 1762336370 en alt_id."""
    catalog_ids = [item["id"] for item in RECOMMENDED_ADDONS_CATALOG]
    assert "353547840" in catalog_ids, "353547840 (Customize Keyboard Shortcuts) doit être proposé dans le catalogue"
    assert "1762336370" not in catalog_ids, "1762336370 ne doit pas être proposé en identifiant principal"

    symbols_item = next(item for item in RECOMMENDED_ADDONS_CATALOG if item["id"] == "2040501954")
    assert "1762336370" not in symbols_item.get("alt_ids", []), "1762336370 n'est pas un symbole mais un gestionnaire de raccourcis"


def test_download_symbols_addon_triggers_edn_symbols_push(fake_mw, monkeypatch, qtbot):
    """Vérifie que le téléchargement de Symbols As You Type (2040501954) déclenche l'import des symboles médicaux."""
    download_addons_mock = MagicMock()
    monkeypatch.setattr("aqt.addons.download_addons", download_addons_mock)

    import_symbols_mock = MagicMock(return_value=(True, "OK", 100))
    monkeypatch.setattr("Anki_EDN_Installer.settings_dialog.import_edn_symbols", import_symbols_mock)

    dialog = EDNSettingsDialog()
    qtbot.addWidget(dialog)

    symbols_row = next(r for r in dialog.addon_rows if r["item"]["id"] == "2040501954")
    cb = symbols_row["checkbox"]

    cb.setChecked(True)
    cb.clicked.emit(True)

    assert download_addons_mock.called
    call_args = download_addons_mock.call_args[0]
    on_done_callback = call_args[3]

    fake_ok = MagicMock()
    fake_ok.__class__.__name__ = "InstallOk"
    fake_ok.name = "Symbols As You Type"

    with patch("aqt.utils.tooltip"):
        on_done_callback([(2040501954, fake_ok)])

    assert import_symbols_mock.called
    assert import_symbols_mock.call_args[1].get("force") is True

