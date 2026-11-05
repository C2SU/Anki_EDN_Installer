# -*- coding: utf-8 -*-
"""
Anki EDN Symbols & Abbreviations Importer
Automatically imports medical shortcuts from raccourcis.csv into the
'Insert Symbols As You Type' addon database (table 'ins_symbols' in mw.col.db).
- Uses SHA-256 content hashing to reliably detect repository updates.
- Uses conservative merge (upsert) to strictly preserve user-created personal shortcuts.
"""
from __future__ import annotations

import os
import csv
import sys
import hashlib
from typing import Tuple, List, Optional, Set

from aqt import mw, gui_hooks
from aqt.utils import tooltip, showInfo

try:
    from .logger import log
    from .shared_menu import get_config, save_config
except (ImportError, ValueError):
    try:
        from Anki_EDN_Installer.logger import log
        from Anki_EDN_Installer.shared_menu import get_config, save_config
    except (ImportError, ValueError):
        from logger import log
        from shared_menu import get_config, save_config

SYMBOLS_ADDON_ID = "2040501954"


def get_raccourcis_csv_path() -> str:
    """Return the absolute path to the bundled raccourcis.csv file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "user_files", "raccourcis.csv"),
        os.path.join(base_dir, "raccourcis.csv"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[0]


def get_raccourcis_csv_hash() -> str:
    """Compute SHA-256 hash of raccourcis.csv to detect repository updates reliably across checkouts."""
    csv_path = get_raccourcis_csv_path()
    if not os.path.isfile(csv_path):
        return ""
    try:
        with open(csv_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def is_symbols_addon_installed() -> bool:
    """Check whether the 'Insert Symbols As You Type' addon is present."""
    if mw and hasattr(mw, "addonManager") and mw.addonManager:
        try:
            installed = mw.addonManager.allAddons()
            if SYMBOLS_ADDON_ID in installed:
                return True
        except Exception:
            pass
    # Check filesystem in addons21
    try:
        addons_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target = os.path.join(addons_dir, SYMBOLS_ADDON_ID)
        if os.path.isdir(target):
            return True
    except Exception:
        pass
    return False


def load_edn_symbols_from_csv() -> List[Tuple[str, str]]:
    """Parse key-value pairs from raccourcis.csv."""
    csv_path = get_raccourcis_csv_path()
    if not os.path.isfile(csv_path):
        log(f"[symbols_importer] Fichier introuvable: {csv_path}")
        return []

    symbols: List[Tuple[str, str]] = []
    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1]:
                    symbols.append((row[0].strip(), row[1]))
    except Exception as e:
        log(f"[symbols_importer] Erreur lecture CSV: {e}")
    return symbols


def import_edn_symbols(force: bool = False) -> Tuple[bool, str, int]:
    """
    Import/merge EDN symbols into mw.col.db (table ins_symbols).
    Guarantees that user personal custom shortcuts are preserved without any deletion.
    """
    if not mw or not mw.col or not hasattr(mw.col, "db") or not mw.col.db:
        return False, "La collection Anki n'est pas ouverte.", 0

    csv_path = get_raccourcis_csv_path()
    if not os.path.isfile(csv_path):
        return False, f"Fichier raccourcis.csv introuvable ({csv_path}).", 0

    current_hash = get_raccourcis_csv_hash()
    cfg = get_config()
    last_hash = cfg.get("edn_symbols_imported_hash", "")

    # Check if up to date with repository hash
    if not force and last_hash and last_hash == current_hash:
        return True, "Les symboles EDN sont deja a jour avec le depot.", 0

    symbols = load_edn_symbols_from_csv()
    if not symbols:
        return False, "Aucun symbole valide trouve dans le fichier raccourcis.csv.", 0

    try:
        db = mw.col.db
        # Ensure ins_symbols table exists
        db.execute(
            "CREATE TABLE IF NOT EXISTS ins_symbols (key varchar(255), value varchar(255))"
        )

        # Retrieve existing keys and values
        existing_rows = db.all("SELECT key, value FROM ins_symbols")
        existing_dict = {r[0]: r[1] for r in existing_rows}

        inserted_count = 0
        updated_count = 0

        # Upsert official symbols while preserving all custom user keys
        for key, val in symbols:
            if key not in existing_dict:
                db.execute("INSERT INTO ins_symbols VALUES (?, ?)", key, val)
                existing_dict[key] = val
                inserted_count += 1
            elif existing_dict[key] != val:
                db.execute("UPDATE ins_symbols SET value = ? WHERE key = ?", val, key)
                existing_dict[key] = val
                updated_count += 1

        total_changed = inserted_count + updated_count

        # Notify active SymbolManager instance if addon 2040501954 is running
        _notify_active_symbol_manager()

        cfg["edn_symbols_imported_hash"] = current_hash
        cfg["edn_official_symbol_keys"] = [k for k, v in symbols]
        save_config(cfg)

        user_custom_count = len(existing_dict) - len(symbols)
        if user_custom_count < 0:
            user_custom_count = 0

        msg = (
            f"Importation terminee : {inserted_count} symbole(s) ajoutes, "
            f"{updated_count} mis a jour ({len(symbols)} symboles EDN au total). "
            f"{user_custom_count} raccourci(s) personnalise(s) conserve(s)."
        )
        log(f"[symbols_importer] {msg}")
        return True, msg, total_changed

    except Exception as e:
        err_msg = f"Erreur lors de l'importation des symboles dans la base Anki: {e}"
        log(f"[symbols_importer] {err_msg}")
        return False, err_msg, 0


def _notify_active_symbol_manager() -> None:
    """Inform 2040501954 to refresh its internal cache and reload open editors."""
    try:
        mod_name = f"{SYMBOLS_ADDON_ID}.insert_symbols"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
            mgr = getattr(mod, "ins_sym_manager", None)
            if mgr:
                mgr.on_profile_loaded()
                update_fn = getattr(mod, "update_symbols", None)
                if callable(update_fn):
                    update_fn()
                log("[symbols_importer] Notification transmise avec succes a Insert Symbols As You Type.")
    except Exception as e:
        log(f"[symbols_importer] Erreur notification ins_sym_manager: {e}")


def auto_import_on_profile_open() -> None:
    """Silent check and import on startup if repository file was updated."""
    try:
        if is_symbols_addon_installed():
            # Will automatically detect if hash changed or never imported
            import_edn_symbols(force=False)
    except Exception as e:
        log(f"[symbols_importer] Erreur auto-import au demarrage: {e}")


def init_symbols_importer_hooks() -> None:
    """Initialize profile hook for automatic symbols synchronization."""
    gui_hooks.profile_did_open.append(auto_import_on_profile_open)
    log("[symbols_importer] Module d'import automatique des symboles initialise.")
