#!/usr/bin/env python3
"""
Script de migration locale des tags EDN pour la collection Anki.
Transforme la nomenclature des tags :
  - 'EDN::sdd-xxx'  -> 'EDN::sdd::xxx'
  - 'EDN::ssdd-xxx' -> 'EDN::ssdd::xxx'
  - 'EDN::item-xxx' -> 'EDN::item::xxx'

Sécurité :
  - Vérification de l'arrêt du processus Anki (si accès SQLite direct).
  - Sauvegarde préalable automatique de la base de données.
  - Mode simulation (--dry-run) actif par défaut.
  - Fonction exportable 'migrate_tags_in_anki()' pour exécution directe dans la console Anki (Ctrl+Shift+;).
"""

import os
import sys
import re
import shutil
import sqlite3
import argparse
import datetime
from typing import Dict, List, Tuple, Set, Optional


ANKI_DEFAULT_BASE = os.path.expandvars(r"%APPDATA%\Anki2")

RE_EDN_SDD = re.compile(r"^(edn)::(s{1,2}dd)-(.*)$", re.IGNORECASE)
RE_EDN_ITEM = re.compile(r"^(edn)::(item)-(.*)$", re.IGNORECASE)


def transform_single_tag(tag: str, migrate_items: bool = False, migrate_sdds: bool = True) -> Optional[str]:
    """
    Transforme un tag s'il correspond à la nomenclature EDN ciblée.
    Par défaut :
      - migrate_sdds=True  : EDN::sdd-xxx -> EDN::SDD::xxx et EDN::ssdd-xxx -> EDN::SSDD::xxx
      - migrate_items=False : EDN::item-xxx reste inchangé.
    Retourne le nouveau tag ou None si inchangé.
    """
    if migrate_items:
        m_item = RE_EDN_ITEM.match(tag)
        if m_item:
            edn_part = m_item.group(1).upper()
            item_part = m_item.group(2)
            rest = m_item.group(3)
            return f"{edn_part}::{item_part}::{rest}"

    if migrate_sdds:
        m_sdd = RE_EDN_SDD.match(tag)
        if m_sdd:
            edn_part = m_sdd.group(1).upper()
            sdd_part = m_sdd.group(2).upper()
            rest = m_sdd.group(3)
            return f"{edn_part}::{sdd_part}::{rest}"

    return None


def is_anki_running() -> bool:
    """Vérifie si le processus Anki est actuellement en cours d'exécution sous Windows."""
    if sys.platform != "win32":
        return False
    try:
        import subprocess
        output = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq anki.exe", "/NH"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        return "anki.exe" in output.lower()
    except Exception:
        return False


