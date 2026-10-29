"""

Tests unitaires pour le module de paquets filtrés EDN.

"""



import os

import tempfile

import shutil

import pytest



from anki.storage import Collection

from Anki_EDN_Installer.filtered_decks import (

    ROOT_DECK_NAME,

    clean_item_label,

    clean_specialty_name,

    is_specialty_tag,

    build_filtered_query,

    analyze_edn_curriculum,

    generate_filtered_hierarchy,

    empty_all_edn_filtered_decks,

    rebuild_all_edn_filtered_decks,

    delete_all_edn_filtered_decks,

    get_edn_filtered_deck_ids,

    get_active_edn_filtered_deck_ids,

    get_edn_deck_and_config,

    map_edn_review_order_to_filtered_order,

    sync_hierarchy_deck_options,

    load_filtered_decks_settings,

    save_filtered_decks_settings,

    DEFAULT_FILTERED_DECKS_SETTINGS,

    on_sync_will_start,

    on_sync_did_finish

)





def test_clean_item_label():

    num, label = clean_item_label("EDN::item-224-HTA")

    assert num == 224

    assert label == "Item 224 - HTA"



    num, label = clean_item_label("EDN::item-236-Troubles-conduction::BAV")

    assert num == 236

    assert label == "Item 236 - Troubles Conduction - BAV"



    num, label = clean_item_label("item-001-Relation-medecin-malade")

    assert num == 1

    assert "Item 001" in label





def test_specialty_filtering():

    assert is_specialty_tag("Cardiologie") is True

    assert is_specialty_tag("Pneumologie::Pathologies") is True

    assert is_specialty_tag("années::2024") is False

    assert is_specialty_tag("dfasm1") is False

    assert is_specialty_tag("EDN::item-203") is False

    assert is_specialty_tag("iconographie") is False

    assert is_specialty_tag("source::college") is False



    assert clean_specialty_name("cardiologie") == "Cardiologie"

    assert clean_specialty_name("pneumologie") == "Pneumologie"

    assert clean_specialty_name("gastro-enterologie") == "Gastro-entérologie"





def test_build_filtered_query_default_is_due_and_new():

    query = build_filtered_query(

        edn_deck="Anki EDN",

        item_tag="EDN::item-224-HTA",

        specialty="Cardiologie",

        scope="volet_matiere",

        card_filter="due_and_new",

        rank_filter="all"

    )

    assert 'deck:"Anki EDN"' in query

    assert '"tag:EDN::item-224-HTA*"' in query

    assert "tag:Cardiologie*" in query

    assert "(is:due or is:new)" in query





def test_build_filtered_query_item_complet_and_ranks():

    query = build_filtered_query(

        edn_deck="Anki EDN",

        item_tag="EDN::item-203-Dyspnee",

        specialty="Cardiologie",

        scope="item_complet",

        card_filter="all",

        rank_filter="A"

    )

    assert 'deck:"Anki EDN"' in query

    assert '"tag:EDN::item-203-Dyspnee*"' in query

    # Scope item_complet ne doit pas restreindre à la spécialité

    assert "tag:Cardiologie" not in query

    assert "(tag:Rang_A* or tag:rang::a*)" in query

    assert "is:due" not in query





@pytest.fixture

def temp_anki_collection():

    tmpdir = tempfile.mkdtemp()

    col_path = os.path.join(tmpdir, "test_edn.anki2")

    col = Collection(col_path)



    res = col.decks.add_normal_deck_with_name("Anki EDN")

    edn_did = res.id

    notetype = col.models.by_name("Basic")



    # Création Item 203 : 10 cartes (6 Pneumo = 60%, 4 Cardio = 40%)

    for i in range(6):

        n = col.new_note(notetype)

        n.fields[0] = f"Pneumo Q{i}"

        n.fields[1] = f"Pneumo A{i}"

        n.tags = ["EDN::item-203-Dyspnee", "Pneumologie", "Rang_A"]

        col.add_note(n, edn_did)



    for i in range(4):

        n = col.new_note(notetype)

        n.fields[0] = f"Cardio Q{i}"

        n.fields[1] = f"Cardio A{i}"

        n.tags = ["EDN::item-203-Dyspnee", "Cardiologie", "Rang_B"]

        col.add_note(n, edn_did)



    # Création Item 224 : 5 cartes 100% Cardio

    for i in range(5):

        n = col.new_note(notetype)

        n.fields[0] = f"HTA Q{i}"

        n.fields[1] = f"HTA A{i}"

        n.tags = ["EDN::item-224-HTA", "Cardiologie", "Rang_A"]

        col.add_note(n, edn_did)



    yield col



    col.close()

    shutil.rmtree(tmpdir, ignore_errors=True)





