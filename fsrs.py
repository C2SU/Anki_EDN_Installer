# -*- coding: utf-8 -*-
"""
Anki EDN FSRS Optimizer Reminder Module
Monitors FSRS configuration freshness, maintains the last optimization date,
and displays a startup reminder pop-up dialog with configurable intervals:
- Default reminder interval: 3 weeks.
- If 'optimal settings were detected last time': shortened reminder of 1 week.
- Strictly no emojis.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QRadioButton, QButtonGroup, QTimer, QApplication, QPalette, Qt
)
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

DEFAULT_INTERVAL_WEEKS = 3
OPTIMAL_DETECTED_INTERVAL_DAYS = 7


def is_dark_mode() -> bool:
    try:
        from aqt.theme import theme_manager
        if theme_manager and hasattr(theme_manager, "night_mode"):
            return bool(theme_manager.night_mode)
    except Exception:
        pass
    try:
        if mw and hasattr(mw, "theme_manager") and hasattr(mw.theme_manager, "night_mode"):
            return bool(mw.theme_manager.night_mode)
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


def get_theme_palette() -> dict:
    dark = is_dark_mode()
    if dark:
        return {
            "bg_dialog": "#1e2227",
            "bg_card": "#21252b",
            "border": "#3b4048",
            "text_main": "#abb2bf",
            "text_muted": "#7f848e",
            "accent": "#61afef",
            "btn_default_bg": "#2c313a",
            "btn_default_hover": "#3b4048",
            "btn_primary_bg": "#2b5278",
            "btn_primary_hover": "#346392",
            "badge_bg": "#282c34",
            "tooltip_bg": "#0f172a",
            "tooltip_text": "#f8fafc",
            "tooltip_border": "#334155",
        }
    return {
        "bg_dialog": "#ffffff",
        "bg_card": "#f8f9fa",
        "border": "#dee2e6",
        "text_main": "#212529",
        "text_muted": "#6c757d",
        "accent": "#1971c2",
        "btn_default_bg": "#f1f3f5",
        "btn_default_hover": "#e9ecef",
        "btn_primary_bg": "#1971c2",
        "btn_primary_hover": "#1864ab",
        "badge_bg": "#e9ecef",
        "tooltip_bg": "#feffc4",
        "tooltip_text": "#000000",
        "tooltip_border": "#cbd5e1",
    }


def get_last_fsrs_optimization_timestamp() -> Optional[float]:
    """Retrieve timestamp of last optimization from config or fallback to deck config modification time."""
    cfg = get_config()
    ts = cfg.get("fsrs_last_optimization_time")
    if ts and isinstance(ts, (int, float)) and ts > 0:
        return float(ts)

    # Fallback to inspecting deck configs in collection
    if mw and mw.col:
        try:
            mods = []
            for conf in mw.col.decks.all_config():
                # Check for FSRS parameters presence
                has_fsrs = bool(
                    conf.get("fsrsWeights") or conf.get("fsrsParams5") or conf.get("fsrsParams6")
                )
                if has_fsrs and "mod" in conf:
                    mods.append(float(conf["mod"]))
            if mods:
                return max(mods)
        except Exception as e:
            log(f"[fsrs] Erreur lecture config decks: {e}")
    return None


def format_timestamp(ts: Optional[float]) -> str:
    """Format timestamp into readable date string."""
    if not ts:
        return "Aucune date enregistree"
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d/%m/%Y a %H:%M")
    except Exception:
        return "Date invalide"


def get_effective_interval_days() -> Tuple[int, str]:
    """
    Compute effective interval in days and descriptive label based on
    whether the last run detected optimal settings.
    """
    cfg = get_config()
    last_was_optimal = bool(cfg.get("fsrs_last_was_optimal", False))

    if last_was_optimal:
        return OPTIMAL_DETECTED_INTERVAL_DAYS, "1 semaine (reglages optimaux detectes la derniere fois)"

    weeks = int(cfg.get("fsrs_reminder_interval_weeks", DEFAULT_INTERVAL_WEEKS))
    if weeks < 1:
        weeks = 1
    return weeks * 7, f"{weeks} semaines"


def record_optimization(was_optimal: bool = False, custom_time: Optional[float] = None) -> None:
    """Save latest optimization timestamp and optimal state."""
    cfg = get_config()
    now = custom_time if custom_time is not None else time.time()
    cfg["fsrs_last_optimization_time"] = now
    cfg["fsrs_last_was_optimal"] = bool(was_optimal)
    cfg["fsrs_snooze_until"] = 0  # Clear snooze
    save_config(cfg)
    log(f"[fsrs] Optimisation enregistree : ts={now}, was_optimal={was_optimal}")


class FSRSReminderDialog(QDialog):
    """
    Startup modal dialog prompting the user to optimize their FSRS scheduler parameters,
    showing last optimization date and providing direct action triggers.
    """

    def __init__(self, parent=None, stale_configs: Optional[List[str]] = None):
        super().__init__(parent)
        self.stale_configs = stale_configs or []
        self.t = get_theme_palette()
        self.setup_ui()

    def setup_ui(self):
        T = self.t
        self.setObjectName("fsrsReminderDialog")
        self.setWindowTitle("Rappel FSRS — Optimisation des parametres")
        self.setMinimumWidth(520)

        self.setStyleSheet(f"""
            QDialog#fsrsReminderDialog {{
                background-color: {T['bg_dialog']};
                color: {T['text_main']};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 13px;
            }}
            QDialog#fsrsReminderDialog QLabel {{
                color: {T['text_main']};
                background: transparent;
            }}
            QFrame.card {{
                background-color: {T['bg_card']};
                border: 1px solid {T['border']};
                border-radius: 6px;
                padding: 12px;
            }}
            QPushButton {{
                background-color: {T['btn_default_bg']};
                color: {T['text_main']};
                border: 1px solid {T['border']};
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 12.5px;
            }}
            QPushButton:hover {{
                background-color: {T['btn_default_hover']};
            }}
            QRadioButton {{
                color: {T['text_main']};
                font-size: 12.5px;
                padding: 3px 0;
            }}
            QToolTip, CustomLabel, QLabel[customTooltip="true"] {{
                background-color: {T['tooltip_bg']};
                color: {T['tooltip_text']};
                border: 1px solid {T['tooltip_border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title
        title_label = QLabel("Optimisation des parametres FSRS recommandee")
        title_label.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {T['accent']};")
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Pour adapter l'algorithme a votre historique recent de revisions et "
            "optimiser la precision du calcul des intervalles, il est recommande de recalculer "
            "periodiquement vos poids FSRS dans les options de paquet."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {T['text_muted']}; line-height: 1.4;")
        layout.addWidget(desc_label)

        # Status Card
        card = QFrame()
        card.setProperty("class", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        last_ts = get_last_fsrs_optimization_timestamp()
        last_date_str = format_timestamp(last_ts)

        elapsed_str = ""
        if last_ts:
            days_ago = int((time.time() - last_ts) / 86400)
            elapsed_str = f" (il y a {days_ago} jour{'s' if days_ago > 1 else ''})"

        interval_days, interval_label = get_effective_interval_days()

        card_layout.addWidget(
            QLabel(f"<b>Derniere optimisation :</b> {last_date_str}{elapsed_str}")
        )
        card_layout.addWidget(
            QLabel(f"<b>Frequence de rappel configuree :</b> {interval_label}")
        )

        cfg = get_config()
        if cfg.get("fsrs_last_was_optimal", False):
            info_sub = QLabel("Note : Le dernier diagnostic indiquait que les parametres etaient deja optimaux. Le rappel est donc rapproche a 1 semaine.")
            info_sub.setStyleSheet(f"color: {T['text_muted']}; font-size: 11.5px; font-style: italic;")
            card_layout.addWidget(info_sub)

        layout.addWidget(card)

        # Outcome selection on marking
        mark_box = QFrame()
        mark_box.setProperty("class", "card")
        mark_layout = QVBoxLayout(mark_box)
        mark_layout.setContentsMargins(12, 10, 12, 10)
        mark_layout.setSpacing(6)

        mark_title = QLabel("Enregistrer le resultat d'une optimisation :")
        mark_title.setStyleSheet(f"font-weight: 600; color: {T['text_main']};")
        mark_layout.addWidget(mark_title)

        self.btn_group = QButtonGroup(self)
        self.radio_updated = QRadioButton("Parametres mis a jour (nouveaux poids FSRS) -> prochain rappel dans 3 semaines")
        self.radio_optimal = QRadioButton("Reglages optimaux detectes (deja optimaux) -> prochain rappel dans 1 semaine")

        self.btn_group.addButton(self.radio_updated, 1)
        self.btn_group.addButton(self.radio_optimal, 2)

        if cfg.get("fsrs_last_was_optimal", False):
            self.radio_optimal.setChecked(True)
        else:
            self.radio_updated.setChecked(True)

        mark_layout.addWidget(self.radio_updated)
        mark_layout.addWidget(self.radio_optimal)

        mark_action_btn = QPushButton("Marquer comme optimise aujourd'hui")
        mark_action_btn.clicked.connect(self.on_mark_optimized)
        mark_layout.addWidget(mark_action_btn)

        layout.addWidget(mark_box)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        open_options_btn = QPushButton("Ouvrir les options du paquet...")
        open_options_btn.clicked.connect(self.on_open_deck_options)
        btn_layout.addWidget(open_options_btn)

        snooze_btn = QPushButton("Rappeler dans 3 jours")
        snooze_btn.clicked.connect(self.on_snooze)
        btn_layout.addWidget(snooze_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def on_open_deck_options(self):
        """Open Anki's Deck Options dialog."""
        try:
            if mw:
                # Open options of current deck or EDN deck
                did = mw.col.decks.selected()
                mw.onDeckOptions(did)
        except Exception as e:
            log(f"[fsrs] Erreur ouverture options: {e}")

    def on_mark_optimized(self):
        was_optimal = self.radio_optimal.isChecked()
        record_optimization(was_optimal=was_optimal)
        delay_msg = "1 semaine" if was_optimal else "3 semaines"
        tooltip(f"Date d'optimisation actualisee. Prochain rappel dans {delay_msg}.", period=3000)
        self.accept()

    def on_snooze(self):
        cfg = get_config()
        cfg["fsrs_snooze_until"] = time.time() + (3 * 86400)
        save_config(cfg)
        tooltip("Rappel FSRS reporte de 3 jours.", period=2000)
        self.accept()


def check_fsrs_status() -> None:
    """
    Checks if FSRS weights need re-optimization according to configured interval.
    Displays a modal pop-up at startup when overdue.
    """
    if not mw or not mw.col:
        return

    cfg = get_config()
    # Check if FSRS module is enabled
    modules = cfg.get("modules", {})
    if not modules.get("fsrs_checker", True):
        return

    now = time.time()

    # Check snooze
    snooze_until = float(cfg.get("fsrs_snooze_until", 0))
    if now < snooze_until:
        return

    last_ts = get_last_fsrs_optimization_timestamp()
    interval_days, interval_label = get_effective_interval_days()
    limit_seconds = interval_days * 86400

    if last_ts is None:
        # No recorded optimization date: check deck config mod times
        stale_configs = []
        try:
            for conf in mw.col.decks.all_config():
                mod = float(conf.get("mod", 0))
                if (now - mod) > limit_seconds:
                    stale_configs.append(conf.get("name", "Inconnu"))
        except Exception:
            pass
        if stale_configs:
            _show_reminder_popup(stale_configs)
        return

    # Check elapsed time since last recorded optimization
    if (now - last_ts) > limit_seconds:
        _show_reminder_popup([])


def _show_reminder_popup(stale_configs: List[str]) -> None:
    """Show the FSRS reminder pop-up dialog with a brief safety delay."""
    def launch():
        try:
            if mw and getattr(mw, "col", None) is not None:
                dialog = FSRSReminderDialog(mw, stale_configs=stale_configs)
                dialog.exec()
        except Exception as e:
            log(f"[fsrs] Erreur affichage dialogue rappel: {e}")

    QTimer.singleShot(1500, launch)


def init_fsrs() -> None:
    """Initialize profile open hook for FSRS status check."""
    gui_hooks.profile_did_open.append(check_fsrs_status)
    log("[fsrs] Module de surveillance FSRS initialise.")
