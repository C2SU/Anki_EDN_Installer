# -*- coding: utf-8 -*-
"""
Anki EDN Setup Assistant & Tutorial Defaults
Consolidates the automated installation workflow into a unified, guided, and lightweight assistant:
1. Pre-installation AnkiWeb sync to prevent "device / AnkiWeb" conflicts (`sync_first_then`).
2. Automatic check & 1-click installation of required AnkiWeb add-ons (`missing_addons`, `install_addons`).
3. Guided AnkiCollab subscription (share code copied, settings auto-applied, live deck polling).
4. Recommended global options (AnkiCollab pull on startup, auto-suspend new cards, auto-sync).
5. Recommended review options preset (FSRS 88%, bury siblings, leech threshold) assigned to EDN deck.
6. Initial suspension of EDN-tagged cards for progressive study (distinguishes new users vs existing reviewers).
7. NID repair for linked cards + AnkiWeb synchronization.
8. Import of medical abbreviations & symbols (`raccourcis.csv`) into Insert Symbols As You Type.
"""
from __future__ import annotations

import os
import json
import time
from typing import Optional, Tuple, Dict, Any, List, Callable

from aqt import mw, gui_hooks
from aqt.addons import download_addons
from aqt.operations import CollectionOp
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QPushButton,
    QFrame, QTimer, QApplication, Qt, QPalette, QWidget, QAction, QStackedWidget
)
from aqt.utils import tooltip, showInfo

STATE_KEY = "anki_edn_setup"
TITLE = "Anki EDN"

DEFAULT_SETUP_CONFIG: Dict[str, Any] = {
    "deck_name": "Anki EDN",
    "share_code": "mango-may-georgia-eleven-moon-orange",
    "addons": [
        1957538407,
        1052724801,
        1762336370,
        1201122026,
        445658251,
    ],
    "preset_name": "Anki EDN",
    "options": {
        "new_per_day": 30,
        "reviews_per_day": 9999,
        "desired_retention": 0.88,
        "leech_threshold": 20,
    },
}

ADDON_NAMES: Dict[int, str] = {
    1957538407: "AnkiCollab (synchronisation collaborative du paquet)",
    1052724801: "BetterSearch (recherche avancée par étiquette)",
    1762336370: "Insert Symbols As You Type (symboles médicaux)",
    1201122026: "Anki EDN Stats (statistiques d'avancement par item)",
    445658251: "Anki EDN Lier les cartes (navigation entre cartes liées)",
}

ADDON_LOCAL_ALIASES: Dict[int, Tuple[str, ...]] = {
    445658251: ("445658251", "Anki_EDN_Lier_les_cartes"),
    1201122026: ("1201122026", "Anki_EDN_Stats"),
    2135076010: ("2135076010", "Anki_EDN_nid", "Anki_EDN_NID"),
    1957538407: ("1957538407", "AnkiCollab"),
}

ANKICOLLAB_WINDOW_HINTS = (
    "ankicollab",
    "subscription",
    "global settings",
    "help improve the deck",
)

_poll_timer: Optional[QTimer] = None
_sync_callback: Optional[Callable] = None
_fallback_state: Dict[str, Any] = {}


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
# 0. Profile State & Pre-Installation Sync
# -----------------------------------------------------------------------------

def cfg() -> dict:
    """Return merged addon configuration with defaults."""
    merged = dict(DEFAULT_SETUP_CONFIG)
    merged["options"] = dict(DEFAULT_SETUP_CONFIG["options"])
    try:
        mgr = getattr(mw, "addonManager", None) if mw else None
        if mgr and hasattr(mgr, "getConfig"):
            pkg = __name__.split(".")[0]
            raw = mgr.getConfig(pkg) or mgr.getConfig(__name__)
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if k == "options" and isinstance(v, dict):
                        merged["options"].update(v)
                    else:
                        merged[k] = v
    except Exception:
        pass
    return merged


def get_state() -> dict:
    """Retrieve setup state stored in local profile (never in collection)."""
    defaults = {
        "stage": "start",
        "already_studied": False,
    }
    try:
        if mw and hasattr(mw, "pm") and isinstance(getattr(mw.pm, "profile", None), dict):
            raw = mw.pm.profile.get(STATE_KEY)
            if isinstance(raw, dict):
                merged = dict(defaults)
                merged.update(raw)
                return merged
            return dict(defaults)
    except Exception:
        pass
    merged = dict(defaults)
    merged.update(_fallback_state)
    return merged


def set_state(**changes) -> None:
    """Persist setup state in local profile."""
    st = get_state()
    st.update(changes)
    _fallback_state.update(st)
    try:
        if mw and hasattr(mw, "pm") and isinstance(getattr(mw.pm, "profile", None), dict):
            mw.pm.profile[STATE_KEY] = st
            try:
                mw.pm.save()
            except Exception:
                pass
    except Exception:
        pass


def is_logged_in_ankiweb() -> bool:
    try:
        return bool(mw and hasattr(mw, "pm") and mw.pm.sync_auth() is not None)
    except Exception:
        return False


def _on_sync_finished() -> None:
    global _sync_callback
    cb = _sync_callback
    _sync_callback = None
    try:
        gui_hooks.sync_did_finish.remove(_on_sync_finished)
    except ValueError:
        pass
    set_state(synced_once=True)
    if cb:
        QTimer.singleShot(1000, cb)