def test_analyze_edn_curriculum(temp_anki_collection):

    col = temp_anki_collection

    data = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    specs = data["specialties"]

    assert "Cardiologie" in specs

    assert "Pneumologie" in specs



    # Vérification que l'Item 203 apparaît sous Pneumo ET sous Cardio

    cardio_items = [it["tag"] for it in specs["Cardiologie"]["items"]]

    pneumo_items = [it["tag"] for it in specs["Pneumologie"]["items"]]



    assert "EDN::item-203-Dyspnee" in cardio_items

    assert "EDN::item-203-Dyspnee" in pneumo_items

    assert "EDN::item-224-HTA" in cardio_items

    assert "EDN::item-224-HTA" not in pneumo_items





def test_generate_and_lifecycle(temp_anki_collection):

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # 1. Génération pour Cardiologie

    opts = {

        "root_name": ROOT_DECK_NAME,

        "scope": "volet_matiere",

        "card_filter": "due_and_new",

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

    assert res["created_decks"] == 2  # Item 203 + Item 224

    assert res["rebuilt_cards"] == 9  # 4 cardio dyspnee + 5 cardio HTA



    # Vérification structure decks

    dids = get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    assert len(dids) == 2



    # 2. Vidage

    emptied = empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert emptied == 2



    edn_cards = col.find_cards('deck:"Anki EDN"')

    assert len(edn_cards) == 15  # Toutes les cartes sont réintégrées dans Anki EDN



    # 3. Reconstruction

    rebuilt = rebuild_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert rebuilt["count"] == 2

    assert rebuilt["total_cards"] == 9



    # 4. Suppression

    deleted = delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert deleted is True



    # Vérifier qu'aucune carte n'a été supprimée

    assert len(col.find_cards("")) == 15

    assert len(get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)) == 0





