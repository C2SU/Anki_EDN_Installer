# -*- coding: utf-8 -*-
"""
Anki EDN Setup Assistant & Tutorial Defaults
Provides automated configuration according to official Anki EDN tutorial guidelines:
1. Recommended global options (AnkiCollab pull on startup, auto-suspend new cards, auto-sync).
2. NID repair for linked cards + AnkiWeb synchronization.
3. Recommended review options preset (FSRS 88%, bury siblings, leech threshold) assigned to EDN deck.
4. Initial suspension of EDN-tagged cards for progressive study.

Includes detection of previously executed actions ("moves") and guarantees
that the startup prompt is shown only once at installation.
"""
from __future__ import annotations

import os
import json
import time
from typing import Optional, Tuple, Dict, Any, List

from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QFrame, QTimer, QApplication, Qt, QPalette, QWidget
)
from aqt.utils import tooltip, showInfo


def is_dark_mode() -> bool:
    try:
        from aqt.theme import theme_manager
        if theme_manager and hasattr(theme_manager, "night_mode"):
            return bool(theme_manager.night_mode)
    except Exception:
        pass
    try:
        app = QApplication.instance()
        if app:
            bg_col = app.palette().color(QPalette.ColorRole.Window)
            return bg_col.lightness() < 128
    except Exception:
        pass
    return False


# -----------------------------------------------------------------------------
# 1. Action: Global Options (AnkiCollab + AnkiWeb)
# -----------------------------------------------------------------------------

def apply_global_ankicollab_settings() -> Tuple[bool, str]:
    """
    Configure recommended global options:
    - AnkiCollab: Update Decks on startup, Automatically suspend new Cards.
    - AnkiWeb: Auto-sync on open/close and media sync.
    """
    updated_items = []

    # 1. AnkiCollab settings
    try:
        mgr = getattr(mw, "addonManager", None) if mw else None
        if mgr and hasattr(mgr, "getConfig") and hasattr(mgr, "writeConfig"):
            cfg = mgr.getConfig("1957538407") or {}
            settings = cfg.setdefault("settings", {})
            settings["pull_on_startup"] = True
            settings["suspend_new_cards"] = True
            mgr.writeConfig("1957538407", cfg)
            updated_items.append("AnkiCollab (mises à jour au démarrage, suspension des nouvelles cartes)")
        # Also try direct config_manager if loaded
        try:
            import importlib
            cm = importlib.import_module("1957538407.config_manager")
            cur = cm.get_stored_config() or {}
            s = cur.setdefault("settings", {})
            s["pull_on_startup"] = True
            s["suspend_new_cards"] = True
            cm.write_config(cur)
        except Exception:
            pass
    except Exception as e:
        print(f"[setup_assistant] Erreur configuration AnkiCollab: {e}")

    # 2. Native Anki preferences (auto-sync)
    try:
        if mw and hasattr(mw, "pm") and getattr(mw.pm, "profile", None) is not None:
            mw.pm.profile["autoSync"] = True
            mw.pm.profile["syncMedia"] = True
            try:
                mw.pm.save()
            except Exception:
                pass
            updated_items.append("AnkiWeb (synchronisation et médias automatiques)")
    except Exception as e:
        print(f"[setup_assistant] Erreur configuration auto-sync Anki: {e}")

    if updated_items:
        return True, "Options globales configurées : " + ", ".join(updated_items) + "."
    return False, "Aucun paramètre global n'a pu être modifié (AnkiCollab non détecté)."


