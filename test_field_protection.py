# -*- coding: utf-8 -*-
"""
Tests unitaires pour la protection des champs modifiés et le guide d'installation EDN.
Vérifie la stricte exclusion du champ 'Erreurs faites', le formatage des tags,
l'absence d'emojis, et le comportement 'désactivé nativement'.
"""
import re
import pytest

from Anki_EDN_Installer.field_protection import (
    is_excluded_field,
    protect_tag,
    is_protect_tag,
    protected_names,
    field_hashes,
    fingerprint,
    edits_to_protect,
    save_baseline,
    load_baseline,
    PROTECT_PREFIX,
)
from Anki_EDN_Installer.guide import get_guide_html, GUIDE_VERSION


def test_is_excluded_field():
    """Vérifie l'exclusion de toutes les variantes du champ 'Erreurs faites'."""
    assert is_excluded_field("Erreurs faites") is True
    assert is_excluded_field("erreurs faites") is True
    assert is_excluded_field("Erreur faites") is True
    assert is_excluded_field("erreur faites") is True
    assert is_excluded_field("  ERREURS FAITES  ") is True
    assert is_excluded_field("  erreur faites  ") is True

    # Les autres champs doivent être inclus
    assert is_excluded_field("Recto") is False
    assert is_excluded_field("Verso") is False
    assert is_excluded_field("Infos supplémentaires") is False
    assert is_excluded_field("Commentaires") is False
    assert is_excluded_field("") is False
    assert is_excluded_field(None) is False


def test_protect_tag_and_helpers():
    """Vérifie le formatage des tags AnkiCollab_Protect."""
    assert protect_tag("Recto") == "AnkiCollab_Protect::Recto"
    assert protect_tag("Infos supplémentaires") == "AnkiCollab_Protect::Infos_supplémentaires"

    assert is_protect_tag("AnkiCollab_Protect::Recto") is True
    assert is_protect_tag("ankicollab_protect::verso") is True
    assert is_protect_tag("EDN::item-224") is False

    tags = ["AnkiCollab_Protect::Recto", "EDN::item-224", "AnkiCollab_Protect::Infos_supplémentaires"]
    names = protected_names(tags)
    assert names == {"recto", "infos_supplémentaires"}


def test_edits_to_protect_excludes_erreurs_faites():
    """
    Règle clé : le champ 'Erreurs faites' est personnel et ne doit JAMAIS recevoir
    de tag AnkiCollab_Protect, même s'il est modifié par l'utilisateur.
    """
    mid = 1
    field_names = {mid: ["Recto", "Verso", "Infos supplémentaires", "Erreurs faites"]}

    # Baseline initiale
    base_flds = "Question 1\x1fRéponse 1\x1fExtra 1\x1fErreur perso 1"
    rows_initial = [(1001, mid, base_flds, "EDN::item-101")]
    baseline = fingerprint(rows_initial)

    # Scénario 1 : L'utilisateur modifie Recto ET Erreurs faites
    edited_flds = "Question 1 MODIFIEE\x1fRéponse 1\x1fExtra 1\x1fErreur perso 1 MODIFIEE"
    rows_edited = [(1001, mid, edited_flds, "EDN::item-101")]

    adds = edits_to_protect(baseline, rows_edited, field_names)
    assert 1001 in adds
    # Recto doit être protégé
    assert "AnkiCollab_Protect::Recto" in adds[1001]
    # Erreurs faites NE DOIT PAS être protégé
    assert "AnkiCollab_Protect::Erreurs_faites" not in adds[1001]
    assert "AnkiCollab_Protect::Erreurs_Faites" not in adds[1001]
    assert len(adds[1001]) == 1


def test_edits_to_protect_only_erreurs_faites_modified():
    """Si l'utilisateur ne modifie QUE 'Erreurs faites', aucune protection n'est requise."""
    mid = 1
    field_names = {mid: ["Recto", "Verso", "Infos supplémentaires", "Erreurs faites"]}

    base_flds = "Question 1\x1fRéponse 1\x1fExtra 1\x1fErreur perso 1"
    rows_initial = [(1001, mid, base_flds, "EDN::item-101")]
    baseline = fingerprint(rows_initial)

    # Seul le champ 'Erreurs faites' est altéré
    edited_flds = "Question 1\x1fRéponse 1\x1fExtra 1\x1fMes erreurs personnelles du jour"
    rows_edited = [(1001, mid, edited_flds, "EDN::item-101")]

    adds = edits_to_protect(baseline, rows_edited, field_names)
    assert adds == {}


def test_edits_to_protect_multiple_fields():
    """Vérifie la protection simultanée de plusieurs champs autorisés."""
    mid = 1
    field_names = {mid: ["Recto", "Verso", "Infos supplémentaires", "Erreurs faites"]}

    base_flds = "Q\x1fR\x1fE\x1fErr"
    rows_initial = [(1001, mid, base_flds, "EDN::item-101")]
    baseline = fingerprint(rows_initial)

    edited_flds = "Q modifiée\x1fR modifiée\x1fE modifiée\x1fErr modifiée"
    rows_edited = [(1001, mid, edited_flds, "EDN::item-101")]

    adds = edits_to_protect(baseline, rows_edited, field_names)
    assert 1001 in adds
    assert set(adds[1001]) == {
        "AnkiCollab_Protect::Recto",
        "AnkiCollab_Protect::Verso",
        "AnkiCollab_Protect::Infos_supplémentaires"
    }