def test_generate_with_selected_items_filter(temp_anki_collection):

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # Ne générer que l'Item 224 pour Cardiologie (ignorer l'Item 203)

    opts = {

        "root_name": ROOT_DECK_NAME,

        "scope": "volet_matiere",

        "card_filter": "due_and_new",

        "resched": True,

        "rebuild": True

    }

    res = generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options=opts,

        col=col,

        selected_items={"Cardiologie": ["EDN::item-224-HTA"]}

    )



    assert res["success"] is True

    assert res["created_decks"] == 1  # Uniquement l'Item 224

    assert res["rebuilt_cards"] == 5  # 5 cartes HTA (au lieu de 9 avec Item 203)



    dids = get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    assert len(dids) == 1



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_sync_hooks_behavior(temp_anki_collection):

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # Créer les paquets

    generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options={"rebuild": True, "card_filter": "due_and_new"},

        col=col

    )



    # Avant synchro : vidage

    emptied = empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert emptied == 2

    for cid in col.find_cards(""):

        card = col.get_card(cid)

        # Aucune carte ne doit avoir un odid résiduel

        assert card.odid == 0



    # Après synchro : reconstruction automatique

    rebuilt = rebuild_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert rebuilt["count"] == 2

    assert rebuilt["total_cards"] == 9



    # Nettoyage final

    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_dialog_structure_and_no_stage(qapp):

    from aqt.qt import Qt

    from Anki_EDN_Installer.filtered_decks_dialog import FilteredDecksDialog



    dialog = FilteredDecksDialog()

    

    # 1. Vérifier que la partie stage a été complètement supprimée

    assert not hasattr(dialog, "stage_combo")

    assert not hasattr(dialog, "on_select_stage_clicked")



    # 2. Vérifier la présence des éléments de navigation améliorée

    assert hasattr(dialog, "search_input")

    assert hasattr(dialog, "filter_only_selected_cb")

    assert hasattr(dialog, "summary_label")

    assert hasattr(dialog, "order_combo")

    assert hasattr(dialog, "preset_info_label")

    assert dialog.tree_widget.isSortingEnabled() is True

    assert dialog.tree_widget.rootIsDecorated() is True



    # 3. Test de synchronisation parent / enfant

    # Simuler des items dans l'arbre

    from Anki_EDN_Installer.filtered_decks_dialog import CurriculumTreeWidgetItem

    parent = CurriculumTreeWidgetItem(dialog.tree_widget)

    parent.setText(0, "Cardiologie")

    parent.setCheckState(0, Qt.CheckState.Unchecked)



    child1 = CurriculumTreeWidgetItem(parent)

    child1.setText(0, "Item 224 - HTA")

    child1.item_tag = "EDN::item-224-HTA"

    child1.spec_cards = 10

    child1.setCheckState(0, Qt.CheckState.Unchecked)



    child2 = CurriculumTreeWidgetItem(parent)

    child2.setText(0, "Item 203 - Dyspnée")

    child2.item_tag = "EDN::item-203-Dyspnee"

    child2.spec_cards = 15

    child2.setCheckState(0, Qt.CheckState.Unchecked)



    dialog.specialty_items["Cardiologie"] = parent



    # Cocher parent -> coche tous les enfants

    parent.setCheckState(0, Qt.CheckState.Checked)

    dialog.on_item_changed(parent, 0)

    assert child1.checkState(0) == Qt.CheckState.Checked

    assert child2.checkState(0) == Qt.CheckState.Checked



    # Décocher child1 -> parent passe en PartiallyChecked

    child1.setCheckState(0, Qt.CheckState.Unchecked)

    dialog.on_item_changed(child1, 0)

    assert parent.checkState(0) == Qt.CheckState.PartiallyChecked



    # Décocher child2 -> parent passe en Unchecked

    child2.setCheckState(0, Qt.CheckState.Unchecked)

    dialog.on_item_changed(child2, 0)

    assert parent.checkState(0) == Qt.CheckState.Unchecked



    # 4. Test du filtrage par recherche textuelle

    dialog.filter_only_selected_cb.setChecked(False)

    dialog.search_input.setText("HTA")

    dialog.apply_filter()

    assert parent.isHidden() is False

    assert child1.isHidden() is False

    assert child2.isHidden() is True



    # Effacer la recherche

    dialog.search_input.setText("")

    dialog.apply_filter()

    assert child1.isHidden() is False

    assert child2.isHidden() is False



    # 5. Test Tout cocher et Tout décocher

    dialog.on_check_all_clicked()

    assert parent.checkState(0) == Qt.CheckState.Checked

    assert child1.checkState(0) == Qt.CheckState.Checked

    assert child2.checkState(0) == Qt.CheckState.Checked

    specs, items_map = dialog.get_selected_data()

    assert "Cardiologie" in specs

    assert len(items_map["Cardiologie"]) == 2



    dialog.on_uncheck_all_clicked()

    assert parent.checkState(0) == Qt.CheckState.Unchecked

    assert child1.checkState(0) == Qt.CheckState.Unchecked

    assert child2.checkState(0) == Qt.CheckState.Unchecked

    specs, items_map = dialog.get_selected_data()

    assert len(specs) == 0



    # 6. Test filtre "Sélection uniquement"

    child1.setCheckState(0, Qt.CheckState.Checked)

    dialog.on_item_changed(child1, 0)

    dialog.filter_only_selected_cb.setChecked(True)

    dialog.apply_filter()

    assert parent.isHidden() is False

    assert child1.isHidden() is False

    assert child2.isHidden() is True



    dialog.deleteLater()