def sync_first_then(callback: Callable) -> None:
    """
    Synchronize with AnkiWeb before modifying the collection, then continue.
    Prevents 'device / AnkiWeb' full-sync conflicts during initial installation.
    """
    global _sync_callback
    if not is_logged_in_ankiweb() or get_state().get("synced_once"):
        callback()
        return
    if _sync_callback is not None:
        return
    _sync_callback = callback
    gui_hooks.sync_did_finish.append(_on_sync_finished)
    if getattr(mw, "app", None):
        tooltip("Synchronisation avec AnkiWeb avant l'installation…")
    sync = getattr(mw, "on_sync_button_clicked", None) or getattr(mw, "onSync", None)
    if callable(sync):
        sync()
    else:
        _on_sync_finished()


def deck_name() -> str:
    return str(cfg().get("deck_name", "Anki EDN"))


def deck_id(col=None):
    if col is None and mw:
        col = getattr(mw, "col", None)
    if not col:
        return None
    return col.decks.id_for_name(deck_name())


def deck_card_count(col=None) -> int:
    if col is None and mw:
        col = getattr(mw, "col", None)
    if not col or deck_id(col) is None:
        return 0
    return len(col.find_cards(f'deck:"{deck_name()}"'))


def find_menu_action(menu_name: str, keyword: str) -> Optional[QAction]:
    """Find a QAction in the main menu bar by menu title and action keyword."""
    try:
        if not mw or not getattr(mw, "form", None) or not getattr(mw.form, "menubar", None):
            return None
        for action in mw.form.menubar.actions():
            menu = action.menu()
            title = (action.text() or "").replace("&", "").lower()
            if menu is None or menu_name.lower() not in title:
                continue
            for sub in menu.actions():
                if keyword.lower() in (sub.text() or "").replace("&", "").lower():
                    return sub
    except Exception:
        pass
    return None


def trigger_nid_repair() -> bool:
    """Trigger NID repair via direct module function."""
    try:
        from .nid_repair import migrate_nids
        updated, _ = migrate_nids(silent=False, trigger_sync=True)
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# 1. Step 1: Required Add-ons Installation & Status
# -----------------------------------------------------------------------------

def missing_addons() -> List[int]:
    """Return list of required AnkiWeb add-on IDs not currently installed."""
    try:
        mgr = getattr(mw, "addonManager", None) if mw else None
        installed = set(mgr.allAddons()) if (mgr and hasattr(mgr, "allAddons")) else set()
    except Exception:
        installed = set()

    missing: List[int] = []
    for raw_id in cfg().get("addons", DEFAULT_SETUP_CONFIG["addons"]):
        try:
            aid = int(raw_id)
        except (ValueError, TypeError):
            continue
        aliases = ADDON_LOCAL_ALIASES.get(aid, (str(aid),))
        if not any(alias in installed for alias in aliases) and str(aid) not in installed:
            missing.append(aid)
    return missing


def install_addons(on_complete: Optional[Callable] = None) -> None:
    """Download and install missing required add-ons from AnkiWeb."""
    missing = missing_addons()
    if not missing:
        set_state(stage="addons_installed")
        if on_complete:
            on_complete()
        return

    def on_done(log) -> None:
        set_state(stage="addons_installed")
        if on_complete:
            on_complete()
        else:
            showInfo(
                "Les greffons nécessaires ont été installés avec succès.\n\n"
                "Fermez puis rouvrez Anki pour poursuivre l'installation.",
                title=TITLE,
            )

    download_addons(mw, mw.addonManager, missing, on_done)


def detect_required_addons_status() -> dict:
    """Detect whether all required AnkiWeb add-ons from config are installed."""
    all_req = cfg().get("addons", DEFAULT_SETUP_CONFIG["addons"])
    missing = missing_addons()
    total = len(all_req)
    installed_cnt = total - len(missing)
    if not missing:
        return {
            "done": True,
            "badge": "Déjà configuré",
            "details": f"Tous les greffons requis sont installés ({total}/{total})",
            "missing": [],
        }
    return {
        "done": False,
        "badge": f"{len(missing)} à installer",
        "details": f"{installed_cnt}/{total} greffons installés ({len(missing)} manquant(s) sur AnkiWeb)",
        "missing": missing,
    }


# -----------------------------------------------------------------------------
# 2. Step 2: AnkiCollab Guided Subscription & Deck Polling
# -----------------------------------------------------------------------------

def ankicollab_window_open() -> bool:
    """Return True if any AnkiCollab dialog/window is currently visible."""
    try:
        for w in QApplication.topLevelWidgets():
            if w.isVisible() and any(
                h in (w.windowTitle() or "").lower() for h in ANKICOLLAB_WINDOW_HINTS
            ):
                return True
    except Exception:
        pass
    return False


def guide_ankicollab(deck_present: bool = False) -> None:
    """Copy share code to clipboard, configure global AnkiCollab settings, and open AnkiCollab window."""
    code = cfg().get("share_code", DEFAULT_SETUP_CONFIG["share_code"])
    try:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(code)
    except Exception:
        pass

    try:
        apply_global_ankicollab_settings()
    except Exception:
        pass

    action = find_menu_action("AnkiCollab", "subscription") or find_menu_action(
        "AnkiCollab", "settings"
    )
    if action:
        action.trigger()
    wait_for_deck()


def wait_for_deck(timeout_s: int = 1800, on_ready: Optional[Callable] = None) -> None:
    """Poll for the arrival of the Anki EDN deck."""
    global _poll_timer
    if _poll_timer is not None:
        return
    started = time.time()
    last_count = {"n": -1}

    def stop() -> None:
        global _poll_timer
        if _poll_timer:
            _poll_timer.stop()
            _poll_timer = None

    def tick() -> None:
        if mw is None or getattr(mw, "col", None) is None:
            stop()
            return
        n = deck_card_count()
        if n > 0 and n == last_count["n"] and not ankicollab_window_open():
            stop()
            if on_ready:
                on_ready()
            else:
                finalize()
        elif time.time() - started > timeout_s:
            stop()
        last_count["n"] = n

    _poll_timer = QTimer(mw)
    _poll_timer.timeout.connect(tick)
    _poll_timer.start(5_000)