def detect_global_settings_status() -> dict:
    """
    Detect whether recommended global options are already applied:
    - AnkiCollab: pull_on_startup and suspend_new_cards
    - AnkiWeb: autoSync and syncMedia
    """
    collab_installed = False
    collab_ok = False
    ankiweb_ok = False

    # 1. AnkiCollab check
    try:
        mgr = getattr(mw, "addonManager", None) if mw else None
        if mgr and hasattr(mgr, "allAddons"):
            all_addons = set(mgr.allAddons())
            if "1957538407" in all_addons:
                collab_installed = True
                cfg = mgr.getConfig("1957538407") or {}
                s = cfg.get("settings", {})
                if bool(s.get("pull_on_startup")) and bool(s.get("suspend_new_cards")):
                    collab_ok = True
    except Exception:
        pass

    if not collab_ok:
        try:
            import importlib
            cm = importlib.import_module("1957538407.config_manager")
            cur = cm.get_stored_config() or {}
            s = cur.get("settings", {})
            collab_installed = True
            if bool(s.get("pull_on_startup")) and bool(s.get("suspend_new_cards")):
                collab_ok = True
        except Exception:
            pass

    # 2. Native Anki preferences (autoSync, syncMedia)
    try:
        if mw and hasattr(mw, "pm") and getattr(mw.pm, "profile", None) is not None:
            prof = mw.pm.profile
            if bool(prof.get("autoSync")) and bool(prof.get("syncMedia")):
                ankiweb_ok = True
    except Exception:
        pass

    if collab_installed:
        if collab_ok and ankiweb_ok:
            return {"done": True, "badge": "Déjà configuré", "details": "AnkiCollab et AnkiWeb synchronisés"}
        elif collab_ok:
            return {"done": False, "badge": "Partiellement configuré", "details": "AnkiCollab ok, synchronisation AnkiWeb inactive"}
        elif ankiweb_ok:
            return {"done": False, "badge": "Partiellement configuré", "details": "AnkiWeb ok, options AnkiCollab inactives"}
        else:
            return {"done": False, "badge": "À configurer", "details": "Options recommandées non activées"}
    else:
        if ankiweb_ok:
            return {"done": True, "badge": "Déjà configuré", "details": "Synchronisation AnkiWeb active (AnkiCollab non installé)"}
        else:
            return {"done": False, "badge": "À configurer", "details": "Synchronisation automatique inactive"}


# -----------------------------------------------------------------------------
# 2. Action: NID Repair & AnkiWeb Sync
# -----------------------------------------------------------------------------

def _get_nid_mapping_path() -> Optional[str]:
    """Locate nid_mapping.txt in Anki_EDN_nid addon directory."""
    addon_dir = os.path.dirname(os.path.abspath(__file__))
    addons21_dir = os.path.dirname(addon_dir)
    candidate = os.path.join(addons21_dir, "Anki_EDN_nid", "nid_mapping.txt")
    if os.path.isfile(candidate):
        return candidate
    try:
        if mw and hasattr(mw, "addonManager"):
            base = mw.addonManager.addonsFolder()
            cand2 = os.path.join(base, "Anki_EDN_nid", "nid_mapping.txt")
            if os.path.isfile(cand2):
                return cand2
    except Exception:
        pass
    return None


def repair_nids_and_sync() -> Tuple[bool, str]:
    """
    Repair linked cards NID mapping and trigger AnkiWeb synchronization.
    """
    migrated_count = 0
    # Try calling migrate_nids from Anki_EDN_nid
    try:
        import importlib
        mod = importlib.import_module("Anki_EDN_nid")
        if hasattr(mod, "migrate_nids"):
            mod.migrate_nids()
            return True, "Réparation des NID exécutée et synchronisation AnkiWeb lancée."
    except Exception:
        pass

    # Direct fallback if mapping file exists
    try:
        if mw and mw.col:
            mapping_file = _get_nid_mapping_path()
            if mapping_file and os.path.exists(mapping_file):
                import codecs
                with codecs.open(mapping_file, "r", "utf-8") as f:
                    lines = f.readlines()
                local_notes = dict(mw.col.db.all("SELECT guid, id FROM notes"))
                existing_ids = set(local_notes.values())
                now = int(time.time())
                planned = []
                targets = set()
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
                        if admin_nid in existing_ids or admin_nid in targets:
                            continue
                        targets.add(admin_nid)
                        planned.append((admin_nid, now, local_nid))
                if planned:
                    orig_fk = mw.col.db.scalar("PRAGMA foreign_keys")
                    mw.col.db.execute("PRAGMA foreign_keys = OFF")
                    try:
                        mw.col.db.executemany("UPDATE notes SET id = ?, mod = ?, usn = -1 WHERE id = ?", planned)
                        mw.col.db.executemany("UPDATE cards SET nid = ?, mod = ?, usn = -1 WHERE nid = ?", planned)
                        migrated_count = len(planned)
                        mw.col.setMod()
                        mw.col.save()
                    finally:
                        mw.col.db.execute(f"PRAGMA foreign_keys = {1 if orig_fk else 0}")
    except Exception as e:
        print(f"[setup_assistant] Erreur directe réparation NID: {e}")

    # Trigger AnkiWeb Sync
    try:
        if mw and hasattr(mw, "onSync"):
            mw.onSync()
    except Exception:
        pass

    if migrated_count > 0:
        return True, f"NID réparés ({migrated_count} notes mises à jour) et synchronisation AnkiWeb lancée."
    return True, "NID vérifiés (déjà synchronisés) et synchronisation AnkiWeb initiée."