def test_map_edn_review_order_to_filtered_order():

    # Défaut / Aucun conf

    assert map_edn_review_order_to_filtered_order(None) == 6

    assert map_edn_review_order_to_filtered_order({}) == 6



    # Ordre par jour / échéance (0, 1, 2) -> 6

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 0}) == 6

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 1}) == 6

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 2}) == 6



    # Intervalles croissants / décroissants (3, 4) -> (2, 3)

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 3}) == 2

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 4}) == 3



    # Retard relatif (9) -> 10

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 9}) == 10



    # Aléatoire (10) -> 1

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 10}) == 1



    # Ordre d'ajout (11) -> 5

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 11}) == 5



    # Dernier ajouté en premier (12) -> 7

    assert map_edn_review_order_to_filtered_order({"reviewOrder": 12}) == 7





def test_get_edn_deck_and_config(temp_anki_collection):

    col = temp_anki_collection

    deck_dict, conf_id, conf_dict = get_edn_deck_and_config(col)

    assert deck_dict is not None

    assert deck_dict["name"] == "Anki EDN"

    assert conf_id is not None

    assert conf_dict is not None





def test_hierarchy_inherits_edn_deck_options(temp_anki_collection):

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # 1. Configurer un preset personnalisé avec des options de révision distinctives

    edn_did = col.decks.id_for_name("Anki EDN")

    edn_deck = col.decks.get(edn_did)



    custom_conf = col.decks.add_config("EDN FSRS Preset")

    custom_conf_id = custom_conf["id"]

    custom_conf["reviewOrder"] = 11  # Ordre d'ajout

    custom_conf["rev"]["perDay"] = 9999

    custom_conf["desiredRetention"] = 0.82

    col.decks.update_config(custom_conf)



    col.decks.set_config_id_for_deck_dict(edn_deck, custom_conf_id)



    # 2. Générer l'arborescence des paquets filtrés

    opts = {

        "root_name": ROOT_DECK_NAME,

        "scope": "volet_matiere",

        "card_filter": "due_and_new",

        "order": "inherit",

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

    assert res["inherited_conf_id"] == custom_conf_id

    assert res["inherited_preset_name"] == "EDN FSRS Preset"

    assert res["order_used"] == 5  # Mappé automatiquement depuis reviewOrder=11



    # 3. Vérifier que le paquet racine normal a hérité du preset

    root_did = col.decks.id_for_name(ROOT_DECK_NAME)

    root_deck = col.decks.get(root_did)

    assert root_deck.get("conf") == custom_conf_id



    # 4. Vérifier que le dossier de spécialité normal a hérité du preset

    sp_did = col.decks.id_for_name(f"{ROOT_DECK_NAME}::Cardiologie")

    sp_deck = col.decks.get(sp_did)

    assert sp_deck.get("conf") == custom_conf_id



    # 5. Vérifier que les paquets filtrés feuilles ont l'ordre hérité et pas de surcharge de délais

    f_dids = get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    assert len(f_dids) > 0

    for fdid in f_dids:

        fdeck = col.decks.get(fdid)

        assert fdeck.get("dyn") == 1

        assert fdeck.get("resched") is True

        assert fdeck.get("delays") is None

        # Ordre de révision hérité : 5 (Order added)

        assert fdeck["terms"][0][2] == 5



    # 6. Vérifier le fonctionnement de sync_hierarchy_deck_options

    updated = sync_hierarchy_deck_options(ROOT_DECK_NAME, col=col)

    assert updated == 0  # Déjà tous synchronisés



    # Si on réinitialise manuellement un dossier à conf=1

    root_deck["conf"] = 1

    col.decks.save(root_deck)

    assert col.decks.get(root_did).get("conf") == 1



    # sync_hierarchy_deck_options doit réparer immédiatement l'héritage

    updated = sync_hierarchy_deck_options(ROOT_DECK_NAME, col=col)

    assert updated >= 1

    assert col.decks.get(root_did).get("conf") == custom_conf_id



    # Nettoyage

    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_explicit_order_override(temp_anki_collection):

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # Forcer l'ordre aléatoire (1)

    opts = {

        "root_name": ROOT_DECK_NAME,

        "scope": "volet_matiere",

        "card_filter": "due_and_new",

        "order": 1,

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

    assert res["order_used"] == 1



    f_dids = get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    for fdid in f_dids:

        fdeck = col.decks.get(fdid)

        assert fdeck["terms"][0][2] == 1



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_settings_persistence():

    """Vérifie la sauvegarde et le rechargement fidèle des réglages utilisateur."""

    custom_settings = {

        "threshold": 55,

        "scope": "item_complet",

        "card_filter": "due_only",

        "rank_filter": "B",

        "order": 1,

        "resched": False,

        "auto_sync": False,

        "filter_only_selected": True,

        "selected_specs": ["Neurologie"],

        "selected_items": {"Neurologie": ["EDN::item-090-AVC"]},

        "fully_checked_specs": ["Neurologie"]

    }



    saved = save_filtered_decks_settings(custom_settings)

    assert saved is True



    loaded = load_filtered_decks_settings()

    assert loaded["threshold"] == 55

    assert loaded["scope"] == "item_complet"

    assert loaded["card_filter"] == "due_only"

    assert loaded["rank_filter"] == "B"

    assert loaded["order"] == 1

    assert loaded["resched"] is False

    assert loaded["auto_sync"] is False

    assert loaded["filter_only_selected"] is True

    assert loaded["selected_specs"] == ["Neurologie"]

    assert loaded["selected_items"] == {"Neurologie": ["EDN::item-090-AVC"]}

    assert loaded["fully_checked_specs"] == ["Neurologie"]



    # Remise à l'état par défaut

    save_filtered_decks_settings(DEFAULT_FILTERED_DECKS_SETTINGS)











def test_dialog_rebuild_button_and_remember_settings(qapp):

    """Vérifie que le dialogue restaure les derniers réglages et comporte le bouton 'Régénérer les paquets'."""

    from aqt.qt import Qt

    from Anki_EDN_Installer.filtered_decks_dialog import FilteredDecksDialog, CurriculumTreeWidgetItem



    # 1. Sauvegarder des réglages préalables

    pre_settings = {

        "threshold": 35,

        "scope": "item_complet",

        "card_filter": "new_only",

        "rank_filter": "A",

        "order": 10,

        "resched": False,

        "auto_sync": False,

        "filter_only_selected": True,

        "selected_specs": ["Cardiologie"],

        "selected_items": {"Cardiologie": ["EDN::item-224-HTA"]},

        "fully_checked_specs": []

    }

    save_filtered_decks_settings(pre_settings)



    # 2. Ouvrir le dialogue

    dialog = FilteredDecksDialog()



    # Vérification des widgets pré-remplis

    assert dialog.threshold_spin.value() == 35

    assert dialog.radio_scope_item.isChecked() is True

    assert dialog.radio_scope_matiere.isChecked() is False

    assert dialog.status_combo.currentData() == "new_only"

    assert dialog.rank_combo.currentData() == "A"

    assert dialog.order_combo.currentData() == 10

    assert dialog.resched_checkbox.isChecked() is False

    assert dialog.auto_sync_checkbox.isChecked() is False

    assert dialog.filter_only_selected_cb.isChecked() is True



    # Vérification de la présence des boutons d'action

    assert hasattr(dialog, "rebuild_btn")

    assert dialog.rebuild_btn.text() == "Régénérer les paquets"

    assert "Reconstruit" in dialog.rebuild_btn.toolTip()



    assert hasattr(dialog, "empty_btn")

    assert dialog.empty_btn.text() == "Vider les paquets"



    # Vérification de la pré-sélection dans l'arbre (simulation d'items)

    parent = CurriculumTreeWidgetItem(dialog.tree_widget)

    parent.setText(0, "Cardiologie")

    parent.setCheckState(0, Qt.CheckState.Unchecked)



    child1 = CurriculumTreeWidgetItem(parent)

    child1.setText(0, "Item 224 - HTA")

    child1.item_tag = "EDN::item-224-HTA"

    child1.setCheckState(0, Qt.CheckState.Unchecked)



    child2 = CurriculumTreeWidgetItem(parent)

    child2.setText(0, "Item 203 - Dyspnée")

    child2.item_tag = "EDN::item-203-Dyspnee"

    child2.setCheckState(0, Qt.CheckState.Unchecked)



    dialog.specialty_items["Cardiologie"] = parent



    # Restauration simulée

    target_tags = set(pre_settings["selected_items"]["Cardiologie"])

    checked_count = 0

    for i in range(parent.childCount()):

        c = parent.child(i)

        if c.item_tag in target_tags:

            c.setCheckState(0, Qt.CheckState.Checked)

            checked_count += 1

    if checked_count > 0:

        parent.setCheckState(0, Qt.CheckState.PartiallyChecked)



    assert child1.checkState(0) == Qt.CheckState.Checked

    assert child2.checkState(0) == Qt.CheckState.Unchecked

    assert parent.checkState(0) == Qt.CheckState.PartiallyChecked



    # Test collecte des réglages

    collected = dialog.collect_current_settings()

    assert collected["threshold"] == 35

    assert collected["scope"] == "item_complet"

    assert collected["card_filter"] == "new_only"

    assert collected["rank_filter"] == "A"

    assert "Cardiologie" in collected["selected_specs"]

    assert "EDN::item-224-HTA" in collected["selected_items"]["Cardiologie"]



    # Test déclenchement on_rebuild_clicked sans paquets filtrés

    from unittest.mock import patch

    with patch("Anki_EDN_Installer.filtered_decks_dialog.showInfo") as mock_info:

        with patch("Anki_EDN_Installer.filtered_decks_dialog.get_edn_filtered_deck_ids", return_value=[]):

            dialog.on_rebuild_clicked()

            mock_info.assert_called_once()



    # Test déclenchement on_rebuild_clicked avec paquets filtrés existants

    with patch("Anki_EDN_Installer.filtered_decks_dialog.get_edn_filtered_deck_ids", return_value=[12345]):

        with patch("Anki_EDN_Installer.filtered_decks_dialog.rebuild_all_edn_filtered_decks", return_value={"count": 1, "total_cards": 5}) as mock_rebuild:

            with patch("Anki_EDN_Installer.filtered_decks_dialog.tooltip") as mock_tooltip:

                dialog.on_rebuild_clicked()

                mock_rebuild.assert_called_once()

                mock_tooltip.assert_called_once()



    dialog.deleteLater()

    save_filtered_decks_settings(DEFAULT_FILTERED_DECKS_SETTINGS)











def test_rebuild_filtered_decks_with_progress_callback(temp_anki_collection):

    """Vérifie la régénération avec remontée de progression."""

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # 1. Génération

    generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options={"rebuild": True, "card_filter": "all"},

        col=col

    )



    # 2. Vidage

    empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert len(col.find_cards('deck:"Anki EDN"')) == 15



    # 3. Régénération avec callback

    progress_records = []



    def on_progress(current, total, did):

        progress_records.append((current, total, did))



    res = rebuild_all_edn_filtered_decks(ROOT_DECK_NAME, col=col, progress_callback=on_progress)

    assert res["count"] == 2

    assert res["total_cards"] == 9

    assert len(progress_records) == 2

    assert progress_records[0][0] == 1

    assert progress_records[1][0] == 2



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_auto_sync_setting_disables_hooks(temp_anki_collection):

    """Vérifie que désactiver 'auto_sync' dans les réglages désactive le vidage automatique."""

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options={"rebuild": True, "card_filter": "all"},

        col=col

    )



    # Vérifier que les 9 cartes ont un odid actif (résident dans des paquets filtrés)

    filtered_cards_count = len([cid for cid in col.find_cards("") if col.get_card(cid).odid != 0])

    assert filtered_cards_count == 9



    # 1. Si auto_sync est False, on_sync_will_start ne vide PAS

    save_filtered_decks_settings({"auto_sync": False})

    on_sync_will_start(col=col)

    filtered_cards_after_sync = len([cid for cid in col.find_cards("") if col.get_card(cid).odid != 0])

    assert filtered_cards_after_sync == 9



    # 2. Si auto_sync est True, on_sync_will_start vide les paquets

    save_filtered_decks_settings({"auto_sync": True})

    on_sync_will_start(col=col)

    filtered_cards_after_sync_true = len([cid for cid in col.find_cards("") if col.get_card(cid).odid != 0])

    assert filtered_cards_after_sync_true == 0



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    save_filtered_decks_settings(DEFAULT_FILTERED_DECKS_SETTINGS)





