"""
Anki EDN Installer - NID Repair & Identity Alignment
Integrates note identifier migration natively into EDN Installer.
Aligns local note IDs (NID) and card associations based on nid_mapping.txt.
Automatically hooks AnkiCollab to repair NIDs immediately after deck arrival.
"""
from __future__ import annotations

import codecs
import json
import os
import time
from typing import Optional, Tuple, Dict, Any

from aqt import mw, gui_hooks
from aqt.utils import showCritical, tooltip
from .logger import log


def get_nid_mapping_path() -> Optional[str]:
    """Return the absolute path to nid_mapping.txt or fallback json."""
    search_dirs = []
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs.append(cur_dir)
    search_dirs.append(os.path.join(cur_dir, "user_files"))

    if mw and hasattr(mw, "addonManager"):
        try:
            addon_dir = mw.addonManager.addonsFolder()
            search_dirs.append(os.path.join(addon_dir, "Anki_EDN_Installer"))
            search_dirs.append(os.path.join(addon_dir, "Anki_EDN_Installer", "user_files"))
            search_dirs.append(os.path.join(addon_dir, "Anki_EDN_nid"))
        except Exception:
            pass

    for d in search_dirs:
        for fname in ("nid_mapping.txt", "nids_list.json"):
            candidate = os.path.join(d, fname)
            if os.path.isfile(candidate):
                return candidate
    return None


