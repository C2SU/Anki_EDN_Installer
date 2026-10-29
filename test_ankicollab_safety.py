"""
Tests exhaustifs de sécurité des cartes, des révisions et de l'intégrité du deck
vis-à-vis d'AnkiCollab et d'AnkiWeb.
"""

import os
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch

from anki.storage import Collection
from anki.consts import QUEUE_TYPE_REV, CARD_TYPE_REV

from Anki_EDN_Installer.filtered_decks import (
    ROOT_DECK_NAME,
    analyze_edn_curriculum,
    generate_filtered_hierarchy,
    empty_all_edn_filtered_decks,
    rebuild_all_edn_filtered_decks,
    delete_all_edn_filtered_decks,
    get_edn_filtered_deck_ids,
    on_sync_will_start,
    on_sync_did_finish,
    save_filtered_decks_settings,
)


@pytest.fixture
def anki_test_col():
    """Crée une collection Anki temporaire et isolée avec deck EDN et notes étiquetées."""
    tmpdir = tempfile.mkdtemp()
    col_path = os.path.join(tmpdir, "edn_safety_test.anki2")
    col = Collection(col_path)

    res = col.decks.add_normal_deck_with_name("Anki EDN")
    edn_did = res.id
    notetype = col.models.by_name("Basic")

    # Création de 10 notes pour l'Item 224 (Cardiologie)
    for i in range(10):
        n = col.new_note(notetype)
        n.fields[0] = f"Question HTA {i}"
        n.fields[1] = f"Réponse HTA {i}"
        n.tags = ["EDN::item-224-HTA", "Cardiologie", "Rang_A"]
        col.add_note(n, edn_did)

    # Création de 5 notes pour l'Item 203 (Pneumologie)
    for i in range(5):
        n = col.new_note(notetype)
        n.fields[0] = f"Question Dyspnée {i}"
        n.fields[1] = f"Réponse Dyspnée {i}"
        n.tags = ["EDN::item-203-Dyspnee", "Pneumologie", "Rang_B"]
        col.add_note(n, edn_did)

    yield col, edn_did

    col.close()
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_card_safety_and_odid_isolation(anki_test_col):
    """
    Vérifie qu'aucune carte n'est altérée ou perdue lors de la génération,
    du vidage ou de la suppression de paquets filtrés.
    Vérifie l'intégrité de card.odid (Original Deck ID).
    """
    col, edn_did = anki_test_col
    initial_total_cards = len(col.find_cards(""))
    assert initial_total_cards == 15

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)

    # 1. Génération de paquets filtrés pour Cardiologie
    opts = {
        "root_name": ROOT_DECK_NAME,
        "scope": "volet_matiere",
        "card_filter": "all",
        "resched": True,
        "rebuild": True
    }
    res = generate_filtered_hierarchy(
        selected_specialties=["Cardiologie"],
        curriculum_data=curriculum,
        options=opts,
        col=col
    )
    assert res["success"] is True

    # 2. Vérification de l'isolation : les cartes de Cardio sont dans le paquet filtré
    cardio_cards = col.find_cards('"tag:EDN::item-224-HTA"')
    assert len(cardio_cards) == 10

    for cid in cardio_cards:
        card = col.get_card(cid)
        # La carte est dans le paquet filtré
        assert card.did != edn_did
        # La propriété odid référence obligatoirement le deck d'origine Anki EDN
        assert card.odid == edn_did

    # Les cartes Pneumo sont restées dans Anki EDN sans odid résiduel
    pneumo_cards = col.find_cards('"tag:EDN::item-203-Dyspnee"')
    for cid in pneumo_cards:
        card = col.get_card(cid)
        assert card.did == edn_did
        assert card.odid == 0

    # 3. Vidage de tous les paquets filtrés
    emptied_count = empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)
    assert emptied_count >= 1

    # Vérification que TOUTES les cartes sans exception sont de retour dans Anki EDN
    for cid in col.find_cards(""):
        card = col.get_card(cid)
        assert card.did == edn_did
        assert card.odid == 0

    # Aucun contenu de note n'a été modifié
    assert len(col.find_cards("")) == initial_total_cards
    note_sample = col.get_note(col.find_notes('"tag:EDN::item-224-HTA"')[0])
    assert "Question HTA" in note_sample.fields[0]
    assert "Rang_A" in note_sample.tags

    # 4. Suppression complète de l'arborescence : 0 carte perdue
    deleted = delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)
    assert deleted is True
    assert len(col.find_cards("")) == initial_total_cards
    assert len(get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)) == 0


