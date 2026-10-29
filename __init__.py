"""
Anki EDN Installer - Main Entry Point
Modular addon system for Anki EDN deck tools and Installer.
"""
from aqt import mw
from aqt.qt import *

from .shared_menu import register_module, register_action, get_edn_menu
from .logger import log
from . import multi_window

def init_addon():
    get_edn_menu()
    
    if register_module("fsrs_checker", "Vérificateur FSRS",
                       "Vérifie les paramètres FSRS périodiquement"):
        from .fsrs import init_fsrs
        init_fsrs()
        log("FSRS Checker module loaded.")
    
    if register_module("card_styles", "Réglages Cartes",
                       "Barre de rang A/B, pictogrammes de matière sur les cartes"):
        # Initialisation automatique gérée via profile_did_open dans shared_menu.py
        pass

    if register_module("filtered_decks", "Paquets Filtrés",
                       "Génération hiérarchique de paquets filtrés par matière et par item"):
        try:
            from .filtered_decks import init_filtered_decks, rebuild_all_edn_filtered_decks, empty_all_edn_filtered_decks, get_edn_filtered_deck_ids
            from .filtered_decks_dialog import open_filtered_decks_dialog
            init_filtered_decks()
            register_action(
                "filtered_decks",
                "Générateur de paquets filtrés...",
                open_filtered_decks_dialog,
                shortcut="Ctrl+Alt+F"
            )

            def _quick_rebuild():
                dids = get_edn_filtered_deck_ids()
                if not dids:
                    from aqt.utils import showInfo
                    showInfo("Aucun paquet filtré actif n'a été détecté sous 'EDN - Paquets Filtrés'.")
                    return
                res = rebuild_all_edn_filtered_decks()
                if mw:
                    mw.reset()
                from aqt.utils import tooltip
                count = res.get("count", 0)
                cards = res.get("total_cards", 0)
                tooltip(f"{count} paquets filtrés régénérés ({cards} cartes allouées).")

            register_action(
                "filtered_decks",
                "Régénérer les paquets filtrés",
                _quick_rebuild,
                shortcut="Ctrl+Alt+R"
            )

            def _quick_empty():
                dids = get_edn_filtered_deck_ids()
                if not dids:
                    from aqt.utils import showInfo
                    showInfo("Aucun paquet filtré actif n'a été détecté sous 'EDN - Paquets Filtrés'.")
                    return
                cnt = empty_all_edn_filtered_decks()
                if mw:
                    mw.reset()
                from aqt.utils import tooltip
                tooltip(f"{cnt} paquets filtrés vidés.")

            register_action(
                "filtered_decks",
                "Vider les paquets filtrés",
                _quick_empty,
                shortcut="Ctrl+Alt+E"
            )
            log("Filtered Decks module loaded.")
        except Exception as e:
            log(f"Erreur chargement filtered_decks: {e}")
    
    try:
        from .guide import init_guide_hooks
        init_guide_hooks()
        log("Guide module loaded.")
    except Exception as e:
        log(f"Erreur chargement guide: {e}")

    try:
        from .field_protection import init_field_protection_hooks
        init_field_protection_hooks()
        log("Field protection module loaded.")
    except Exception as e:
        log(f"Erreur chargement field_protection: {e}")

    try:
        from .setup_assistant import init_setup_assistant_hooks
        init_setup_assistant_hooks()
        log("Setup assistant module loaded.")
    except Exception as e:
        log(f"Erreur chargement setup_assistant: {e}")

    log("Anki EDN Installer loaded successfully.")

try:
    init_addon()
except Exception as e:
    print(f"Failed to load Installer: {e}")
