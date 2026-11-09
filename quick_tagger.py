# -*- coding: utf-8 -*-
"""
Anki EDN Quick Tagger
Allows adding, searching, and managing tags on the fly during review sessions
via a fast keyboard shortcut (default: 'T'), inspired by TagOnTheGo (1507758285).
"""
from __future__ import annotations

import re
from typing import List, Set, Optional, Sequence, Tuple, Callable

from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QWidget, QFrame, QCompleter, QStringListModel, Qt,
    QKeySequence, QShortcut, QApplication, QPalette
)
from aqt.reviewer import Reviewer
from aqt.utils import tooltip, showWarning
from anki.hooks import wrap
try:
    from .logger import log
    from .shared_menu import get_config, save_config, get_shortcut
except (ImportError, ValueError):
    try:
        from Anki_EDN_Installer.logger import log
        from Anki_EDN_Installer.shared_menu import get_config, save_config, get_shortcut
    except (ImportError, ValueError):
        from logger import log
        from shared_menu import get_config, save_config, get_shortcut

DEFAULT_TAG_SHORTCUT = "T"
INVALID_TAG_CHARS = set('<>"\'&\t\n\r')

SUGGESTED_EDN_TAGS = [
    "Difficile",
    "A_revoir",
    "Important",
    "Erreur_recurrente",
    "EDN::Difficulte::1",
    "EDN::Difficulte::2",
    "EDN::Difficulte::3",
]


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
            "bg_input": "#282c34",
            "border": "#3b4048",
            "border_accent": "#61afef",
            "text_main": "#abb2bf",
            "text_muted": "#7f848e",
            "accent": "#61afef",
            "accent_hover": "#528bcc",
            "pill_bg": "#2c313a",
            "pill_border": "#4b5263",
            "pill_hover": "#e06c75",
            "btn_default_bg": "#2c313a",
            "btn_default_hover": "#3b4048",
            "btn_primary_bg": "#2b5278",
            "btn_primary_hover": "#346392",
            "tooltip_bg": "#0f172a",
            "tooltip_text": "#f8fafc",
            "tooltip_border": "#334155",
        }
    return {
        "bg_dialog": "#ffffff",
        "bg_card": "#f8f9fa",
        "bg_input": "#ffffff",
        "border": "#dee2e6",
        "border_accent": "#1971c2",
        "text_main": "#212529",
        "text_muted": "#6c757d",
        "accent": "#1971c2",
        "accent_hover": "#1864ab",
        "pill_bg": "#e9ecef",
        "pill_border": "#ced4da",
        "pill_hover": "#e03131",
        "btn_default_bg": "#f1f3f5",
        "btn_default_hover": "#e9ecef",
        "btn_primary_bg": "#1971c2",
        "btn_primary_hover": "#1864ab",
        "tooltip_bg": "#feffc4",
        "tooltip_text": "#000000",
        "tooltip_border": "#cbd5e1",
    }


def clean_tag_name(tag: str) -> str:
    """Strip invalid characters and spaces from tag name."""
    tag = tag.strip().replace(" ", "_")
    for ch in INVALID_TAG_CHARS:
        tag = tag.replace(ch, "")
    return tag


