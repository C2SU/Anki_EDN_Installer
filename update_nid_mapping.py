"""Script d'actualisation automatique du fichier nid_mapping.txt.

Ce script synchronise le mapping des identifiants administratifs (guid -> admin_nid)
a partir de la collection Anki locale de reference (profils Anki2 contenant des
types de notes EDN-Picat).
Il met a jour les copies de nid_mapping.txt dans :
  - Anki_EDN_Installer/nid_mapping.txt
  - Anki_EDN_Installer/user_files/nid_mapping.txt
  - Anki_EDN_nid/nid_mapping.txt (si present)
"""

import os
import sys
import sqlite3
from typing import Dict, List, Optional, Tuple


def find_anki2_dir() -> str:
    """Trouve le repertoire de base d'Anki2."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        anki2 = os.path.join(appdata, "Anki2")
        if os.path.isdir(anki2):
            return anki2
    # Fallback chemin courant relatif
    cur = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(cur)
    if os.path.basename(parent) == "addons21":
        return os.path.dirname(parent)
    return r"C:\Users\Pipou\AppData\Roaming\Anki2"


def find_reference_collection(anki2_dir: str) -> Optional[str]:
    """Trouve la collection SQLite de reference contenant le plus de notes EDN."""
    best_col: Optional[str] = None
    max_edn_notes = -1

    candidates: List[str] = []
    # Verifier 'Utilisateur 1' en priorite
    u1 = os.path.join(anki2_dir, "Utilisateur 1", "collection.anki2")
    if os.path.isfile(u1):
        candidates.append(u1)

    # Verifier tous les sous-dossiers de profils
    try:
        for entry in os.listdir(anki2_dir):
            sub = os.path.join(anki2_dir, entry)
            if os.path.isdir(sub) and entry not in ("addons21", "debug_scripts", "logs", "edn_profiler_logs"):
                col = os.path.join(sub, "collection.anki2")
                if os.path.isfile(col) and col not in candidates:
                    candidates.append(col)
    except Exception:
        pass

    for col_path in candidates:
        try:
            norm_path = col_path.replace("\\", "/")
            uri = f"file:///{norm_path}?mode=ro"
            con = sqlite3.connect(uri, uri=True, timeout=5)
            cur = con.cursor()
            count = cur.execute(
                """
                SELECT count(*) FROM notes
                WHERE mid IN (SELECT id FROM notetypes WHERE name LIKE '%EDN-Picat%')
                """
            ).fetchone()[0]
            con.close()
            if count > max_edn_notes:
                max_edn_notes = count
                best_col = col_path
        except Exception:
            continue

    return best_col


def load_existing_mapping(mapping_path: str) -> Dict[str, int]:
    """Charge un fichier nid_mapping.txt existant."""
    mapping: Dict[str, int] = {}
    if not os.path.isfile(mapping_path):
        return mapping

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                guid, nid_str = line.rsplit(",", 1)
                try:
                    mapping[guid] = int(nid_str)
                except ValueError:
                    continue
    except Exception as e:
        print(f"[Avertissement] Erreur lecture {mapping_path}: {e}")

    return mapping


def update_nid_mapping(col_path: Optional[str] = None) -> Tuple[int, int, int, int]:
    """Met a jour nid_mapping.txt pour Installer et Anki_EDN_nid.

    Returns:
        (total_collection, new_added, updated, total_mapping)
    """
    anki2_dir = find_anki2_dir()
    if not col_path:
        col_path = find_reference_collection(anki2_dir)

    cur_dir = os.path.dirname(os.path.abspath(__file__))
    addons_dir = os.path.dirname(cur_dir)

    # Cibles a synchroniser
    installer_dir = cur_dir if os.path.basename(cur_dir) == "Anki_EDN_Installer" else os.path.join(addons_dir, "Anki_EDN_Installer")
    nid_addon_dir = os.path.join(addons_dir, "Anki_EDN_nid")

    targets = [
        os.path.join(installer_dir, "nid_mapping.txt"),
        os.path.join(installer_dir, "user_files", "nid_mapping.txt"),
    ]
    if os.path.isdir(nid_addon_dir):
        targets.append(os.path.join(nid_addon_dir, "nid_mapping.txt"))

    # Charger le mapping existant le plus complet
    mapping: Dict[str, int] = {}
    for t in targets:
        curr = load_existing_mapping(t)
        if len(curr) > len(mapping):
            mapping = curr

    initial_count = len(mapping)

    if not col_path or not os.path.isfile(col_path):
        print(f"[Avertissement] Aucune collection de reference accessible pour actualiser le mapping.")
        return 0, 0, 0, initial_count

    norm_path = col_path.replace("\\", "/")
    uri = f"file:///{norm_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    cur = con.cursor()
    edn_notes = cur.execute(
        """
        SELECT guid, id
        FROM notes
        WHERE mid IN (SELECT id FROM notetypes WHERE name LIKE '%EDN-Picat%')
        """
    ).fetchall()
    con.close()

    new_added = 0
    updated = 0
    for guid, nid in edn_notes:
        if guid not in mapping:
            mapping[guid] = nid
            new_added += 1
        elif mapping[guid] != nid:
            mapping[guid] = nid
            updated += 1

    sorted_mapping = sorted(mapping.items(), key=lambda item: item[1])
    lines = [f"{guid},{nid}\n" for guid, nid in sorted_mapping]

    for t in targets:
        try:
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with open(t, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(lines)
            print(f"Mapping actualise ({len(lines)} notes) -> {t}")
        except Exception as e:
            print(f"[Erreur] Ecriture echouee pour {t}: {e}")

    return len(edn_notes), new_added, updated, len(mapping)


if __name__ == "__main__":
    total_col, added, upd, total_map = update_nid_mapping()
    print("\n--- Bilan Actualisation Mapping ---")
    print(f"Notes EDN dans la collection : {total_col}")
    print(f"Nouvelles notes integrees    : {added}")
    print(f"Notes modifiees              : {upd}")
    print(f"Total notes dans le mapping  : {total_map}")