def test_sync_does_not_rebuild_when_subdecks_were_emptied(temp_anki_collection):

    """

    Regle le bug : si l'utilisateur vide ses sous-paquets puis se synchronise,

    les sous-paquets NE doivent PAS etre reconstruits.

    """

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # 1. Generation des sous-paquets (Cardiologie : Item 203 + Item 224)

    generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options={"rebuild": True, "card_filter": "all"},

        col=col

    )



    # Verifier que les sous-paquets contiennent bien des cartes

    initial_filtered = [cid for cid in col.find_cards("") if col.get_card(cid).odid != 0]

    assert len(initial_filtered) == 9



    # 2. L'utilisateur vide les sous-paquets

    empty_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)

    assert len([cid for cid in col.find_cards("") if col.get_card(cid).odid != 0]) == 0

    assert len(get_active_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)) == 0



    # 3. L'utilisateur lance une synchronisation (sync_will_start puis sync_did_finish)

    on_sync_will_start(col=col)

    on_sync_did_finish(col=col)



    # 4. Verification formelle : AUCUN sous-paquet n'a ete reconstruit

    cards_after_sync = [cid for cid in col.find_cards("") if col.get_card(cid).odid != 0]

    assert len(cards_after_sync) == 0



    # Les sous-paquets existent toujours mais restent entierement vides (0 carte)

    for did in get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col):

        assert col.decks.card_count(did, False) == 0



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)