def find_default_collection(profile_name: Optional[str] = None) -> Optional[str]:
    """Localise le fichier collection.anki2 dans le dossier Anki2."""
    if not os.path.exists(ANKI_DEFAULT_BASE):
        return None

    if profile_name:
        candidate = os.path.join(ANKI_DEFAULT_BASE, profile_name, "collection.anki2")
        if os.path.isfile(candidate):
            return candidate
        return None

    # Recherche automatique : ignorer addons21, crash dumps, etc.
    candidates = []
    for entry in os.listdir(ANKI_DEFAULT_BASE):
        full_dir = os.path.join(ANKI_DEFAULT_BASE, entry)
        if os.path.isdir(full_dir) and entry not in ("addons21", "logs", "crash_dumps"):
            col_file = os.path.join(full_dir, "collection.anki2")
            if os.path.isfile(col_file):
                size = os.path.getsize(col_file)
                candidates.append((size, col_file, entry))

    if not candidates:
        return None

    # Retourne le profil principal (celui qui a la base la plus volumineuse)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def migrate_tags_in_anki(col=None, dry_run: bool = False, migrate_items: bool = False, migrate_sdds: bool = True) -> Dict[str, any]:
    """
    Exécute la migration directement dans une session Anki ouverte
    (ex: depuis la console Debug d'Anki ou un hook interne d'addon).
    """
    if col is None:
        try:
            from aqt import mw
            if mw and mw.col:
                col = mw.col
            else:
                raise RuntimeError("mw.col n'est pas disponible.")
        except Exception as e:
            raise RuntimeError(f"Impossible d'accéder à la collection Anki en mémoire: {e}")

    notes_modified = 0
    tags_count_map = {}

    queries = []
    if migrate_sdds:
        queries.extend(["tag:EDN::sdd-*", "tag:EDN::SDD-*", "tag:EDN::ssdd-*", "tag:EDN::SSDD-*"])
    if migrate_items:
        queries.extend(["tag:EDN::item-*", "tag:EDN::ITEM-*"])

    if not queries:
        return {"success": True, "notes_modified": 0, "total_candidate_notes": 0, "tags_count_map": {}, "dry_run": dry_run}

    all_nids = col.find_notes(" or ".join(queries))
    
    for nid in all_nids:
        note = col.get_note(nid)
        new_tags = []
        modified = False

        for tag in note.tags:
            new_tag = transform_single_tag(tag, migrate_items=migrate_items, migrate_sdds=migrate_sdds)
            if new_tag and new_tag != tag:
                modified = True
                new_tags.append(new_tag)
                key = f"{tag} -> {new_tag}"
                tags_count_map[key] = tags_count_map.get(key, 0) + 1
            else:
                new_tags.append(tag)

        if modified:
            notes_modified += 1
            if not dry_run:
                # Éliminer d'éventuels doublons
                deduped_tags = []
                seen = set()
                for t in new_tags:
                    if t not in seen:
                        seen.add(t)
                        deduped_tags.append(t)
                note.tags = deduped_tags
                col.update_note(note)

    if not dry_run and hasattr(col, "tags") and hasattr(col.tags, "clear_unused_tags"):
        col.tags.clear_unused_tags()

    return {
        "success": True,
        "notes_modified": notes_modified,
        "total_candidate_notes": len(all_nids),
        "tags_count_map": tags_count_map,
        "dry_run": dry_run
    }