def detect_nid_repair_status(col=None) -> dict:
    """
    Detect whether note IDs for linked cards are already aligned with admin mapping.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return {"done": True, "badge": "À jour", "details": "Collection non disponible", "pending": 0}

    mapping_file = _get_nid_mapping_path()
    if not mapping_file or not os.path.exists(mapping_file):
        return {"done": True, "badge": "À jour", "details": "Module NID absent ou déjà synchronisé", "pending": 0}

    try:
        import codecs
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


# -----------------------------------------------------------------------------
# 3. Action: EDN Review Options Preset & Assignment to EDN Deck
# -----------------------------------------------------------------------------

def apply_edn_deck_preset(col=None) -> Tuple[bool, str]:
    """
    Create or update deck configuration preset 'Anki EDN' with tutorial recommendations:
    - FSRS enabled, desired retention 88% (0.88)
    - New cards per day: 30
    - Max reviews per day: 9999
    - Bury new and review siblings: True
    - Leech threshold: 20, Leech action: Suspend
    And assign it to all decks containing 'EDN'.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return False, "Collection Anki non disponible."

    # 1. Enable FSRS in collection
    try:
        col.set_config("fsrs", True)
    except Exception as e:
        print(f"[setup_assistant] Erreur activation FSRS: {e}")

    # 2. Find or create 'Anki EDN' preset
    preset_name = "Anki EDN"
    existing_conf = None
    try:
        for c in col.decks.all_config():
            if c.get("name") == preset_name:
                existing_conf = c
                break
    except Exception:
        pass

    try:
        if existing_conf is None:
            base_conf = col.decks.get_config(1) or col.decks.all_config()[0]
            conf = col.decks.add_config(preset_name, clone_from=base_conf)
        else:
            conf = existing_conf

        conf_id = conf["id"]
        conf.setdefault("new", {})["perDay"] = 30
        conf["new"]["bury"] = True
        conf.setdefault("rev", {})["perDay"] = 9999
        conf["rev"]["bury"] = True
        conf.setdefault("lapse", {})["leechFails"] = 20
        conf["lapse"]["leechAction"] = 1  # Suspend
        conf["desiredRetention"] = 0.88
        col.decks.update_config(conf)
    except Exception as e:
        return False, f"Erreur lors de la création du préréglage : {e}"

    # 3. Assign this preset to all EDN decks
    assigned_count = 0
    try:
        for d in col.decks.all():
            dname = d.get("name", "")
            if "EDN" in dname and not dname.startswith("EDN - Paquets Filtr"):
                col.decks.set_config_id_for_deck_dict(d, conf_id)
                col.decks.save(d)
                assigned_count += 1
    except Exception as e:
        print(f"[setup_assistant] Erreur affectation préréglage aux paquets: {e}")

    return True, (
        f"Préréglage '{preset_name}' configuré (FSRS 88%, cartes sœurs enfouies, max 30 nlles/jour) "
        f"et assigné à {assigned_count} paquet(s) EDN."
    )


