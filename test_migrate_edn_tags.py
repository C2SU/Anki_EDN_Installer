"""
Tests unitaires pour le script de migration locale des tags EDN.
"""

import os
import tempfile
import sqlite3
import pytest

from Anki_EDN_Installer.migrate_edn_tags import (
    transform_single_tag,
    migrate_tags_sqlite
)


def test_transform_single_tag():
    # Par défaut (migrate_items=False, migrate_sdds=True)
    # Items NON migrés par défaut
    assert transform_single_tag("EDN::item-001") is None
    assert transform_single_tag("EDN::item-001-Relation") is None
    assert transform_single_tag("edn::item-224-HTA") is None

    # SDD & SSDD migrés en EDN::SDD:: et EDN::SSDD::
    assert transform_single_tag("EDN::sdd-002-Diarrhee") == "EDN::SDD::002-Diarrhee"
    assert transform_single_tag("EDN::SDD-002-Diarrhee::arbre") == "EDN::SDD::002-Diarrhee::arbre"
    assert transform_single_tag("EDN::ssdd-005-Masse") == "EDN::SSDD::005-Masse"
    assert transform_single_tag("edn::sdd-010-Fievre") == "EDN::SDD::010-Fievre"

    # Si migrate_items=True explicitement
    assert transform_single_tag("EDN::item-001", migrate_items=True) == "EDN::item::001"
    assert transform_single_tag("EDN::item-001-Relation", migrate_items=True) == "EDN::item::001-Relation"
    assert transform_single_tag("edn::item-224-HTA", migrate_items=True) == "EDN::item::224-HTA"

    # Déjà migré ou non concerné
    assert transform_single_tag("EDN::item::001") is None
    assert transform_single_tag("EDN::SDD::002-Diarrhee") is None
    assert transform_single_tag("EDN::sdd::002-Diarrhee") is None
    assert transform_single_tag("Cardiologie") is None
    assert transform_single_tag("rang::rang_a") is None
    assert transform_single_tag("source::college") is None


def test_migrate_tags_sqlite_dry_run_and_apply(monkeypatch):
    # Mock is_anki_running to return False
    monkeypatch.setattr("Anki_EDN_Installer.migrate_edn_tags.is_anki_running", lambda: False)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "collection.anki2")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("CREATE TABLE notes (id integer primary key, tags text, mod integer, usn integer)")
        cur.execute("CREATE TABLE tags (tag text primary key, usn integer)")

        # Insérer des données de test
        cur.execute("INSERT INTO notes VALUES (1, ' EDN::item-224-HTA Cardiologie rang::rang_a ', 1000, 0)")
        cur.execute("INSERT INTO notes VALUES (2, ' EDN::sdd-002-Diarrhee::arbre Urgent ', 1001, 0)")
        cur.execute("INSERT INTO notes VALUES (3, ' Pneumologie EDN::item::100-Migre ', 1002, 0)")
        cur.execute("INSERT INTO tags VALUES ('EDN::item-224-HTA', 0)")
        cur.execute("INSERT INTO tags VALUES ('EDN::sdd-002-Diarrhee::arbre', 0)")
        conn.commit()
        conn.close()

        # 1. Test Dry Run SDD uniquement (comportement par défaut)
        res_dry = migrate_tags_sqlite(db_path, apply_changes=False, migrate_items=False, migrate_sdds=True)
        assert res_dry["dry_run"] is True
        assert res_dry["notes_modified"] == 1
        assert res_dry["total_scanned_notes"] == 1

        # Vérifier que la base est inchangée
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT tags FROM notes WHERE id = 1")
        assert cur.fetchone()[0] == " EDN::item-224-HTA Cardiologie rang::rang_a "
        conn.close()

        # 2. Test Apply SDD uniquement
        res_apply = migrate_tags_sqlite(db_path, apply_changes=True, migrate_items=False, migrate_sdds=True)
        assert res_apply["dry_run"] is False
        assert res_apply["notes_modified"] == 1
        assert os.path.exists(res_apply["backup_path"])

        # Vérifier que la note 1 (item-224) n'a PAS été modifiée
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT tags, usn FROM notes WHERE id = 1")
        tags1, usn1 = cur.fetchone()
        assert "EDN::item-224-HTA" in tags1
        assert "EDN::item::" not in tags1
        assert usn1 == 0

        # Vérifier que la note 2 (sdd-002) a été migrée vers EDN::SDD::002-Diarrhee::arbre
        cur.execute("SELECT tags, usn FROM notes WHERE id = 2")
        tags2, usn2 = cur.fetchone()
        assert "EDN::SDD::002-Diarrhee::arbre" in tags2
        assert "EDN::sdd-002-Diarrhee::arbre" not in tags2
        assert "Urgent" in tags2
        assert usn2 == -1

        conn.close()