def test_edits_to_protect_respects_all_and_existing_tags():
    """Vérifie le respect du tag 'All' et des tags déjà posés sur la note."""
    mid = 1
    field_names = {mid: ["Recto", "Verso", "Erreurs faites"]}

    base_flds = "Q\x1fR\x1fErr"
    baseline = fingerprint([(1001, mid, base_flds, "")])

    # Note avec AnkiCollab_Protect::All
    rows_all = [(1001, mid, "Q2\x1fR2\x1fErr", "AnkiCollab_Protect::All")]
    adds = edits_to_protect(baseline, rows_all, field_names)
    assert adds == {}

    # Note ayant déjà AnkiCollab_Protect::Recto
    rows_existing = [(1001, mid, "Q2\x1fR2\x1fErr", "AnkiCollab_Protect::Recto")]
    adds_existing = edits_to_protect(baseline, rows_existing, field_names)
    assert adds_existing == {1001: ["AnkiCollab_Protect::Verso"]}


def test_baseline_save_and_load(tmp_path, monkeypatch):
    """Vérifie la persistance et le rechargement de l'empreinte JSON."""
    monkeypatch.setattr(
        "Anki_EDN_Installer.field_protection.get_baselines_dir",
        lambda: str(tmp_path)
    )

    data = {"1001": ["abc123456789", "def123456789"]}
    save_baseline("test_deck_hash", data)

    loaded = load_baseline("test_deck_hash")
    assert loaded == data


def test_guide_html_structure_and_no_emojis():
    """
    Vérifie le contenu textuel du guide Anki EDN et contrôle strictement l'absence d'emojis
    conformément aux directives globales de conception.
    """
    html_dark = get_guide_html(dark=True, updated=False)
    html_light = get_guide_html(dark=False, updated=True)

    # 1. Vérification des éléments indispensables tirés du site tuto Anki EDN
    assert "mango-may-georgia-eleven-moon-orange" in html_dark
    assert "AnkiCollab" in html_dark
    assert "FSRS" in html_dark
    assert "Léo Picat" in html_dark
    assert "Réparer les NID" in html_dark
    assert "Erreurs faites" in html_dark
    assert "Envoyer vers AnkiWeb" in html_dark
    assert "Télécharger depuis AnkiWeb" in html_dark

    # 2. Règle absolue : STRICTEMENT AUCUN EMOJI
    emoji_pattern = re.compile(
        r"[\U00010000-\U0010ffff]|[\u2600-\u26ff]|[\u2700-\u27bf]|[\u2300-\u23ff]"
    )
    assert not emoji_pattern.search(html_dark), "Le HTML du guide en mode sombre contient des emojis !"
    assert not emoji_pattern.search(html_light), "Le HTML du guide en mode clair contient des emojis !"


def test_is_edn_or_collab_note():
    from Anki_EDN_Installer.field_protection import is_edn_or_collab_note

    class FakeNote:
        def __init__(self, tags, model_name="Basique"):
            self.tags = tags
            self._model_name = model_name
        def note_type(self):
            return {"name": self._model_name, "flds": [{"name": "Recto"}]}

    assert is_edn_or_collab_note(FakeNote(["EDN::Cardio"])) is True
    assert is_edn_or_collab_note(FakeNote(["AnkiCollab::Sub"])) is True
    assert is_edn_or_collab_note(FakeNote([], model_name="Basique-EDN-Picat-8b691")) is True
    assert is_edn_or_collab_note(FakeNote([], model_name="Syndrome-EDN-Picat-a47eb")) is True
    assert is_edn_or_collab_note(FakeNote([], model_name="Anglais")) is False
    assert is_edn_or_collab_note(None) is False


def test_editor_did_unfocus_field_auto_protect(monkeypatch):
    from Anki_EDN_Installer.field_protection import _on_editor_did_unfocus_field
    import Anki_EDN_Installer.shared_menu as sm

    class FakeEditorNote:
        def __init__(self):
            self.id = 12345
            self.tags = []
        def note_type(self):
            return {
                "name": "Basique-EDN-Picat",
                "flds": [
                    {"name": "Recto"},
                    {"name": "Verso"},
                    {"name": "Erreurs faites"}
                ]
            }
        def add_tag(self, tag):
            if tag not in self.tags:
                self.tags.append(tag)

    class FakeEditor:
        def __init__(self, note):
            self.note = note
            self.tags_loaded = False
        def load_tags(self):
            self.tags_loaded = True

    # Case 1: Protection enabled -> field 0 (Recto) gets protected
    monkeypatch.setattr(sm, "is_protect_user_edits_enabled", lambda: True)
    note = FakeEditorNote()
    editor = FakeEditor(note)
    res = _on_editor_did_unfocus_field(True, editor, 0)
    assert res is True
    assert "AnkiCollab_Protect::Recto" in note.tags
    assert editor.tags_loaded is True

    # Case 2: Field 2 (Erreurs faites) -> strictly excluded
    res_err = _on_editor_did_unfocus_field(True, editor, 2)
    assert res_err is True
    assert "AnkiCollab_Protect::Erreurs_faites" not in note.tags

    # Case 3: Protection disabled -> no tags added
    monkeypatch.setattr(sm, "is_protect_user_edits_enabled", lambda: False)
    note2 = FakeEditorNote()
    editor2 = FakeEditor(note2)
    res_off = _on_editor_did_unfocus_field(True, editor2, 1)
    assert res_off is True
    assert note2.tags == []