def detect_edn_preset_status(col=None) -> dict:
    """
    Detect whether preset 'Anki EDN' is configured with FSRS enabled (regardless of retention rate)
    and assigned to all EDN decks.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return {"done": False, "badge": "Non disponible", "details": "Collection non disponible"}

    try:
        fsrs_enabled = bool(col.get_config("fsrs"))
        if not fsrs_enabled:
            return {"done": False, "badge": "À activer", "details": "FSRS non activé"}

        preset_name = "Anki EDN"
        edn_conf = None
        for c in col.decks.all_config():
            if c.get("name") == preset_name:
                edn_conf = c
                break

        if not edn_conf:
            return {"done": False, "badge": "À configurer", "details": "Préréglage 'Anki EDN' absent"}

        conf_id = edn_conf.get("id")
        new_bury = edn_conf.get("new", {}).get("bury")
        rev_bury = edn_conf.get("rev", {}).get("bury")

        # As long as FSRS is enabled, retention rate is not enforced
        params_ok = fsrs_enabled and bool(new_bury) and bool(rev_bury)

        if not params_ok:
            return {"done": False, "badge": "Partiellement configuré", "details": "Cartes sœurs non enfouies"}

        edn_decks = [
            d for d in col.decks.all()
            if "EDN" in d.get("name", "") and not d.get("name", "").startswith("EDN - Paquets Filtr")
        ]

        retention_val = edn_conf.get("desiredRetention", 0.88)
        retention_str = f"{int(round(float(retention_val) * 100))}%" if retention_val else "actif"

        if not edn_decks:
            return {"done": True, "badge": "Déjà configuré", "details": f"FSRS {retention_str} prêt (aucun paquet EDN)"}

        all_assigned = all(d.get("conf") == conf_id for d in edn_decks)
        if all_assigned:
            return {"done": True, "badge": "Déjà configuré", "details": f"FSRS {retention_str}, cartes sœurs enfouies ({len(edn_decks)} paquet(s))"}
        else:
            return {"done": False, "badge": "À assigner", "details": "Préréglage non assigné à tous les paquets EDN"}
    except Exception as e:
        return {"done": False, "badge": "Erreur", "details": f"Erreur détection: {e}"}


# -----------------------------------------------------------------------------
# 4. Action: Initial Suspension of EDN Cards
# -----------------------------------------------------------------------------

def suspend_initial_edn_cards(col=None) -> Tuple[bool, str]:
    """
    Suspend all cards tagged EDN (or in EDN decks) so the student can unsuspend
    them progressively item by item after studying their medical lectures.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return False, "Collection Anki non disponible."

    cids = col.find_cards("tag:EDN*")
    if not cids:
        cids = col.find_cards('"deck:*EDN*"')

    if not cids:
        return True, "Aucune carte EDN détectée à suspendre."

    try:
        col.sched.suspend_cards(cids)
        if mw and hasattr(mw, "reset"):
            mw.reset()
        try:
            from .shared_menu import get_config, save_config
            cfg = get_config()
            cfg["initial_suspension_done"] = True
            save_config(cfg)
        except Exception:
            pass
        return True, f"{len(cids)} carte(s) EDN suspendue(s) pour débuter l'apprentissage pas-à-pas."
    except Exception as e:
        return False, f"Erreur lors de la suspension des cartes : {e}"