def apply_preset(did, col=None) -> None:
    """Apply the Anki EDN review options preset to the given deck ID and enable FSRS."""
    if col is None and mw:
        col = mw.col
    if not col or did is None:
        return

    c = cfg()
    opts = c.get("options", {})
    name = c.get("preset_name", "Anki EDN")

    existing = next(
        (x for x in col.decks.all_config() if x.get("name") == name), None
    )
    if existing:
        conf_id = existing["id"]
        conf = col.decks.get_config(conf_id)
    elif hasattr(col.decks, "add_config_returning_id"):
        conf_id = col.decks.add_config_returning_id(name)
        conf = col.decks.get_config(conf_id)
    else:
        base_conf = col.decks.get_config(1) or col.decks.all_config()[0]
        conf = col.decks.add_config(name, clone_from=base_conf)
        conf_id = conf["id"]

    conf.setdefault("new", {})["perDay"] = opts.get("new_per_day", 30)
    conf.setdefault("rev", {})["perDay"] = opts.get("reviews_per_day", 9999)
    conf["new"]["bury"] = True
    conf["rev"]["bury"] = True
    conf.setdefault("lapse", {})["leechFails"] = opts.get("leech_threshold", 20)
    conf["lapse"]["leechAction"] = 1
    conf["desiredRetention"] = opts.get("desired_retention", 0.88)
    col.decks.update_config(conf)

    deck = col.decks.get(did)
    if deck:
        deck["conf"] = conf_id
        col.decks.save(deck)

    col.set_config("fsrs", True)


def finalize(col=None) -> None:
    """Finalize initial Anki EDN installation cleanly."""
    if col is None and mw:
        col = getattr(mw, "col", None)
    if not col:
        return
    did = col.decks.id_for_name(deck_name())
    if did is None:
        return

    st = get_state()
    already_studied = bool(st.get("already_studied")) or (
        len(col.find_cards(f'deck:"{deck_name()}" -is:new')) > 0
    )

    apply_preset(did, col=col)
    try:
        apply_edn_deck_preset(col=col)
    except Exception:
        pass
    try:
        apply_edn_symbols_import()
    except Exception:
        pass

    def done(_=None) -> None:
        trigger_nid_repair()
        set_state(stage="done")
        try:
            from .shared_menu import get_config, save_config
            shared_cfg = get_config()
            shared_cfg["setup_assistant_shown"] = True
            shared_cfg["setup_assistant_completed"] = True
            if not already_studied:
                shared_cfg["initial_suspension_done"] = True
            save_config(shared_cfg)
        except Exception:
            pass
        if mw and getattr(mw, "deckBrowser", None):
            mw.deckBrowser.refresh()
        try:
            if getattr(mw, "app", None):
                tooltip("Configuration Anki EDN finalisée avec succès.")
        except Exception:
            pass

    if not already_studied:
        cids = list(col.find_cards(f'deck:"{deck_name()}" -is:suspended'))
        if mw and getattr(mw, "col", None) is col:
            try:
                CollectionOp(mw, lambda c: c.sched.suspend_cards(cids)).success(
                    done
                ).run_in_background()
                return
            except Exception:
                pass
        col.sched.suspend_cards(cids)
        done()
    else:
        done()


def continue_setup() -> None:
    """Entry point to launch or resume setup assistant."""
    open_setup_assistant_dialog(mw)


def on_setup_menu() -> None:
    """Handle 'Lancer / reprendre l'installation' menu action."""
    open_setup_assistant_dialog(mw)


# -----------------------------------------------------------------------------
# 4. Action: Global Options (AnkiCollab + AnkiWeb)
# -----------------------------------------------------------------------------

def apply_global_ankicollab_settings() -> Tuple[bool, str]:
    """Configure recommended global options for AnkiCollab and AnkiWeb."""
    updated_items = []
    try:
        mgr = getattr(mw, "addonManager", None) if mw else None
        if mgr and hasattr(mgr, "getConfig") and hasattr(mgr, "writeConfig"):
            ac_cfg = mgr.getConfig("1957538407") or {}
            settings = ac_cfg.setdefault("settings", {})
            settings["pull_on_startup"] = True
            settings["suspend_new_cards"] = True
            mgr.writeConfig("1957538407", ac_cfg)
            updated_items.append("AnkiCollab (mises à jour au démarrage, suspension des nouvelles cartes)")
        try:
            import importlib
            cm = importlib.import_module("1957538407.config_manager")
            cur = cm.get_stored_config() or {}
            cur_settings = cur.setdefault("settings", {})
            cur_settings["pull_on_startup"] = True
            cur_settings["suspend_new_cards"] = True
            cm.save_config_to_file(cur)
        except Exception:
            pass
    except Exception as e:
        print(f"[setup_assistant] Erreur config AnkiCollab: {e}")

    try:
        if mw and hasattr(mw, "pm") and hasattr(mw.pm, "profile"):
            prof = mw.pm.profile
            prof["autoSync"] = "always"
            prof["syncMedia"] = True
            mw.pm.save()
            updated_items.append("AnkiWeb (synchronisation automatique collection et médias)")
    except Exception as e:
        print(f"[setup_assistant] Erreur config AnkiWeb: {e}")

    if updated_items:
        return True, "Options globales configurées : " + ", ".join(updated_items) + "."
    return False, "Impossible de modifier les réglages AnkiCollab / AnkiWeb."