def migrate_nids(
    col=None,
    auto: bool = False,
    silent: bool = False,
    trigger_sync: bool = True,
    mapping_file: Optional[str] = None,
) -> Tuple[int, str]:
    """
    Execute NID repair on the collection.
    Aligns note and card IDs with canonical admin IDs from nid_mapping.txt.
    """
    if col is None and mw:
        col = getattr(mw, "col", None)
    if not col:
        return 0, "Collection Anki non disponible."

    if mapping_file is None:
        mapping_file = get_nid_mapping_path()

    if not mapping_file or not os.path.exists(mapping_file):
        msg = "Fichier de correspondance des identifiants (nid_mapping.txt) introuvable."
        log(f"[NID] {msg}")
        if not silent and not auto and mw:
            try:
                showCritical(msg)
            except Exception:
                pass
        return 0, msg

    if not auto and mw and getattr(mw, "progress", None):
        try:
            mw.progress.start(immediate=True)
        except Exception:
            pass

    if mw and hasattr(mw, "checkpoint"):
        try:
            mw.checkpoint("Mise à jour NIDs")
        except Exception:
            pass

    updated = 0
    orig_fk = None

    try:
        lines = []
        if mapping_file.endswith(".json"):
            with open(mapping_file, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
                if isinstance(raw_json, dict):
                    lines = [f"{guid},{nid}" for guid, nid in raw_json.items()]
        else:
            with codecs.open(mapping_file, "r", "utf-8") as f:
                lines = f.readlines()

        local_notes = dict(col.db.all("SELECT guid, id FROM notes"))
        existing_ids = set(local_notes.values())
        now = int(time.time())

        planned_updates = []
        target_admin_nids = set()

        for line in lines:
            line = line.strip()
            if not line or "," not in line:
                continue

            guid, nid_str = line.rsplit(",", 1)
            try:
                admin_nid = int(nid_str)
            except ValueError:
                continue

            local_nid = local_notes.get(guid)
            if local_nid and local_nid != admin_nid:
                if admin_nid in existing_ids or admin_nid in target_admin_nids:
                    # Collision detected: skip to avoid duplicate primary keys
                    continue
                target_admin_nids.add(admin_nid)
                planned_updates.append((admin_nid, now, local_nid))

        if planned_updates:
            try:
                orig_fk = col.db.scalar("PRAGMA foreign_keys")
            except Exception:
                orig_fk = None

            col.db.execute("PRAGMA foreign_keys = OFF")

            col.db.executemany(
                "UPDATE notes SET id = ?, mod = ?, usn = -1 WHERE id = ?",
                planned_updates,
            )
            col.db.executemany(
                "UPDATE cards SET nid = ?, mod = ?, usn = -1 WHERE nid = ?",
                planned_updates,
            )
            updated = len(planned_updates)
            if hasattr(col, "setMod"):
                col.setMod()
            if hasattr(col, "save"):
                col.save()

    except Exception as e:
        log(f"[NID] Erreur lors de la migration des NID : {e}")
        if not silent and not auto and mw:
            try:
                showCritical(f"Une erreur est survenue lors de la migration des NID :\n{e}")
            except Exception:
                pass
        return 0, f"Erreur migration : {e}"
    finally:
        try:
            if orig_fk is not None:
                col.db.execute(f"PRAGMA foreign_keys = {1 if orig_fk else 0}")
            else:
                col.db.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass

        if not auto and mw and getattr(mw, "progress", None):
            try:
                mw.progress.finish()
            except Exception:
                pass

        if mw:
            if hasattr(col, "reset"):
                try:
                    col.reset()
                except Exception:
                    pass
            if hasattr(mw, "reset"):
                try:
                    mw.reset()
                except Exception:
                    pass

    if updated > 0:
        if hasattr(col, "mod_schema"):
            try:
                col.mod_schema(check=False)
            except Exception:
                pass
        elif hasattr(col, "modSchema"):
            try:
                col.modSchema(check=False)
            except Exception:
                pass

        msg = f"NIDs réparés ({updated} notes mises à jour)."
        log(f"[NID] {msg}")

        if not silent and mw and getattr(mw, "app", None):
            try:
                tooltip(msg, period=3500)
            except Exception:
                pass

        if trigger_sync and mw:
            if hasattr(mw, "onSync"):
                try:
                    mw.onSync()
                except Exception:
                    pass
            elif hasattr(mw, "on_sync_button_clicked"):
                try:
                    mw.on_sync_button_clicked()
                except Exception:
                    pass

        return updated, msg
    else:
        msg = "Tous les NIDs sont déjà à jour."
        log(f"[NID] {msg}")
        if not silent and not auto and mw and getattr(mw, "app", None):
            try:
                tooltip(msg, period=2500)
            except Exception:
                pass
        return 0, msg


def detect_nid_repair_status(col=None, mapping_file: Optional[str] = None) -> Dict[str, Any]:
    """Detect whether note IDs for linked cards are already aligned with admin mapping."""
    if col is None and mw:
        col = getattr(mw, "col", None)
    if not col:
        return {"done": True, "badge": "À jour", "details": "Collection non disponible", "pending": 0}

    if mapping_file is None:
        mapping_file = get_nid_mapping_path()

    if not mapping_file or not os.path.exists(mapping_file):
        return {"done": True, "badge": "À jour", "details": "Module NID absent ou déjà synchronisé", "pending": 0}

    try:
        lines = []
        if mapping_file.endswith(".json"):
            with open(mapping_file, "r", encoding="utf-8") as f:
                raw_json = json.load(f)
                if isinstance(raw_json, dict):
                    lines = [f"{guid},{nid}" for guid, nid in raw_json.items()]
        else:
            with codecs.open(mapping_file, "r", "utf-8") as f:
                lines = f.readlines()

        local_notes = dict(col.db.all("SELECT guid, id FROM notes"))
        if not local_notes:
            return {"done": True, "badge": "À jour", "details": "Aucune note présente", "pending": 0}

        pending = 0
        matched = 0
        for line in lines:
            line = line.strip()
            if not line or "," not in line:
                continue
            guid, nid_str = line.rsplit(",", 1)
            try:
                admin_nid = int(nid_str)
            except ValueError:
                continue
            local_nid = local_notes.get(guid)
            if local_nid is not None:
                matched += 1
                if local_nid != admin_nid:
                    pending += 1

        if matched == 0:
            return {"done": True, "badge": "À jour", "details": "Aucune carte liée EDN dans la collection", "pending": 0}
        if pending == 0:
            return {"done": True, "badge": "Déjà synchronisé", "details": f"{matched} notes liées déjà synchronisées", "pending": 0}
        return {"done": False, "badge": f"{pending} à réparer", "details": f"{pending} NID(s) à réaligner", "pending": pending}
    except Exception as e:
        return {"done": True, "badge": "À jour", "details": f"Vérification ignorée: {e}", "pending": 0}


def install_ankicollab_deck_hook():
    """
    Hook AnkiCollab's _on_deck_installed to automatically trigger NID repair
    as soon as a deck download/update completes.
    """
    try:
        import sys
        for mod_name in ("1957538407.import_manager", "AnkiCollab.import_manager"):
            im = sys.modules.get(mod_name)
            if im and hasattr(im, "_on_deck_installed") and not hasattr(im, "_edn_orig_on_deck_installed"):
                orig = im._on_deck_installed
                im._edn_orig_on_deck_installed = orig

                def wrapped_on_deck_installed(install_result, deck, subscription, input_hash=None, update_timestamp_after=False):
                    res = orig(install_result, deck, subscription, input_hash=input_hash, update_timestamp_after=update_timestamp_after)
                    try:
                        deck_name = ""
                        try:
                            deck_name = str(deck.anki_dict.get("name", ""))
                        except Exception:
                            pass
                        # Trigger if it's the EDN deck or if no name could be read (safe catch-all)
                        if not deck_name or "edn" in deck_name.lower():
                            log(f"[NID] Fin du téléchargement AnkiCollab ('{deck_name}'). Déclenchement automatique de la réparation des NID...")
                            target_col = getattr(mw, "col", None)
                            migrate_nids(col=target_col, auto=True, silent=False, trigger_sync=True)
                    except Exception as e:
                        log(f"[NID] Erreur réparation automatique post-téléchargement AnkiCollab : {e}")
                    return res

                im._on_deck_installed = wrapped_on_deck_installed
                log("[NID] Hook AnkiCollab installé sur import_manager._on_deck_installed.")
                break
    except Exception as e:
        log(f"[NID] Erreur installation hook AnkiCollab: {e}")


def init_nid_repair_hooks():
    """Register lifecycle hooks for NID repair and AnkiCollab interception."""
    install_ankicollab_deck_hook()
    if gui_hooks:
        if hasattr(gui_hooks, "main_window_did_init"):
            gui_hooks.main_window_did_init.append(install_ankicollab_deck_hook)
        if hasattr(gui_hooks, "profile_did_open"):
            gui_hooks.profile_did_open.append(lambda *_: install_ankicollab_deck_hook())