def test_sync_rebuilds_only_active_subdecks_and_preserves_emptied_ones(temp_anki_collection):
    save_filtered_decks_settings({"auto_sync": True})


    """

    Verifie que la synchronisation ne reconstruit que les sous-paquets qui contenaient

    effectivement des cartes, et laisse intacts (vides) ceux que l'utilisateur a vides.

    """

    col = temp_anki_collection

    curriculum = analyze_edn_curriculum(col=col, threshold_pct=40.0)



    # Generation des paquets (Cardiologie : Item 224 et Item 203)

    generate_filtered_hierarchy(

        selected_specialties=["Cardiologie"],

        curriculum_data=curriculum,

        options={"rebuild": True, "card_filter": "all"},

        col=col

    )



    dids = get_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    assert len(dids) == 2



    # L'utilisateur vide specifiquement le premier sous-paquet

    did_to_empty = dids[0]

    did_to_keep = dids[1]



    col.sched.empty_filtered_deck(did_to_empty)

    assert col.decks.card_count(did_to_empty, False) == 0

    assert col.decks.card_count(did_to_keep, False) > 0



    active_before_sync = get_active_edn_filtered_deck_ids(ROOT_DECK_NAME, col=col)

    assert active_before_sync == [did_to_keep]



    # Synchronisation

    on_sync_will_start(col=col)

    # Pendant la synchro, meme did_to_keep est temporairement vide pour securite

    assert col.decks.card_count(did_to_keep, False) == 0



    on_sync_did_finish(col=col)



    # Apres synchro : seul did_to_keep a ete restaure ! did_to_empty reste vide !

    assert col.decks.card_count(did_to_keep, False) > 0

    assert col.decks.card_count(did_to_empty, False) == 0



    delete_all_edn_filtered_decks(ROOT_DECK_NAME, col=col)