def migrate_tags_sqlite(db_path: str, apply_changes: bool = False, migrate_items: bool = False, migrate_sdds: bool = True) -> Dict[str, any]:
    """
    Exécute la migration directement sur le fichier SQLite collection.anki2
    (quand Anki est fermé).
    """
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Fichier introuvable: {db_path}")

    if is_anki_running():
        raise RuntimeError(
            "Anki est actuellement en cours d'exécution !\n"
            "Veuillez fermer Anki avant d'appliquer les modifications sur la base SQLite."
        )

    # Sauvegarde automatique si application demandée
    backup_path = None
    if apply_changes:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.backup_tag_migration_{timestamp}"
        shutil.copy2(db_path, backup_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    conditions = []
    if migrate_sdds:
        conditions.extend(["tags LIKE '%sdd-%'", "tags LIKE '%ssdd-%'", "tags LIKE '%SDD-%'", "tags LIKE '%SSDD-%'"])
    if migrate_items:
        conditions.extend(["tags LIKE '%item-%'", "tags LIKE '%ITEM-%'"])

    if not conditions:
        conn.close()
        return {"success": True, "notes_modified": 0, "total_candidate_notes": 0, "tags_count_map": {}, "dry_run": not apply_changes, "backup_path": backup_path}

    where_clause = " OR ".join(conditions)
    cur.execute(f"SELECT id, tags FROM notes WHERE {where_clause}")
    rows = cur.fetchall()

    notes_modified = 0
    tags_count_map = {}
    updates = []

    for nid, tags_str in rows:
        if not tags_str:
            continue

        raw_tags = [t for t in tags_str.strip().split() if t]
        new_tags = []
        note_modified = False

        for tag in raw_tags:
            new_tag = transform_single_tag(tag)
            if new_tag and new_tag != tag:
                note_modified = True
                new_tags.append(new_tag)
                key = f"{tag} -> {new_tag}"
                tags_count_map[key] = tags_count_map.get(key, 0) + 1
            else:
                new_tags.append(tag)

        if note_modified:
            notes_modified += 1
            # Anki stocke les tags sous la forme ' tag1 tag2 ' (avec espaces de délimitation)
            # Élimination des doublons en préservant l'ordre
            deduped = []
            seen = set()
            for t in new_tags:
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            formatted_tags = f" {' '.join(deduped)} "
            updates.append((formatted_tags, nid))

    if apply_changes and updates:
        # Appliquer les mises à jour par lot
        cur.executemany("UPDATE notes SET tags = ?, usn = -1 WHERE id = ?", updates)
        
        # Mettre à jour la table des tags enregistrés
        for pair in tags_count_map.keys():
            old_t, new_t = pair.split(" -> ")
            cur.execute("INSERT OR IGNORE INTO tags (tag, usn) VALUES (?, -1)", (new_t,))

        conn.commit()

    conn.close()

    return {
        "success": True,
        "notes_modified": notes_modified,
        "total_scanned_notes": len(rows),
        "tags_count_map": tags_count_map,
        "backup_path": backup_path,
        "dry_run": not apply_changes
    }


def main():
    parser = argparse.ArgumentParser(
        description="Migration locale des tags Anki EDN (edn::sdd-xxx -> edn::sdd::xxx, edn::item-xxx -> edn::item::xxx)"
    )
    parser.add_argument(
        "--col-path",
        help="Chemin direct vers le fichier collection.anki2."
    )
    parser.add_argument(
        "--profile",
        help="Nom du profil Anki à migrer (ex: 'Utilisateur 1')."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Appliquer réellement les modifications (sans cette option, le script s'exécute en mode simulation)."
    )

    args = parser.parse_args()

    print("=" * 65)
    print("  MIGRATION LOCALE DES TAGS ANKI EDN")
    print("  edn::sdd-xxx -> edn::sdd::xxx  |  edn::item-xxx -> edn::item::xxx")
    print("=" * 65)

    col_path = args.col_path or find_default_collection(args.profile)

    if not col_path:
        print("\n[ERREUR] Impossible de localiser collection.anki2.")
        print("Veuillez spécifier le chemin avec l'option --col-path <chemin> ou --profile <nom>.")
        sys.exit(1)

    print(f"\nBase de données ciblée : {col_path}")
    mode_str = "APPLICATION REELLE" if args.apply else "SIMULATION (Dry-Run)"
    print(f"Mode d'exécution       : {mode_str}\n")

    if is_anki_running():
        print("[ATTENTION] L'application Anki est actuellement ouverte.")
        print("Pour modifier directement la base SQLite sans risque de conflit,")
        print("veuillez fermer Anki avant d'appliquer les modifications.")
        if args.apply:
            print("\nOpération interrompue pour protéger l'intégrité de la collection.")
            sys.exit(1)
        else:
            print("(La simulation peut continuer en lecture seule si la base n'est pas verrouillée)\n")

    try:
        results = migrate_tags_sqlite(col_path, apply_changes=args.apply)
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print(f"[VERROU] La base de données est verrouillée par Anki : {e}")
            print("Fermez complètement Anki puis relancez cette commande.")
            sys.exit(1)
        raise

    print(f"Notes analysées avec tags cibles : {results['total_scanned_notes']}")
    print(f"Notes à modifier                 : {results['notes_modified']}")
    print(f"Nombre de règles de renommage   : {len(results['tags_count_map'])}\n")

    if results["tags_count_map"]:
        print("Détail des transformations (top 20) :")
        sorted_pairs = sorted(results["tags_count_map"].items(), key=lambda x: x[1], reverse=True)
        for pair, count in sorted_pairs[:20]:
            print(f"  [{count:>4} notes] {pair}")
        if len(sorted_pairs) > 20:
            print(f"  ... et {len(sorted_pairs) - 20} autres tags transformés.")

    if results["dry_run"]:
        print("\n" + "-" * 65)
        print("MODE SIMULATION TERMINE - Aucune note n'a été modifiée.")
        print("Pour appliquer définitivement ces modifications :")
        print(f"  python migrate_edn_tags.py --apply")
        print("-" * 65)
    else:
        print("\n" + "=" * 65)
        print("MIGRATION APPLIQUEE AVEC SUCCES !")
        print(f"Sauvegarde de sécurité créée : {results['backup_path']}")
        print("Les tags ont été mis à jour dans la collection locale.")
        print("=" * 65)


if __name__ == "__main__":
    main()