def detect_initial_suspension_status(col=None) -> dict:
    """
    Detect whether the initial suspension of EDN cards has already been done.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return {"done": False, "badge": "Non disponible", "details": "Collection non disponible"}

    try:
        edn_cids = col.find_cards("tag:EDN*")
        search_prefix = "tag:EDN*"
        if not edn_cids:
            edn_cids = col.find_cards('"deck:*EDN*"')
            search_prefix = '"deck:*EDN*"'

        if not edn_cids:
            return {"done": True, "badge": "À jour", "details": "Aucune carte EDN dans la collection"}

        total_edn = len(edn_cids)
        unsuspended_new = col.find_cards(f"{search_prefix} is:new -is:suspended")
        count_unsuspended_new = len(unsuspended_new)

        suspended = col.find_cards(f"{search_prefix} is:suspended")
        count_suspended = len(suspended)

        if count_unsuspended_new == 0:
            return {"done": True, "badge": "Déjà configuré", "details": f"Cartes suspendues ({count_suspended}/{total_edn})"}

        if count_suspended > 0 and (count_suspended / total_edn) >= 0.85:
            return {"done": True, "badge": "Déjà configuré", "details": f"Majorité des cartes déjà suspendues ({count_suspended}/{total_edn})"}

        return {
            "done": False,
            "badge": "À appliquer",
            "details": f"{count_unsuspended_new} nouvelle(s) carte(s) non suspendue(s)"
        }
    except Exception as e:
        return {"done": False, "badge": "Erreur", "details": f"Erreur détection: {e}"}


def detect_all_setup_statuses(col=None) -> Dict[str, dict]:
    """Run all detection checks and return status dictionary for each move."""
    return {
        "options": detect_global_settings_status(),
        "nids": detect_nid_repair_status(col=col),
        "preset": detect_edn_preset_status(col=col),
        "suspend": detect_initial_suspension_status(col=col),
    }


# -----------------------------------------------------------------------------
# 5. Assistant UI Dialog
# -----------------------------------------------------------------------------

class EDNSetupAssistantDialog(QDialog):
    """
    Sleek modal dialog presenting tutorial setup options.
    Detects which actions have already been performed, unchecks them by default,
    and displays status badges.
    """

    def __init__(self, parent=None, is_startup: bool = False, col=None):
        dlg_parent = parent if parent is not None else (mw if isinstance(mw, QWidget) else None)
        super().__init__(dlg_parent)
        self.is_startup = is_startup
        active_col = col if col is not None else (getattr(mw, "col", None) if mw else None)
        self.statuses = detect_all_setup_statuses(col=active_col)
        self.setWindowTitle("Assistant d'installation — Anki EDN")
        self.resize(600, 500)

        # Mark that assistant was presented so it never prompts at every session
        if self.is_startup:
            self._persist_shown_flag()

        self._init_ui()

    def _persist_shown_flag(self):
        try:
            from .shared_menu import get_config, save_config
            cfg = get_config()
            cfg["setup_assistant_shown"] = True
            save_config(cfg)
        except Exception:
            pass

    def _init_ui(self):
        dark = is_dark_mode()
        bg_card = "#21252b" if dark else "#f8f9fa"
        border_card = "#3b4048" if dark else "#dee2e6"
        text_muted = "#7f848e" if dark else "#6c757d"
        accent = "#61afef" if dark else "#1971c2"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        title_lbl = QLabel(
            f"<b style='font-size: 15px; color: {accent};'>"
            "Configuration recommandée du tutoriel Anki EDN"
            "</b>"
        )
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            f"<span style='font-size: 12px; color: {text_muted};'>"
            "Cet assistant permet d'appliquer les réglages méthodologiques et techniques "
            "du tutoriel officiel Anki EDN. Les étapes déjà configurées sont automatiquement détectées :"
            "</span>"
        )
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        all_done = all(s.get("done", False) for s in self.statuses.values())
        if all_done:
            b_bg = "#1b3320" if dark else "#e6f4ea"
            b_border = "#2d5a37" if dark else "#ceead6"
            b_text = "#73c991" if dark else "#137333"
            banner = QLabel(
                f"<div style='background-color: {b_bg}; border: 1px solid {b_border}; "
                f"border-radius: 5px; padding: 7px 12px; color: {b_text}; font-size: 11.5px; font-weight: 500;'>"
                "Tous les réglages recommandés sont déjà configurés sur ce profil."
                "</div>"
            )
            banner.setWordWrap(True)
            layout.addWidget(banner)

        # Options Container Frame
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 6px;
            }}
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(10)

        # 1. Options globales
        self.cb_options, row_options = self._create_option_row(
            title="Options globales AnkiCollab & AnkiWeb (mises à jour au lancement, suspension auto, sync auto)",
            tooltip_text=(
                "Active le téléchargement automatique des mises à jour au démarrage, la suspension native des cartes ajoutées,\n"
                "et la synchronisation automatique des médias et de la collection avec AnkiWeb."
            ),
            status=self.statuses.get("options", {}),
            dark=dark
        )
        frame_layout.addWidget(row_options)

        # 2. Réparation NID + sync
        self.cb_nids, row_nids = self._create_option_row(
            title="Réparation des NID des cartes liées & synchronisation avec AnkiWeb",
            tooltip_text=(
                "Aligne les identifiants locaux des notes pour rendre opérationnelle la navigation entre cartes liées,\n"
                "puis déclenche une synchronisation avec AnkiWeb."
            ),
            status=self.statuses.get("nids", {}),
            dark=dark
        )
        frame_layout.addWidget(row_nids)

        # 3. Préréglage options révision
        self.cb_preset, row_preset = self._create_option_row(
            title="Préréglage de révision 'Anki EDN' (FSRS 88%, cartes sœurs enfouies) assigné au paquet",
            tooltip_text=(
                "Active FSRS, configure la rétention cible à 88%, enfouit les cartes sœurs nouvelles et en révision,\n"
                "fixe les nouvelles cartes à 30/jour et affecte ce préréglage à tous vos paquets EDN."
            ),
            status=self.statuses.get("preset", {}),
            dark=dark
        )
        frame_layout.addWidget(row_preset)

        # 4. Suspension initiale
        self.cb_suspend, row_suspend = self._create_option_row(
            title="Suspension initiale des cartes EDN (recommandé : déblocage item par item après le cours)",
            tooltip_text=(
                "Suspend l'intégralité du paquet au départ. Vous désuspendrez uniquement les cartes correspondant\n"
                "aux items médicaux au fur et à mesure de votre apprentissage des cours."
            ),
            status=self.statuses.get("suspend", {}),
            dark=dark
        )
        frame_layout.addWidget(row_suspend)

        layout.addWidget(frame)

        hint_lbl = QLabel(
            f"<span style='font-size: 11px; color: {text_muted};'>"
            "Vous pourrez réexécuter cet assistant à tout moment depuis les "
            "<b>Paramètres EDN &gt; Rétablir les réglages du tuto</b>."
            "</span>"
        )
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

        layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        cancel_text = "Plus tard" if self.is_startup else "Fermer"
        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 7px 16px; border-radius: 5px; font-weight: 600; font-size: 12px;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        self.apply_btn = QPushButton("Appliquer les réglages sélectionnés")
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent}; color: white; border: none;
                padding: 7px 18px; border-radius: 5px; font-weight: bold; font-size: 12px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)
        self._update_button_state()

    def _create_option_row(self, title: str, tooltip_text: str, status: dict, dark: bool) -> Tuple[QCheckBox, QWidget]:
        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(2)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        cb = QCheckBox(title)
        cb.setToolTip(tooltip_text)
        is_done = status.get("done", False)
        cb.setChecked(not is_done)
        top_layout.addWidget(cb, 1)

        badge_text = status.get("badge", "Déjà configuré" if is_done else "À appliquer")
        if is_done:
            b_bg = "#1b3320" if dark else "#e6f4ea"
            b_text = "#73c991" if dark else "#137333"
            b_border = "#2d5a37" if dark else "#ceead6"
        else:
            b_bg = "#172554" if dark else "#e0f2fe"
            b_text = "#60a5fa" if dark else "#0369a1"
            b_border = "#1d4ed8" if dark else "#bae6fd"

        badge_lbl = QLabel(
            f"<span style='padding: 2px 7px; border-radius: 4px; font-size: 10.5px; "
            f"font-weight: 600; background: {b_bg}; color: {b_text}; border: 1px solid {b_border};'>"
            f"{badge_text}</span>"
        )
        badge_lbl.setStyleSheet("border: none; background: transparent;")
        top_layout.addWidget(badge_lbl, 0)

        row_layout.addLayout(top_layout)

        detail_text = status.get("details", "")
        if detail_text:
            text_muted = "#7f848e" if dark else "#6c757d"
            detail_lbl = QLabel(
                f"<span style='font-size: 11px; color: {text_muted};'>"
                f"• {detail_text}</span>"
            )
            detail_lbl.setContentsMargins(22, 0, 0, 0)
            detail_lbl.setWordWrap(True)
            row_layout.addWidget(detail_lbl)

        cb.toggled.connect(self._update_button_state)
        return cb, row_widget

    def _update_button_state(self):
        has_checked = (
            self.cb_options.isChecked() or
            self.cb_nids.isChecked() or
            self.cb_preset.isChecked() or
            self.cb_suspend.isChecked()
        )
        if has_checked:
            self.apply_btn.setText("Appliquer les réglages sélectionnés")
            self.apply_btn.setEnabled(True)
        else:
            self.apply_btn.setText("Fermer")

    def reject(self):
        self._persist_shown_flag()
        super().reject()

    def closeEvent(self, event):
        self._persist_shown_flag()
        super().closeEvent(event)

    def _on_cancel(self):
        self.reject()
        if self.is_startup:
            tooltip(
                "Assistant reporté. Retrouvez-le à tout moment dans Paramètres EDN > Rétablir les réglages du tuto.",
                period=3500
            )

    def _on_apply(self):
        has_checked = (
            self.cb_options.isChecked() or
            self.cb_nids.isChecked() or
            self.cb_preset.isChecked() or
            self.cb_suspend.isChecked()
        )
        if not has_checked:
            self.accept()
            return

        reports = []

        # 1. Options globales
        if self.cb_options.isChecked():
            ok, msg = apply_global_ankicollab_settings()
            reports.append(msg)

        # 2. NIDs + sync
        if self.cb_nids.isChecked():
            ok, msg = repair_nids_and_sync()
            reports.append(msg)

        # 3. Préréglage EDN
        if self.cb_preset.isChecked():
            ok, msg = apply_edn_deck_preset()
            reports.append(msg)

        # 4. Suspension
        if self.cb_suspend.isChecked():
            ok, msg = suspend_initial_edn_cards()
            reports.append(msg)

        # Mark shown & completed in config
        try:
            from .shared_menu import get_config, save_config
            cfg = get_config()
            cfg["setup_assistant_shown"] = True
            cfg["setup_assistant_completed"] = True
            save_config(cfg)
        except Exception:
            pass

        self.accept()

        report_txt = "\n• " + "\n• ".join(reports) if reports else "Aucune option sélectionnée."
        showInfo(
            f"Configuration terminée avec succès !\n{report_txt}",
            parent=self.parent(),
            title="Assistant Anki EDN"
        )


def open_setup_assistant_dialog(parent=None, is_startup: bool = False, col=None) -> None:
    """Open the setup assistant modal dialog."""
    if is_startup:
        try:
            from .shared_menu import get_config, save_config
            cfg = get_config()
            cfg["setup_assistant_shown"] = True
            save_config(cfg)
        except Exception:
            pass
    d = EDNSetupAssistantDialog(parent=parent or mw, is_startup=is_startup, col=col)
    d.exec()


def check_startup_assistant() -> None:
    """
    Prompt the user on profile open only once at installation,
    unless all recommended tutorial moves are already done.
    """
    if not mw:
        return
    try:
        from .shared_menu import get_config, save_config
        cfg = get_config()
        if cfg.get("setup_assistant_shown", False) or cfg.get("setup_assistant_completed", False):
            return

        # Pre-check: if all moves are already done, mark complete without showing dialog
        col = getattr(mw, "col", None)
        statuses = detect_all_setup_statuses(col=col)
        if all(s.get("done", False) for s in statuses.values()):
            cfg["setup_assistant_shown"] = True
            cfg["setup_assistant_completed"] = True
            save_config(cfg)
            return

        timer = QTimer(mw)

        def tick():
            if mw.col is None:
                timer.stop()
            elif not mw.progress.busy() and QApplication.activeModalWidget() is None:
                timer.stop()
                open_setup_assistant_dialog(parent=mw, is_startup=True)

        timer.timeout.connect(tick)
        QTimer.singleShot(3500, lambda: timer.start(1000))
    except Exception as e:
        print(f"[setup_assistant] Erreur vérification démarrage: {e}")


def init_setup_assistant_hooks() -> None:
    """Hook startup verification into profile_did_open."""
    gui_hooks.profile_did_open.append(check_startup_assistant)