class QuickTagDialog(QDialog):
    """
    Sleek, minimalist modal dialog to view and update note tags on the fly.
    Features instant autocomplete, tag pills with removal, and common presets.
    """

    def __init__(self, parent=None, note=None):
        super().__init__(parent)
        self.note = note
        self.current_tags: List[str] = list(note.tags) if note else []
        self.all_collection_tags: List[str] = []
        self.t = get_theme_palette()

        self._load_collection_tags()
        self.setup_ui()

    def _load_collection_tags(self):
        try:
            if mw and mw.col:
                self.all_collection_tags = sorted(mw.col.tags.all(), key=str.lower)
        except Exception:
            self.all_collection_tags = []

    def setup_ui(self):
        T = self.t
        self.setObjectName("quickTagDialog")
        self.setWindowTitle("Ajout d'etiquette a la volee — Anki EDN")
        self.setMinimumWidth(480)
        self.setMinimumHeight(380)

        self.setStyleSheet(f"""
            QDialog#quickTagDialog {{
                background-color: {T['bg_dialog']};
                color: {T['text_main']};
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                font-size: 13px;
            }}
            QDialog#quickTagDialog QLabel {{
                color: {T['text_main']};
                background: transparent;
            }}
            QLineEdit {{
                background-color: {T['bg_input']};
                color: {T['text_main']};
                border: 1px solid {T['border']};
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {T['border_accent']};
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
            QScrollArea {{
                border: 1px solid {T['border']};
                border-radius: 4px;
                background-color: {T['bg_card']};
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
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        header_text = "Etiquettes de la note"
        if self.note:
            header_text += f" (ID: {self.note.id})"
        header_label = QLabel(header_text)
        header_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {T['accent']};")
        layout.addWidget(header_label)

        # Input row
        input_label = QLabel("Nouvelle etiquette (Entree pour ajouter) :")
        input_label.setStyleSheet(f"color: {T['text_muted']}; font-size: 11.5px;")
        layout.addWidget(input_label)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Ex: Difficile, EDN::item-020...")
        self.completer = QCompleter(self.all_collection_tags, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.tag_input.setCompleter(self.completer)
        self.tag_input.returnPressed.connect(self.add_tag_from_input)

        add_btn = QPushButton("Ajouter")
        add_btn.clicked.connect(self.add_tag_from_input)

        input_layout.addWidget(self.tag_input)
        input_layout.addWidget(add_btn)
        layout.addLayout(input_layout)

        # Active tags area
        tags_section_label = QLabel("Etiquettes actuellement appliquees :")
        tags_section_label.setStyleSheet(f"color: {T['text_muted']}; font-size: 11.5px; margin-top: 4px;")
        layout.addWidget(tags_section_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMaximumHeight(140)

        self.pills_container = QWidget()
        self.pills_layout = QVBoxLayout(self.pills_container)
        self.pills_layout.setContentsMargins(8, 8, 8, 8)
        self.pills_layout.setSpacing(6)
        self.scroll.setWidget(self.pills_container)
        layout.addWidget(self.scroll)

        # Suggestions section - desactivees temporairement
        SHOW_SUGGESTIONS = False
        if SHOW_SUGGESTIONS and SUGGESTED_EDN_TAGS:
            sug_label = QLabel("Suggestions rapides :")
            sug_label.setStyleSheet(f"color: {T['text_muted']}; font-size: 11.5px; margin-top: 4px;")
            layout.addWidget(sug_label)
            sug_layout = QHBoxLayout()
            sug_layout.setSpacing(6)
            for sug in SUGGESTED_EDN_TAGS[:5]:
                btn = QPushButton(sug)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        font-size: 11px;
                        padding: 3px 8px;
                        background-color: {T['pill_bg']};
                        border: 1px solid {T['pill_border']};
                    }}
                    QPushButton:hover {{
                        border-color: {T['accent']};
                    }}
                """)
                btn.clicked.connect(lambda checked, s=sug: self.toggle_suggested_tag(s))
                sug_layout.addWidget(btn)
            sug_layout.addStretch()
            layout.addLayout(sug_layout)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Annuler")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Enregistrer")
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {T['btn_primary_bg']};
                color: #ffffff;
                border: 1px solid {T['btn_primary_bg']};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {T['btn_primary_hover']};
            }}
        """)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept_and_save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        self.refresh_pills()
        self.tag_input.setFocus()

    def refresh_pills(self):
        """Re-render tag badges."""
        # Clear existing
        while self.pills_layout.count():
            item = self.pills_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.current_tags:
            empty_lbl = QLabel("Aucune etiquette sur cette carte.")
            empty_lbl.setStyleSheet(f"color: {self.t['text_muted']}; font-style: italic; font-size: 12px;")
            self.pills_layout.addWidget(empty_lbl)
            return

        T = self.t
        for tag in self.current_tags:
            row = QWidget()
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(4, 2, 4, 2)
            r_layout.setSpacing(6)

            tag_lbl = QLabel(tag)
            tag_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {T['pill_bg']};
                    color: {T['text_main']};
                    border: 1px solid {T['pill_border']};
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 12px;
                }}
            """)
            r_layout.addWidget(tag_lbl)

            del_btn = QPushButton("Supprimer")
            del_btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: 11px;
                    padding: 2px 6px;
                    border: 1px solid {T['border']};
                    background: transparent;
                    color: {T['text_muted']};
                }}
                QPushButton:hover {{
                    color: {T['pill_hover']};
                    border-color: {T['pill_hover']};
                }}
            """)
            del_btn.clicked.connect(lambda checked, t=tag: self.remove_tag(t))
            r_layout.addWidget(del_btn)
            r_layout.addStretch()

            self.pills_layout.addWidget(row)

    def add_tag_from_input(self):
        raw = self.tag_input.text()
        parts = raw.split()
        for p in parts:
            clean = clean_tag_name(p)
            if clean and clean not in self.current_tags:
                self.current_tags.append(clean)
        self.tag_input.clear()
        self.refresh_pills()

    def toggle_suggested_tag(self, tag: str):
        if tag in self.current_tags:
            self.current_tags.remove(tag)
        else:
            self.current_tags.append(tag)
        self.refresh_pills()

    def remove_tag(self, tag: str):
        if tag in self.current_tags:
            self.current_tags.remove(tag)
            self.refresh_pills()

    def accept_and_save(self):
        # Also process any text currently left in input
        self.add_tag_from_input()
        if self.note and mw and mw.col:
            try:
                self.note.tags = list(dict.fromkeys(self.current_tags))
                mw.col.update_note(self.note)
                tooltip(f"Etiquettes enregistrees : {len(self.note.tags)} etiquette(s).", period=2000)
                log(f"[quick_tagger] Tags mis a jour pour note {self.note.id}: {self.note.tags}")
            except Exception as e:
                showWarning(f"Erreur lors de l'enregistrement des etiquettes: {e}")
                log(f"[quick_tagger] Erreur update note: {e}")
                return
        super().accept()


def get_quick_tag_shortcut() -> str:
    """Retrieve configured shortcut via shared_menu broker or default."""
    cfg = get_config()
    shortcuts = cfg.get("shortcuts", {})
    if "quick_tagger_reviewer" in shortcuts and shortcuts["quick_tagger_reviewer"]:
        return shortcuts["quick_tagger_reviewer"]
    if "quick_tagger" in shortcuts and shortcuts["quick_tagger"]:
        return shortcuts["quick_tagger"]
    try:
        from .shared_menu import get_shortcut
        return get_shortcut("quick_tagger_reviewer", DEFAULT_TAG_SHORTCUT)
    except Exception:
        return DEFAULT_TAG_SHORTCUT


def open_quick_tag_dialog() -> None:
    """Open quick tag dialog for the currently reviewed note."""
    if not mw or mw.state != "review":
        return
    reviewer = getattr(mw, "reviewer", None)
    if not reviewer or not reviewer.card:
        tooltip("Aucune carte en cours de revision.")
        return

    card = reviewer.card
    try:
        note = card.note()
    except Exception as e:
        log(f"[quick_tagger] Impossible de charger la note: {e}")
        return

    dialog = QuickTagDialog(mw, note=note)
    dialog.exec()


def _reviewer_shortcut_keys(reviewer: Reviewer, _old: Callable) -> Sequence[Tuple[str, Callable]]:
    """Inject quick tag shortcut into Reviewer shortcut list."""
    keys = list(_old(reviewer))
    sc = get_quick_tag_shortcut()
    if sc:
        keys.append((sc, open_quick_tag_dialog))
    return keys


def _on_reviewer_did_answer_card(reviewer: Reviewer, card: Any, ease: int) -> None:
    """Optional smart trigger for cards without any tags."""
    try:
        cfg = get_config()
        if not cfg.get("tag_on_the_go_untagged", False):
            return
        note = card.note()
        if not note.tags:
            dialog = QuickTagDialog(mw, note=note)
            dialog.exec()
    except Exception as e:
        log(f"[quick_tagger] Erreur hook did_answer: {e}")


def init_quick_tagger_hooks() -> None:
    """Initialize reviewer shortcuts and hooks for quick tagging."""
    Reviewer._shortcutKeys = wrap(Reviewer._shortcutKeys, _reviewer_shortcut_keys, "around")
    gui_hooks.reviewer_did_answer_card.append(_on_reviewer_did_answer_card)
    log("[quick_tagger] Module d'ajout d'etiquettes a la volee initialise.")