def test_review_safety_and_fsrs_scheduling(anki_test_col):
    """
    Vérifie que les révisions effectuées dans un paquet filtré avec rééchelonnement
    actif mettent à jour revlog et le scheduling de manière pérenne,
    et que ces révisions sont conservées lors du vidage dans le deck principal.
    """
    col, edn_did = anki_test_col
    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)

    # Générer le paquet filtré avec rééchelonnement activé (resched=True)
    generate_filtered_hierarchy(
        selected_specialties=["Cardiologie"],
        curriculum_data=curriculum,
        options={"rebuild": True, "card_filter": "all", "resched": True},
        col=col
    )

    cardio_cards = col.find_cards('"tag:EDN::item-224-HTA"')
    target_cid = cardio_cards[0]
    card = col.get_card(target_cid)

    # État initial de la carte : Nouvelle
    assert card.reps == 0
    assert card.queue == 0  # Queue new

    # Simuler une réponse dans Anki
    # Passage en revue avec intervalle
    card.type = CARD_TYPE_REV
    card.queue = QUEUE_TYPE_REV
    card.reps = 1
    card.ivl = 3  # Nouvel intervalle de 3 jours
    card.due = 100
    col.update_card(card)

    import time
    now_ms = int(time.time() * 1000)

    # Enregistrement dans le revlog
    col.db.execute(
        "INSERT INTO revlog (id, cid, usn, ease, ivl, lastIvl, factor, time, type) "
        "VALUES (?, ?, -1, 3, 3, 0, 2500, 15000, 1)",
        now_ms, target_cid
    )

    # Vérification que le log existe
    logs = col.db.all("SELECT * FROM revlog WHERE cid = ?", target_cid)
    assert len(logs) == 1
    assert logs[0][4] == 3  # ivl = 3

    # Vider le paquet filtré
    empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    # Vérification dans le paquet d'origine :
    # La carte réintégrée a conservé son intervalle et son nombre de révisions !
    restored_card = col.get_card(target_cid)
    assert restored_card.did == edn_did
    assert restored_card.odid == 0
    assert restored_card.reps == 1
    assert restored_card.ivl == 3

    # L'historique revlog est intact
    logs_after = col.db.all("SELECT * FROM revlog WHERE cid = ?", target_cid)
    assert len(logs_after) == 1

    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)


def test_ankicollab_sync_guard_hooks(anki_test_col):
    """
    Vérifie que les hooks de synchronisation protègent AnkiCollab :
    - on_sync_will_start vide tous les paquets filtrés pour qu'AnkiCollab ne rencontre que odid=0.
    - on_sync_did_finish reconstruit les paquets après la fin du sync.
    """
    col, edn_did = anki_test_col
    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)

    # Créer les paquets filtrés
    generate_filtered_hierarchy(
        selected_specialties=["Cardiologie"],
        curriculum_data=curriculum,
        options={"rebuild": True, "card_filter": "all"},
        col=col
    )

    # Avant synchro : des cartes ont odid != 0
    cards_with_odid = [col.get_card(cid) for cid in col.find_cards("") if col.get_card(cid).odid != 0]
    assert len(cards_with_odid) > 0

    # Déclenchement du garde-fou de synchronisation
    save_filtered_decks_settings({"auto_sync": True})
    on_sync_will_start(col=col)

    # Après on_sync_will_start : AUCUNE carte n'a d'odid résiduel
    cards_with_odid_after = [col.get_card(cid) for cid in col.find_cards("") if col.get_card(cid).odid != 0]
    assert len(cards_with_odid_after) == 0

    # Toutes les cartes sont dans le deck principal
    for cid in col.find_cards(""):
        c = col.get_card(cid)
        assert c.did == edn_did
        assert c.odid == 0

    # Déclenchement de la fin de synchronisation
    with patch("aqt.utils.tooltip"):
        on_sync_did_finish(col=col)

    # Les paquets filtrés ont été reconstruits automatiquement
    rebuilt_cards = [col.get_card(cid) for cid in col.find_cards("") if col.get_card(cid).odid == edn_did]
    assert len(rebuilt_cards) == 10

    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)


def test_ankicollab_sync_guard_does_not_rebuild_emptied_subdecks(anki_test_col):
    """
    Vérifie formellement que si les sous-paquets ont été vidés par l'utilisateur,
    la synchronisation ne les reconstruit PAS.
    """
    col, edn_did = anki_test_col
    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)

    # Créer les paquets filtrés
    generate_filtered_hierarchy(
        selected_specialties=["Cardiologie"],
        curriculum_data=curriculum,
        options={"rebuild": True, "card_filter": "all"},
        col=col
    )

    # L'utilisateur vide tous les sous-paquets
    empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)
    assert len([cid for cid in col.find_cards("") if col.get_card(cid).odid != 0]) == 0

    # Déclenchement du début de synchronisation
    on_sync_will_start(col=col)

    # Déclenchement de la fin de synchronisation
    with patch("aqt.utils.tooltip") as mock_tooltip:
        on_sync_did_finish(col=col)
        # Aucun tooltip ne doit être affiché car rien n'a été restauré
        mock_tooltip.assert_not_called()

    # Vérification : 0 carte dans les paquets filtrés
    rebuilt_cards = [col.get_card(cid) for cid in col.find_cards("") if col.get_card(cid).odid != 0]
    assert len(rebuilt_cards) == 0

    # Toutes les cartes sont intactes dans le deck EDN principal
    for cid in col.find_cards(""):
        c = col.get_card(cid)
        assert c.did == edn_did
        assert c.odid == 0

    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)