def detect_global_settings_status() -> dict:
    """
    Detect whether recommended global options are already applied:
    - AnkiCollab: pull_on_startup and suspend_new_cards
    - AnkiWeb: autoSync and syncMedia
    """
    collab_installed = False
    collab_ok = False
    ankiweb_ok = False

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
# 5. Action: Repair NIDs & Sync
# -----------------------------------------------------------------------------

def _get_nid_mapping_path() -> Optional[str]:
    from .nid_repair import get_nid_mapping_path as _get
    return _get()


def repair_nids_and_sync(col=None) -> Tuple[bool, str]:
    """Execute NID repair on the collection and trigger AnkiWeb synchronization."""
    from .nid_repair import migrate_nids
    mapping_file = _get_nid_mapping_path()
    updated, msg = migrate_nids(col=col, auto=False, silent=False, trigger_sync=True, mapping_file=mapping_file)
    return True, msg


def detect_nid_repair_status(col=None) -> dict:
    """Detect whether note IDs for linked cards are already aligned with admin mapping."""
    from .nid_repair import detect_nid_repair_status as _detect
    mapping_file = _get_nid_mapping_path()
    return _detect(col=col, mapping_file=mapping_file)


# -----------------------------------------------------------------------------
# 6. Action: Review Options Preset (FSRS)
# -----------------------------------------------------------------------------

def apply_edn_deck_preset(col=None) -> Tuple[bool, str]:
    """Configure or update the 'Anki EDN' deck options preset with recommended FSRS settings."""
    if col is None and mw:
        col = mw.col
    if not col:
        return False, "Collection Anki non disponible."

    c = cfg()
    preset_name = c.get("preset_name", "Anki EDN")
    opts = c.get("options", {})

    target_conf = None
    for conf in col.decks.all_config():
        if conf.get("name") == preset_name:
            target_conf = conf
            break

    if target_conf is None:
        if hasattr(col.decks, "add_config_returning_id"):
            conf_id = col.decks.add_config_returning_id(preset_name)
            target_conf = col.decks.get_config(conf_id)
        else:
            base_conf = col.decks.get_config(1) or col.decks.all_config()[0]
            target_conf = col.decks.add_config(preset_name, clone_from=base_conf)

    target_conf.setdefault("new", {})["perDay"] = opts.get("new_per_day", 30)
    target_conf["new"]["bury"] = True
    target_conf.setdefault("rev", {})["perDay"] = opts.get("reviews_per_day", 9999)
    target_conf["rev"]["bury"] = True
    target_conf.setdefault("lapse", {})["leechFails"] = opts.get("leech_threshold", 20)
    target_conf["lapse"]["leechAction"] = 1
    target_conf["desiredRetention"] = opts.get("desired_retention", 0.88)
    col.decks.update_config(target_conf)

    try:
        col.set_config("fsrs", True)
    except Exception:
        pass

    assigned_count = 0
    try:
        for deck in col.decks.all():
            dname = deck.get("name", "")
            if "EDN" in dname.upper():
                deck["conf"] = target_conf["id"]
                col.decks.save(deck)
                assigned_count += 1
    except Exception as e:
        print(f"[setup_assistant] Erreur affectation préréglage aux paquets: {e}")

    return True, (
        f"Préréglage '{preset_name}' configuré (FSRS, cartes sœurs enfouies, max 30 nlles/jour) "
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

        params_ok = fsrs_enabled and bool(new_bury) and bool(rev_bury)
        if not params_ok:
            return {"done": False, "badge": "Partiellement configuré", "details": "Cartes sœurs non enfouies"}

        edn_decks = [
            d for d in col.decks.all()
            if "EDN" in d.get("name", "") and not d.get("name", "").startswith("EDN - Paquets Filtr")
        ]

        retention_val = edn_conf.get("desiredRetention", 0.88)
        retention_str = f"{int(round(float(retention_val) * 100))}%" if retention_val else "88%"

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
# 7. Action: Initial Suspension of EDN Cards
# -----------------------------------------------------------------------------

def suspend_initial_edn_cards(col=None) -> Tuple[bool, str]:
    """
    Suspend new cards tagged EDN so the student can unsuspend them progressively.
    Never suspends cards already reviewed or in learning.
    """
    if col is None and mw:
        col = mw.col
    if not col:
        return False, "Collection Anki non disponible."

    search_prefix = "tag:EDN*"
    cids = col.find_cards(f"{search_prefix} is:new -is:suspended")
    if not cids:
        search_prefix = '"deck:*EDN*"'
        cids = col.find_cards(f"{search_prefix} is:new -is:suspended")

    if not cids:
        try:
            from .shared_menu import get_config, save_config
            shared_cfg = get_config()
            shared_cfg["initial_suspension_done"] = True
            save_config(shared_cfg)
        except Exception:
            pass
        return True, "Aucune nouvelle carte EDN à suspendre (déjà suspendues ou en révision)."

    try:
        col.sched.suspend_cards(cids)
        try:
            from .shared_menu import get_config, save_config
            shared_cfg = get_config()
            shared_cfg["initial_suspension_done"] = True
            save_config(shared_cfg)
        except Exception:
            pass
        return True, f"{len(cids)} carte(s) EDN suspendue(s) pour débuter l'apprentissage pas-à-pas."
    except Exception as e:
        return False, f"Erreur lors de la suspension des cartes : {e}"


def detect_initial_suspension_status(col=None) -> dict:
    """Detect whether initial suspension has been completed or if the deck is already initialized."""
    if col is None and mw:
        col = mw.col
    if not col:
        return {"done": False, "badge": "Non disponible", "details": "Collection non disponible"}

    try:
        from .shared_menu import get_config
        shared_cfg = get_config()
        if shared_cfg.get("initial_suspension_done"):
            return {
                "done": True,
                "badge": "Déjà configuré",
                "details": "Suspension initiale déjà validée sur ce profil"
            }

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

        learned = col.find_cards(f"{search_prefix} -is:new")
        count_learned = len(learned)

        if count_unsuspended_new == 0:
            return {
                "done": True,
                "badge": "Déjà configuré",
                "details": f"Toutes les cartes sont suspendues ou apprises ({count_suspended} susp., {count_learned} apprises)"
            }

        managed_count = count_suspended + count_learned
        if managed_count > 0:
            ratio_managed = managed_count / total_edn
            if ratio_managed >= 0.50 or count_learned >= 30 or count_suspended >= 100:
                return {
                    "done": True,
                    "badge": "Déjà configuré",
                    "details": f"Deck déjà initialisé ({count_suspended} suspendues, {count_learned} apprises, {count_unsuspended_new} actives)"
                }

        return {
            "done": False,
            "badge": "À appliquer",
            "details": f"{count_unsuspended_new} nouvelle(s) carte(s) à suspendre pour débuter"
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
        "symbols": detect_edn_symbols_status(col=col),
    }


# -----------------------------------------------------------------------------
# 8. Action: Import EDN Symbols
# -----------------------------------------------------------------------------

def apply_edn_symbols_import() -> Tuple[bool, str]:
    """Import medical abbreviations and symbols from raccourcis.csv into Anki collection."""
    try:
        from .symbols_importer import import_edn_symbols
        ok, msg, _ = import_edn_symbols(force=True)
        return ok, msg
    except Exception as e:
        return False, f"Erreur import symboles : {e}"


def detect_edn_symbols_status(col=None) -> dict:
    """Detect whether symbols from raccourcis.csv are already in table ins_symbols."""
    if col is None and mw:
        col = mw.col
    if not col or not hasattr(col, "db"):
        return {"done": False, "badge": "Non disponible", "details": "Collection non accessible"}
    try:
        from .symbols_importer import load_edn_symbols_from_csv
        symbols = load_edn_symbols_from_csv()
        if not symbols:
            return {"done": True, "badge": "À jour", "details": "Fichier de symboles vide"}

        tbl = col.db.first("SELECT name FROM sqlite_master WHERE type='table' AND name='ins_symbols'")
        if not tbl:
            return {
                "done": False,
                "badge": "À importer",
                "details": f"{len(symbols)} symboles médicaux à importer (Insert Symbols)"
            }

        rows = col.db.all("SELECT key FROM ins_symbols")
        existing_keys = {r[0] for r in rows}
        missing = [k for k, _ in symbols if k not in existing_keys]
        if not missing:
            return {
                "done": True,
                "badge": "Déjà configuré",
                "details": f"{len(symbols)} symboles et raccourcis importés"
            }
        elif len(missing) < len(symbols):
            return {
                "done": False,
                "badge": "Partiellement configuré",
                "details": f"{len(symbols) - len(missing)}/{len(symbols)} symboles présents ({len(missing)} manquants)"
            }
        else:
            return {
                "done": False,
                "badge": "À importer",
                "details": f"{len(symbols)} symboles à importer pour la saisie médicale"
            }
    except Exception as e:
        return {"done": False, "badge": "Erreur", "details": f"Erreur détection: {e}"}


# -----------------------------------------------------------------------------
# 9. Unified Multi-Step Assistant UI Dialog
# -----------------------------------------------------------------------------

class EDNSetupAssistantDialog(QDialog):
    """
    Unified, adaptive setup assistant:
    - Step 1: Missing add-ons installation.
    - Step 2: Guided AnkiCollab subscription.
    - Step 3: Recommended tutorial options application.
    """

    def __init__(self, parent=None, is_startup: bool = False, col=None):
        dlg_parent = parent if parent is not None else (mw if isinstance(mw, QWidget) else None)
        super().__init__(dlg_parent)
        self.setObjectName("ednSetupAssistantDialog")
        self.is_startup = is_startup
        self.active_col = col if col is not None else (getattr(mw, "col", None) if mw else None)
        self.statuses = detect_all_setup_statuses(col=self.active_col)
        self.addons_status = detect_required_addons_status()
        self.setWindowTitle("Assistant d'installation — Anki EDN")
        self.resize(640, 580)
        self._poll_timer: Optional[QTimer] = None

        if self.is_startup:
            self._persist_shown_flag()

        self._init_ui()

    def _persist_shown_flag(self):
        try:
            from .shared_menu import get_config, save_config
            shared_cfg = get_config()
            shared_cfg["setup_assistant_shown"] = True
            save_config(shared_cfg)
        except Exception:
            pass

    def _init_ui(self):
        dark = is_dark_mode()
        bg_dialog = "#1e2227" if dark else "#ffffff"
        text_main = "#abb2bf" if dark else "#212529"
        accent = "#61afef" if dark else "#1971c2"

        self.setStyleSheet(f"""
            QDialog#ednSetupAssistantDialog {{
                background-color: {bg_dialog};
                color: {text_main};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 13px;
            }}
            QDialog#ednSetupAssistantDialog QLabel {{
                color: {text_main};
            }}
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(12)

        # Header title
        self.header_title = QLabel(
            f"<b style='font-size: 15px; color: {accent};'>"
            "Configuration recommandée — Anki EDN"
            "</b>"
        )
        self.main_layout.addWidget(self.header_title)

        # Stacked pages for the 3 steps
        self.stack = QStackedWidget(self)

        # Page 1: Addons
        self.page_addons = self._create_addons_page(dark)
        self.stack.addWidget(self.page_addons)

        # Page 2: AnkiCollab
        self.page_ankicollab = self._create_ankicollab_page(dark)
        self.stack.addWidget(self.page_ankicollab)

        # Page 3: Presets & moves
        self.page_presets = self._create_presets_page(dark)
        self.stack.addWidget(self.page_presets)

        self.main_layout.addWidget(self.stack)

        # Determine starting page
        missing = self.addons_status.get("missing", [])
        deck_count = deck_card_count(self.active_col)

        if missing and getattr(mw, "col", None) is not None:
            self._switch_page(0)
        elif deck_count == 0 and getattr(mw, "col", None) is not None:
            self._switch_page(1)
        else:
            self._switch_page(2)

    def _switch_page(self, idx: int):
        self.stack.setCurrentIndex(idx)
        accent = "#61afef" if is_dark_mode() else "#1971c2"
        if idx == 0:
            self.header_title.setText(f"<b style='font-size: 15px; color: {accent};'>Étape 1 sur 3 : Extensions indispensables</b>")
        elif idx == 1:
            self.header_title.setText(f"<b style='font-size: 15px; color: {accent};'>Étape 2 sur 3 : Téléchargement du paquet officiel (AnkiCollab)</b>")
        else:
            self.header_title.setText(f"<b style='font-size: 15px; color: {accent};'>Configuration recommandée — Anki EDN</b>")

    # --- Page 1: Addons ---
    def _create_addons_page(self, dark: bool) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(12)

        desc = QLabel(
            "Pour faire fonctionner le paquet Anki EDN (synchronisation collaborative, "
            "liaison de cartes, recherche rapide et symboles médicaux), les extensions "
            "suivantes doivent être installées depuis AnkiWeb :"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        list_frame = QFrame()
        bg_card = "#21252b" if dark else "#f8f9fa"
        border_card = "#3b4048" if dark else "#dee2e6"
        list_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 6px;
                padding: 10px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setSpacing(6)

        missing = self.addons_status.get("missing", [])
        for aid in missing:
            name = ADDON_NAMES.get(aid, f"Extension AnkiWeb #{aid}")
            lbl = QLabel(f"• <b>{name}</b> (code : {aid})")
            list_layout.addWidget(lbl)
        layout.addWidget(list_frame)

        self.addons_status_lbl = QLabel(
            "<span style='font-size: 12px; color: #7f848e;'>"
            "Cliquez sur le bouton ci-dessous pour lancer le téléchargement automatique."
            "</span>"
        )
        self.addons_status_lbl.setWordWrap(True)
        layout.addWidget(self.addons_status_lbl)

        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Plus tard" if self.is_startup else "Fermer")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        self.install_addons_btn = QPushButton("Télécharger et installer les extensions")
        accent = "#61afef" if dark else "#1971c2"
        self.install_addons_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent}; color: white; border: none;
                padding: 8px 18px; border-radius: 5px; font-weight: bold; font-size: 12px;
            }}
        """)
        self.install_addons_btn.clicked.connect(self._on_install_addons_clicked)
        btn_row.addWidget(self.install_addons_btn)

        layout.addLayout(btn_row)
        return widget

    def _on_install_addons_clicked(self):
        missing = missing_addons()
        if not missing:
            self._switch_page(1)
            return

        self.install_addons_btn.setEnabled(False)
        self.addons_status_lbl.setText("<b>Téléchargement des extensions en cours depuis AnkiWeb...</b>")

        def on_done(log):
            set_state(stage="addons_installed")
            self.addons_status_lbl.setText(
                "<span style='color: #137333; font-weight: bold;'>"
                "Extensions installées avec succès ! Fermez et rouvrez Anki pour poursuivre."
                "</span>"
            )
            self.install_addons_btn.setText("Redémarrer Anki")
            self.install_addons_btn.setEnabled(True)
            self.install_addons_btn.clicked.disconnect()
            self.install_addons_btn.clicked.connect(self._restart_or_close)

        download_addons(mw, mw.addonManager, missing, on_done)

    def _restart_or_close(self):
        self.accept()
        restart_fn = getattr(mw, "unload_and_restart", None)
        if callable(restart_fn):
            restart_fn()
        else:
            showInfo("Veuillez fermer et relancer Anki pour charger les nouvelles extensions.", parent=mw)

    # --- Page 2: AnkiCollab ---
    def _create_ankicollab_page(self, dark: bool) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(12)

        desc = QLabel(
            "Toutes les extensions requises sont en place. L'étape suivante consiste à récupérer "
            "le paquet officiel Anki EDN sur AnkiCollab.<br><br>"
            "Le code de partage a été <b>automatiquement copié dans votre presse-papiers</b>, "
            "et les options AnkiCollab recommandées (mises à jour au lancement, suspension initiale) "
            "sont pré-configurées."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        code_frame = QFrame()
        bg_card = "#21252b" if dark else "#f8f9fa"
        border_card = "#3b4048" if dark else "#dee2e6"
        accent = "#61afef" if dark else "#1971c2"
        code_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 6px;
                padding: 12px;
            }}
            QLabel {{ border: none; background: transparent; }}
        """)
        code_layout = QVBoxLayout(code_frame)
        code = cfg().get("share_code", DEFAULT_SETUP_CONFIG["share_code"])
        code_lbl = QLabel(
            f"Code de partage : <code style='font-size: 13px; font-weight: bold; color: {accent};'>{code}</code>"
        )
        code_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code_layout.addWidget(code_lbl)
        layout.addWidget(code_frame)

        self.ankicollab_status_lbl = QLabel(
            "1. Cliquez sur le bouton ci-dessous pour ouvrir la fenêtre AnkiCollab.<br>"
            "2. Collez le code (Ctrl+V) dans « Share code » puis validez.<br>"
            "3. L'assistant détectera automatiquement la fin du téléchargement."
        )
        self.ankicollab_status_lbl.setWordWrap(True)
        layout.addWidget(self.ankicollab_status_lbl)

        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Plus tard" if self.is_startup else "Fermer")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()

        self.open_ankicollab_btn = QPushButton("Ouvrir AnkiCollab pour s'abonner")
        self.open_ankicollab_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent}; color: white; border: none;
                padding: 8px 18px; border-radius: 5px; font-weight: bold; font-size: 12px;
            }}
        """)
        self.open_ankicollab_btn.clicked.connect(self._on_open_ankicollab_clicked)
        btn_row.addWidget(self.open_ankicollab_btn)

        layout.addLayout(btn_row)
        return widget

    def _on_open_ankicollab_clicked(self):
        code = cfg().get("share_code", DEFAULT_SETUP_CONFIG["share_code"])
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(code)
        except Exception:
            pass

        try:
            apply_global_ankicollab_settings()
        except Exception:
            pass

        action = find_menu_action("AnkiCollab", "subscription") or find_menu_action(
            "AnkiCollab", "settings"
        )
        if action:
            action.trigger()

        self.ankicollab_status_lbl.setText(
            "<b>Fenêtre AnkiCollab ouverte.</b><br>"
            "Collez le code (Ctrl+V) dans « Share code » et validez.<br>"
            "<i>En attente du téléchargement du paquet Anki EDN...</i>"
        )
        self.open_ankicollab_btn.setEnabled(False)

        # Start live polling
        if self._poll_timer is None:
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._check_deck_arrival)
            self._poll_timer.start(2500)

    def _check_deck_arrival(self):
        cnt = deck_card_count(self.active_col)
        if cnt > 0 and not ankicollab_window_open():
            if self._poll_timer:
                self._poll_timer.stop()
                self._poll_timer = None
            try:
                from .nid_repair import migrate_nids
                migrate_nids(col=self.active_col, auto=True, silent=True, trigger_sync=False)
            except Exception:
                pass
            self.statuses = detect_all_setup_statuses(col=self.active_col)
            self._rebuild_presets_page()
            self._switch_page(2)

    # --- Page 3: Presets & Tutorial Moves ---
    def _create_presets_page(self, dark: bool) -> QWidget:
        self.presets_widget = QWidget()
        self.presets_layout = QVBoxLayout(self.presets_widget)
        self.presets_layout.setContentsMargins(0, 5, 0, 0)
        self.presets_layout.setSpacing(10)

        self._populate_presets_content(dark)
        return self.presets_widget

    def _rebuild_presets_page(self):
        dark = is_dark_mode()
        while self.presets_layout.count():
            item = self.presets_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                pass
        self._populate_presets_content(dark)

    def _populate_presets_content(self, dark: bool):
        desc = QLabel(
            "Le paquet Anki EDN est présent dans votre collection. "
            "Appliquez en un clic les réglages méthodologiques recommandés par le tutoriel officiel. "
            "Les étapes déjà conformes sont détectées automatiquement :"
        )
        desc.setWordWrap(True)
        self.presets_layout.addWidget(desc)

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
            self.presets_layout.addWidget(banner)

        # Frame with options
        frame = QFrame()
        bg_card = "#21252b" if dark else "#f8f9fa"
        border_card = "#3b4048" if dark else "#dee2e6"
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_card};
                border: 1px solid {border_card};
                border-radius: 6px;
                padding: 10px;
            }}
            QLabel {{ border: none; background: transparent; }}
            QWidget {{ border: none; background: transparent; }}
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setSpacing(8)

        # Options
        self.cb_options, row_opt = self._create_option_row(
            "Options globales AnkiCollab & AnkiWeb (mises à jour au lancement, suspension auto, sync)",
            "Active le téléchargement automatique des mises à jour au démarrage et la synchronisation continue.",
            self.statuses.get("options", {}),
            dark
        )
        frame_layout.addWidget(row_opt)

        self.cb_preset, row_pre = self._create_option_row(
            "Préréglage de révision 'Anki EDN' (FSRS 88%, cartes sœurs enfouies)",
            "Active FSRS, configure la rétention cible à 88% et enfouit les cartes sœurs.",
            self.statuses.get("preset", {}),
            dark
        )
        frame_layout.addWidget(row_pre)

        self.cb_suspend, row_sus = self._create_option_row(
            "Suspension initiale des cartes EDN (déblocage progressif item par item)",
            "Suspend les nouvelles cartes au départ. Décoché automatiquement si vous avez déjà commencé vos révisions.",
            self.statuses.get("suspend", {}),
            dark
        )
        frame_layout.addWidget(row_sus)

        self.cb_nids, row_nid = self._create_option_row(
            "Réparation des NID des cartes liées",
            "Aligne les identifiants locaux des notes pour assurer la navigation entre cartes d'un même item.",
            self.statuses.get("nids", {}),
            dark
        )
        frame_layout.addWidget(row_nid)

        self.cb_symbols, row_sym = self._create_option_row(
            "Symboles et abréviations médicales (Insert Symbols As You Type)",
            "Importe le dictionnaire raccourcis.csv (flèches, unités, abréviations) pour la saisie médicale.",
            self.statuses.get("symbols", {}),
            dark
        )
        frame_layout.addWidget(row_sym)

        self.presets_layout.addWidget(frame)
        self.presets_layout.addStretch()

        # Action Buttons
        btn_layout = QHBoxLayout()
        cancel_text = "Plus tard" if self.is_startup else "Fermer"
        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()

        accent = "#61afef" if dark else "#1971c2"
        self.apply_btn = QPushButton("Appliquer la configuration recommandée")
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent}; color: white; border: none;
                padding: 8px 18px; border-radius: 5px; font-weight: bold; font-size: 12px;
            }}
        """)
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        self.presets_layout.addLayout(btn_layout)
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
            detail_lbl = QLabel(f"<span style='font-size: 11px; color: {text_muted};'>• {detail_text}</span>")
            detail_lbl.setStyleSheet("border: none; background: transparent; padding: 2px 0;")
            detail_lbl.setContentsMargins(22, 0, 0, 0)
            detail_lbl.setWordWrap(True)
            row_layout.addWidget(detail_lbl)

        cb.toggled.connect(self._update_button_state)
        return cb, row_widget

    def _update_button_state(self):
        if not hasattr(self, "apply_btn"):
            return
        has_checked = bool(
            (hasattr(self, "cb_options") and self.cb_options.isChecked()) or
            (hasattr(self, "cb_preset") and self.cb_preset.isChecked()) or
            (hasattr(self, "cb_suspend") and self.cb_suspend.isChecked()) or
            (hasattr(self, "cb_nids") and self.cb_nids.isChecked()) or
            (hasattr(self, "cb_symbols") and self.cb_symbols.isChecked())
        )
        if has_checked:
            self.apply_btn.setText("Appliquer les réglages sélectionnés")
            self.apply_btn.setEnabled(True)
        else:
            self.apply_btn.setText("Fermer")

    def reject(self):
        self._persist_shown_flag()
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        super().reject()

    def closeEvent(self, event):
        self._persist_shown_flag()
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        super().closeEvent(event)

    def _on_cancel(self):
        self.reject()
        if self.is_startup and getattr(mw, "app", None):
            tooltip(
                "Assistant reporté. Retrouvez-le à tout moment dans Anki EDN > Rétablir les réglages du tuto.",
                period=3500
            )

    def _on_apply(self):
        has_checked = bool(
            (hasattr(self, "cb_options") and self.cb_options.isChecked()) or
            (hasattr(self, "cb_preset") and self.cb_preset.isChecked()) or
            (hasattr(self, "cb_suspend") and self.cb_suspend.isChecked()) or
            (hasattr(self, "cb_nids") and self.cb_nids.isChecked()) or
            (hasattr(self, "cb_symbols") and self.cb_symbols.isChecked())
        )
        if not has_checked:
            self.accept()
            return

        reports = []

        if hasattr(self, "cb_options") and self.cb_options.isChecked():
            ok, msg = apply_global_ankicollab_settings()
            reports.append(msg)

        if hasattr(self, "cb_preset") and self.cb_preset.isChecked():
            ok, msg = apply_edn_deck_preset(col=self.active_col)
            reports.append(msg)

        if hasattr(self, "cb_suspend") and self.cb_suspend.isChecked():
            ok, msg = suspend_initial_edn_cards(col=self.active_col)
            reports.append(msg)

        if hasattr(self, "cb_nids") and self.cb_nids.isChecked():
            ok, msg = repair_nids_and_sync(col=self.active_col)
            reports.append(msg)

        if hasattr(self, "cb_symbols") and self.cb_symbols.isChecked():
            ok, msg = apply_edn_symbols_import()
            reports.append(msg)

        try:
            set_state(stage="done")
            from .shared_menu import get_config, save_config
            shared_cfg = get_config()
            shared_cfg["setup_assistant_shown"] = True
            shared_cfg["setup_assistant_completed"] = True
            save_config(shared_cfg)
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
            shared_cfg = get_config()
            shared_cfg["setup_assistant_shown"] = True
            save_config(shared_cfg)
        except Exception:
            pass
    d = EDNSetupAssistantDialog(parent=parent or mw, is_startup=is_startup, col=col)
    d.exec()


def check_startup_assistant() -> None:
    """
    On profile open:
    Check once at installation if the tutorial setup is needed.
    Never spams update notifications at startup.
    """
    if not mw:
        return
    try:
        from .shared_menu import get_config, save_config
        shared_cfg = get_config()
        st = get_state()

        if shared_cfg.get("setup_assistant_shown", False) or shared_cfg.get("setup_assistant_completed", False) or st.get("stage") == "done":
            if st.get("stage") != "done" and deck_card_count() > 0:
                set_state(stage="done")
            return

        col = getattr(mw, "col", None)
        statuses = detect_all_setup_statuses(col=col)
        addons_st = detect_required_addons_status()
        if all(s.get("done", False) for s in statuses.values()) and addons_st.get("done", True):
            shared_cfg["setup_assistant_shown"] = True
            shared_cfg["setup_assistant_completed"] = True
            save_config(shared_cfg)
            set_state(stage="done")
            return

        timer = QTimer(mw)

        def tick():
            if mw.col is None:
                timer.stop()
            elif not mw.progress.busy() and QApplication.activeModalWidget() is None:
                timer.stop()
                sync_first_then(lambda: open_setup_assistant_dialog(parent=mw, is_startup=True))

        timer.timeout.connect(tick)
        QTimer.singleShot(3500, lambda: timer.start(1000))
    except Exception as e:
        print(f"[setup_assistant] Erreur vérification démarrage: {e}")


def init_setup_assistant_hooks() -> None:
    """Hook startup verification into profile_did_open."""
    gui_hooks.profile_did_open.append(check_startup_assistant)
