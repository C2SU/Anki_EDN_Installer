"""
Dialogue graphique pour le générateur de paquets filtrés Anki EDN.
Design sobre, minimaliste et sans emojis, conforme aux règles globales.
"""

from typing import Dict, Any, List, Optional, Tuple
from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, showWarning, askUser, tooltip

from .filtered_decks import (
    ROOT_DECK_NAME,
    normalize_tag_key,
    analyze_edn_curriculum,
    generate_filtered_hierarchy,
    empty_all_edn_filtered_decks,
    rebuild_all_edn_filtered_decks,
    delete_all_edn_filtered_decks,
    get_edn_filtered_deck_ids,
    get_edn_deck_and_config,
    sync_hierarchy_deck_options,
    load_filtered_decks_settings,
    save_filtered_decks_settings
)
from .logger import log, log_error


class CurriculumTreeWidgetItem(QTreeWidgetItem):
    """Élément d'arborescence pour spécialités et items qualifiés avec tri naturel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_specialty: bool = True
        self.item_tag: str = ""
        self.spec_cards: int = 0

    def __lt__(self, other: "QTreeWidgetItem") -> bool:
        tree = self.treeWidget()
        col = tree.sortColumn() if tree else 0
        val1 = self.data(col, Qt.ItemDataRole.UserRole)
        val2 = other.data(col, Qt.ItemDataRole.UserRole)
        if val1 is not None and val2 is not None:
            try:
                return val1 < val2
            except TypeError:
                pass
        return super().__lt__(other)



def get_theme_colors(is_dark: bool) -> dict:
    """Retourne la palette de couleurs conforme aux thèmes clair et sombre d'Anki."""
    if is_dark:
        return {
            "is_dark": True,
            "bg_window": "#1e1e20",
            "bg_card": "#26262b",
            "bg_subtle": "#2f3137",
            "bg_hover": "#373a42",
            "text_primary": "#f3f4f6",
            "text_secondary": "#9ca3af",
            "text_muted": "#6b7280",
            "border": "#3b3e47",
            "border_subtle": "#30323a",
            "accent": "#388bfd",
            "accent_hover": "#58a6ff",
            "accent_subtle": "#162740",
            "accent_text": "#ffffff",
            "danger": "#f87171",
            "danger_bg": "#391b1e",
            "danger_border": "#5c2428",
            "selection_bg": "#1c385c",
            "selection_text": "#79b8ff",
            "focus_ring": "#388bfd",
            "pill_bg": "#253346",
            "pill_text": "#58a6ff",
            "pill_border": "#314563",
        }
    else:
        return {
            "is_dark": False,
            "bg_window": "#f8fafc",
            "bg_card": "#ffffff",
            "bg_subtle": "#f1f5f9",
            "bg_hover": "#e2e8f0",
            "text_primary": "#0f172a",
            "text_secondary": "#475569",
            "text_muted": "#94a3b8",
            "border": "#cbd5e1",
            "border_subtle": "#f1f5f9",
            "accent": "#0969da",
            "accent_hover": "#0854ad",
            "accent_subtle": "#eff6ff",
            "accent_text": "#ffffff",
            "danger": "#dc2626",
            "danger_bg": "#fef2f2",
            "danger_border": "#fecaca",
            "selection_bg": "#eff6ff",
            "selection_text": "#0969da",
            "focus_ring": "#0969da",
            "pill_bg": "#f0f7ff",
            "pill_text": "#0969da",
            "pill_border": "#bae6fd",
        }


def build_dialog_stylesheet(c: dict) -> str:
    """Génère la feuille de style QSS adaptative et sans slop."""
    return f"""
    QDialog {{
        background-color: {c['bg_window']};
        color: {c['text_primary']};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
    }}
    QLabel {{
        color: {c['text_primary']};
        background: transparent;
    }}
    QGroupBox {{
        background-color: {c['bg_card']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        margin-top: 14px;
        padding: 14px;
        padding-top: 18px;
        color: {c['text_primary']};
        font-weight: 600;
        font-size: 13px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {c['accent']};
        font-weight: 600;
    }}
    QTreeWidget {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 2px;
        outline: none;
    }}
    QTreeWidget::item {{
        padding: 6px 4px;
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QTreeWidget::item:hover {{
        background-color: {c['bg_subtle']};
    }}
    QTreeWidget::item:selected {{
        background-color: {c['selection_bg']};
        color: {c['selection_text']};
    }}
    QHeaderView::section {{
        background-color: {c['bg_subtle']};
        color: {c['text_secondary']};
        padding: 6px 10px;
        border: none;
        border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']};
        font-weight: 600;
        font-size: 12px;
    }}
    QLineEdit {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 20px;
        selection-background-color: {c['selection_bg']};
        selection-color: {c['selection_text']};
    }}
    QLineEdit:focus {{
        border: 1px solid {c['focus_ring']};
    }}
    QComboBox, QSpinBox {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 10px;
        min-height: 20px;
    }}
    QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {c['focus_ring']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        selection-background-color: {c['selection_bg']};
        selection-color: {c['selection_text']};
    }}
    QRadioButton, QCheckBox {{
        color: {c['text_primary']};
        spacing: 8px;
        background: transparent;
    }}
    QRadioButton::indicator, QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}
    QPushButton {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
        font-size: 12.5px;
    }}
    QPushButton:hover {{
        background-color: {c['bg_subtle']};
        border-color: {c['border']};
    }}
    QPushButton:pressed {{
        background-color: {c['bg_hover']};
    }}
    QPushButton#ToolBtn {{
        padding: 4px 10px;
        font-size: 11.5px;
        background-color: {c['bg_subtle']};
    }}
    QPushButton#ToolBtn:hover {{
        background-color: {c['bg_hover']};
    }}
    QPushButton#PrimaryButton {{
        background-color: {c['accent']};
        color: {c['accent_text']};
        border: 1px solid {c['accent']};
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
    }}
    QPushButton#DangerButton {{
        background-color: {c['danger_bg']};
        color: {c['danger']};
        border: 1px solid {c['danger_border']};
    }}
    QPushButton#DangerButton:hover {{
        background-color: {c['danger']};
        color: #ffffff;
    }}
    QProgressBar {{
        background-color: {c['bg_subtle']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        text-align: center;
        color: {c['text_primary']};
    }}
    QProgressBar::chunk {{
        background-color: {c['accent']};
        border-radius: 5px;
    }}
    """


class FilteredDecksDialog(QDialog):
    """Dialogue de configuration et génération des paquets filtrés EDN."""

    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Générateur de Paquets Filtrés - Anki EDN")
        self.resize(860, 780)
        self.setMinimumSize(780, 640)
        self.curriculum_data = {}
        self.specialty_items: Dict[str, CurriculumTreeWidgetItem] = {}
        self._updating_checks = False
        self._is_first_load = True

        self.saved_settings = load_filtered_decks_settings()
        self.setup_ui()
        self.apply_saved_ui_settings()
        self.load_data()

    def is_dark_mode(self) -> bool:
        """Détecte si l'interface d'Anki est en mode nuit / sombre."""
        try:
            from aqt.theme import theme_manager
            if theme_manager and hasattr(theme_manager, "night_mode"):
                return bool(theme_manager.night_mode)
        except Exception:
            pass
        try:
            if mw and hasattr(mw, "pm") and hasattr(mw.pm, "night_mode"):
                return bool(mw.pm.night_mode())
        except Exception:
            pass
        app = QApplication.instance()
        pal = self.palette() if self else (app.palette() if app else None)
        if pal:
            return pal.color(pal.ColorRole.Window).lightness() < 128
        return False

    def update_theme(self, force: bool = False):
        """Applique dynamiquement la palette de couleurs clair/sombre (avec verrou anti-réentrance)."""
        if getattr(self, "_updating_theme", False):
            return
        is_dark = self.is_dark_mode()
        if not force and hasattr(self, "_current_is_dark") and self._current_is_dark == is_dark:
            return
        self._updating_theme = True
        try:
            self._current_is_dark = is_dark
            c = get_theme_colors(is_dark)
            self.setStyleSheet(build_dialog_stylesheet(c))

            if hasattr(self, "title_label"):
                self.title_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {c['accent']};")
            if hasattr(self, "desc_label"):
                self.desc_label.setStyleSheet(f"color: {c['text_secondary']}; font-size: 12px; line-height: 1.4;")
            if hasattr(self, "preset_info_label"):
                self.preset_info_label.setStyleSheet(
                    f"background: {c['pill_bg']}; color: {c['pill_text']}; border: 1px solid {c['pill_border']}; "
                    f"border-radius: 4px; padding: 4px 8px; font-size: 11.5px; font-weight: 600;"
                )
            if hasattr(self, "summary_label"):
                self.summary_label.setStyleSheet(f"color: {c['text_secondary']}; font-weight: 500; font-size: 12px; padding: 2px 0;")
        finally:
            self._updating_theme = False

    def changeEvent(self, event: QEvent):
        """Met à jour le thème instantanément si la palette de l'application change."""
        if not getattr(self, "_updating_theme", False):
            if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
                self.update_theme()
        super().changeEvent(event)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # ── En-tête sobre ──
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        
        header_top_row = QHBoxLayout()
        self.title_label = QLabel("Générateur de Paquets Filtrés - Anki EDN")
        header_top_row.addWidget(self.title_label)
        header_top_row.addStretch()
        
        self.preset_info_label = QLabel()
        header_top_row.addWidget(self.preset_info_label)
        header_layout.addLayout(header_top_row)

        self.desc_label = QLabel(
            "Création hiérarchique automatisée de paquets filtrés par discipline et par item médical.\n"
            "Chaque matière dispose de ses sous-paquets d'items qualifiés, compatibles avec AnkiCollab."
        )
        header_layout.addWidget(self.desc_label)
        main_layout.addLayout(header_layout)

        # ── Disciplines et matières à générer ──
        tree_group = QGroupBox("Disciplines et matières à générer")
        tree_layout = QVBoxLayout(tree_group)
        tree_layout.setSpacing(10)

        # Barre de recherche et filtre rapide
        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)

        search_label = QLabel("Rechercher :")
        search_bar.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filtrer par matière ou par item (ex: Cardio, HTA, 224)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        search_bar.addWidget(self.search_input)

        self.filter_only_selected_cb = QCheckBox("Sélection uniquement")
        self.filter_only_selected_cb.setToolTip("Masquer les disciplines et items non cochés")
        self.filter_only_selected_cb.toggled.connect(self.on_filter_selected_toggled)
        search_bar.addWidget(self.filter_only_selected_cb)

        tree_layout.addLayout(search_bar)

        # Barre d'actions rapides et réglages
        action_bar = QHBoxLayout()
        action_bar.setSpacing(8)

        check_all_btn = QPushButton("Tout cocher")
        check_all_btn.setObjectName("ToolBtn")
        check_all_btn.clicked.connect(self.on_check_all_clicked)
        action_bar.addWidget(check_all_btn)

        uncheck_all_btn = QPushButton("Tout décocher")
        uncheck_all_btn.setObjectName("ToolBtn")
        uncheck_all_btn.clicked.connect(self.on_uncheck_all_clicked)
        action_bar.addWidget(uncheck_all_btn)

        expand_all_btn = QPushButton("Tout développer")
        expand_all_btn.setObjectName("ToolBtn")
        expand_all_btn.clicked.connect(lambda: self.tree_widget.expandAll())
        action_bar.addWidget(expand_all_btn)

        collapse_all_btn = QPushButton("Tout réduire")
        collapse_all_btn.setObjectName("ToolBtn")
        collapse_all_btn.clicked.connect(lambda: self.tree_widget.collapseAll())
        action_bar.addWidget(collapse_all_btn)

        action_bar.addStretch()

        threshold_label = QLabel("Seuil d'attribution :")
        action_bar.addWidget(threshold_label)
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(10, 90)
        self.threshold_spin.setSuffix(" %")
        self.threshold_spin.setValue(40)
        self.threshold_spin.valueChanged.connect(self.on_threshold_changed)
        action_bar.addWidget(self.threshold_spin)

        tree_layout.addLayout(action_bar)

        # Arborescence hiérarchique (Discipline -> Items)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Discipline / Item qualifié", "Items / Qualification", "Cartes estimées"])
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.setSortingEnabled(True)
        self.tree_widget.setIndentation(20)
        self.tree_widget.setAnimated(True)
        self.tree_widget.itemChanged.connect(self.on_item_changed)
        tree_layout.addWidget(self.tree_widget, 1)

        # Indicateur dynamique de sélection
        self.summary_label = QLabel("Aucune discipline sélectionnée")
        tree_layout.addWidget(self.summary_label)

        main_layout.addWidget(tree_group, 1)

        # ── Options de filtrage ──
        options_group = QGroupBox("Paramètres de filtrage et d'échéance")
        options_layout = QGridLayout(options_group)
        options_layout.setHorizontalSpacing(16)
        options_layout.setVerticalSpacing(10)

        # Scope : Volet matière vs Item complet
        scope_label = QLabel("Périmètre des sous-paquets :")
        scope_label.setStyleSheet("font-weight: 600;")
        options_layout.addWidget(scope_label, 0, 0)

        scope_radios_layout = QHBoxLayout()
        scope_radios_layout.setSpacing(14)
        self.radio_scope_matiere = QRadioButton("Volet matière de l'item seul (Recommandé)")
        self.radio_scope_matiere.setChecked(True)
        self.radio_scope_item = QRadioButton("Item complet (toutes les cartes de l'item)")
        scope_radios_layout.addWidget(self.radio_scope_matiere)
        scope_radios_layout.addWidget(self.radio_scope_item)
        scope_radios_layout.addStretch()
        options_layout.addLayout(scope_radios_layout, 0, 1)

        # Filtre d'échéance / statut
        status_label = QLabel("État des cartes :")
        status_label.setStyleSheet("font-weight: 600;")
        options_layout.addWidget(status_label, 1, 0)

        self.status_combo = QComboBox()
        self.status_combo.addItem("Cartes à faire aujourd'hui : Dues + Bleues/Nouvelles (Recommandé)", "due_and_new")
        self.status_combo.addItem("Toutes les cartes (Bleues + Révisions, sans restriction)", "all")
        self.status_combo.addItem("Uniquement les révisions du jour (Dues)", "due_only")
        self.status_combo.addItem("Uniquement les nouvelles cartes (Bleues)", "new_only")
        options_layout.addWidget(self.status_combo, 1, 1)

        # Rangs A / B
        rank_label = QLabel("Objectifs de connaissances :")
        rank_label.setStyleSheet("font-weight: 600;")
        options_layout.addWidget(rank_label, 2, 0)

        self.rank_combo = QComboBox()
        self.rank_combo.addItem("Toutes les cartes (Rang A et Rang B)", "all")
        self.rank_combo.addItem("Rang A uniquement (Connaissances indispensables)", "A")
        self.rank_combo.addItem("Rang B uniquement (Connaissances approfondies)", "B")
        options_layout.addWidget(self.rank_combo, 2, 1)

        # Ordre de révision des cartes
        order_label = QLabel("Ordre des cartes :")
        order_label.setStyleSheet("font-weight: 600;")
        options_layout.addWidget(order_label, 3, 0)

        self.order_combo = QComboBox()
        self.order_combo.addItem("Hériter du deck EDN principal (Recommandé)", "inherit")
        self.order_combo.addItem("Ordre d'échéance (Cartes dues en premier)", 6)
        self.order_combo.addItem("Ordre d'ajout (Chronologique / Date de création)", 5)
        self.order_combo.addItem("Aléatoire (Mélange complet)", 1)
        self.order_combo.addItem("Retard relatif (Priorité aux retards FSRS)", 10)
        self.order_combo.addItem("Plus ancien révisé en premier", 0)
        self.order_combo.addItem("Intervalles croissants", 2)
        self.order_combo.addItem("Intervalles décroissants", 3)
        options_layout.addWidget(self.order_combo, 3, 1)

        # Cases à cocher FSRS et Vidage synchro
        extra_checks_layout = QHBoxLayout()
        extra_checks_layout.setSpacing(20)

        self.resched_checkbox = QCheckBox("Rééchelonner selon les réponses (FSRS actif)")
        self.resched_checkbox.setChecked(True)
        extra_checks_layout.addWidget(self.resched_checkbox)

        self.auto_sync_checkbox = QCheckBox("Protection AnkiCollab (Vidage automatique avant synchronisation)")
        self.auto_sync_checkbox.setChecked(False)
        extra_checks_layout.addWidget(self.auto_sync_checkbox)
        extra_checks_layout.addStretch()

        options_layout.addLayout(extra_checks_layout, 4, 0, 1, 2)
        main_layout.addWidget(options_group)

        # ── Barre de progression (masquée par défaut) ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ── Boutons d'action inférieurs ──
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.empty_btn = QPushButton("Vider les paquets")
        self.empty_btn.setToolTip("Restaure toutes les cartes dans le paquet Anki EDN sans supprimer les filtres.")
        self.empty_btn.clicked.connect(self.on_empty_clicked)
        bottom_layout.addWidget(self.empty_btn)

        self.rebuild_btn = QPushButton("Régénérer les paquets")
        self.rebuild_btn.setToolTip("Reconstruit et réattribue les cartes dans tous les paquets filtrés existants sous 'EDN - Paquets Filtrés'.")
        self.rebuild_btn.clicked.connect(self.on_rebuild_clicked)
        bottom_layout.addWidget(self.rebuild_btn)

        self.delete_btn = QPushButton("Supprimer l'arborescence")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.setToolTip("Vide les paquets et supprime complètement l'arborescence EDN - Paquets Filtrés.")
        self.delete_btn.clicked.connect(self.on_delete_clicked)
        bottom_layout.addWidget(self.delete_btn)

        bottom_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(close_btn)

        self.generate_btn = QPushButton("Générer les paquets filtrés")
        self.generate_btn.setObjectName("PrimaryButton")
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        bottom_layout.addWidget(self.generate_btn)

        main_layout.addLayout(bottom_layout)
        
        # Application initiale du thème adaptatif
        self.update_theme()

    def apply_saved_ui_settings(self):
        """Restaure les options de filtrage et d'échéance depuis les derniers réglages utilisateur."""
        if not self.saved_settings:
            return

        # Seuil d'attribution
        threshold = self.saved_settings.get("threshold")
        if threshold is not None and isinstance(threshold, (int, float)):
            self.threshold_spin.blockSignals(True)
            self.threshold_spin.setValue(int(threshold))
            self.threshold_spin.blockSignals(False)

        # Périmètre (Scope)
        scope = self.saved_settings.get("scope", "volet_matiere")
        if scope == "item_complet":
            self.radio_scope_item.setChecked(True)
        else:
            self.radio_scope_matiere.setChecked(True)

        # État des cartes
        card_filter = self.saved_settings.get("card_filter")
        if card_filter:
            idx = self.status_combo.findData(card_filter)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

        # Rangs A / B
        rank_filter = self.saved_settings.get("rank_filter")
        if rank_filter:
            idx = self.rank_combo.findData(rank_filter)
            if idx >= 0:
                self.rank_combo.setCurrentIndex(idx)

        # Ordre des cartes
        order_val = self.saved_settings.get("order")
        if order_val is not None:
            idx = self.order_combo.findData(order_val)
            if idx >= 0:
                self.order_combo.setCurrentIndex(idx)

        # FSRS rééchelonnement
        resched = self.saved_settings.get("resched")
        if resched is not None:
            self.resched_checkbox.setChecked(bool(resched))

        # Protection AnkiCollab
        auto_sync = self.saved_settings.get("auto_sync")
        if auto_sync is not None:
            self.auto_sync_checkbox.setChecked(bool(auto_sync))

        # Filtre sélection uniquement
        filter_selected = self.saved_settings.get("filter_only_selected")
        if filter_selected is not None:
            self.filter_only_selected_cb.setChecked(bool(filter_selected))

    def load_data(self):
        """Charge l'analyse du curriculum EDN et construit l'arborescence."""
        # Détection et affichage des options héritées du deck principal EDN
        try:
            _, edn_conf_id, edn_conf = get_edn_deck_and_config()
            if edn_conf:
                preset_name = edn_conf.get("name", "Par défaut")
                retention_str = ""
                if "desiredRetention" in edn_conf:
                    retention_pct = int(edn_conf["desiredRetention"] * 100)
                    retention_str = f" • FSRS Rétention {retention_pct}%"
                rev_limit = edn_conf.get("rev", {}).get("perDay", 9999)
                self.preset_info_label.setText(
                    f"Options de révision héritées : Preset '{preset_name}'{retention_str} • Rév/jour : {rev_limit}"
                )
            else:
                self.preset_info_label.setText("Options de révision : Configuration par défaut")
            # Harmonisation proactive si des paquets conteneurs existent déjà
            sync_hierarchy_deck_options()
        except Exception as e:
            log_error(f"Erreur chargement options EDN: {e}")

        # Sauvegarde des sélections actuelles pour restauration si changement de seuil
        prev_specs, prev_items = self.get_selected_data() if self.specialty_items else ([], {})

        # Si premier chargement, restaurer les sélections sauvegardées
        if self._is_first_load:
            if not prev_items and self.saved_settings.get("selected_items"):
                prev_items = self.saved_settings.get("selected_items", {})
            fully_checked_set = set(self.saved_settings.get("fully_checked_specs", []))
        else:
            fully_checked_set = set()

        self.tree_widget.setSortingEnabled(False)
        self.tree_widget.clear()
        self.specialty_items.clear()

        threshold = float(self.threshold_spin.value())
        self.curriculum_data = analyze_edn_curriculum(threshold_pct=threshold)
        specialties = self.curriculum_data.get("specialties", {})

        sorted_specs = sorted(specialties.keys())
        self._updating_checks = True

        try:
            for sp in sorted_specs:
                data = specialties[sp]

                # Élément parent (Discipline)
                parent = CurriculumTreeWidgetItem(self.tree_widget)
                parent.is_specialty = True
                parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                parent.setText(0, sp)
                parent.setData(0, Qt.ItemDataRole.UserRole, sp)
                parent.setText(1, f"{data['item_count']} items")
                parent.setData(1, Qt.ItemDataRole.UserRole, data['item_count'])
                parent.setText(2, f"{data['total_cards']} cartes")
                parent.setData(2, Qt.ItemDataRole.UserRole, data['total_cards'])

                # Style texte renforcé pour les disciplines
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                parent.setFont(1, font)
                parent.setFont(2, font)

                # Éléments enfants (Items qualifiés)
                for it in data["items"]:
                    child = CurriculumTreeWidgetItem(parent)
                    child.is_specialty = False
                    child.item_tag = it["tag"]
                    child.spec_cards = it["spec_cards"]
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    child.setText(0, it["label"])
                    child.setData(0, Qt.ItemDataRole.UserRole, (it["item_num"], it["label"]))
                    child.setText(1, f"{it['pct']:.0f} %")
                    child.setData(1, Qt.ItemDataRole.UserRole, it["pct"])
                    child.setText(2, f"{it['spec_cards']} cartes")
                    child.setData(2, Qt.ItemDataRole.UserRole, it["spec_cards"])

                    # Nuance visuelle sobre pour les lignes enfants
                    child.setForeground(0, QColor("#a6adc8"))
                    child.setForeground(1, QColor("#a6adc8"))
                    child.setForeground(2, QColor("#a6adc8"))

                self.specialty_items[sp] = parent

            # Restauration des sélections si présentes
            if prev_items or fully_checked_set:
                for sp, target_tags in prev_items.items():
                    if sp in self.specialty_items:
                        parent = self.specialty_items[sp]
                        target_set = set(target_tags) if target_tags else set()
                        is_fully = (sp in fully_checked_set)
                        checked_count = 0
                        total_count = parent.childCount()
                        for i in range(total_count):
                            child = parent.child(i)
                            if is_fully or (child.item_tag in target_set):
                                child.setCheckState(0, Qt.CheckState.Checked)
                                checked_count += 1
                        if checked_count == total_count and total_count > 0:
                            parent.setCheckState(0, Qt.CheckState.Checked)
                        elif checked_count > 0:
                            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

                for sp in fully_checked_set:
                    if sp in self.specialty_items and sp not in prev_items:
                        parent = self.specialty_items[sp]
                        total_count = parent.childCount()
                        for i in range(total_count):
                            parent.child(i).setCheckState(0, Qt.CheckState.Checked)
                        if total_count > 0:
                            parent.setCheckState(0, Qt.CheckState.Checked)

        finally:
            self._updating_checks = False
            self._is_first_load = False

        self.tree_widget.setSortingEnabled(True)
        self.tree_widget.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.update_selection_summary()
        self.apply_filter()

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Synchronise l'état des cases à cocher entre disciplines et items."""
        if column != 0 or self._updating_checks:
            return

        self._updating_checks = True
        try:
            parent = item.parent()
            if parent is None:
                # Modification au niveau d'une discipline parente
                state = item.checkState(0)
                if state in (Qt.CheckState.Checked, Qt.CheckState.Unchecked):
                    for i in range(item.childCount()):
                        item.child(i).setCheckState(0, state)
            else:
                # Modification au niveau d'un item enfant
                checked_count = 0
                total = parent.childCount()
                for i in range(total):
                    if parent.child(i).checkState(0) == Qt.CheckState.Checked:
                        checked_count += 1

                if checked_count == 0:
                    parent.setCheckState(0, Qt.CheckState.Unchecked)
                elif checked_count == total:
                    parent.setCheckState(0, Qt.CheckState.Checked)
                else:
                    parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
        finally:
            self._updating_checks = False

        self.update_selection_summary()
        if self.filter_only_selected_cb.isChecked():
            self.apply_filter()

    def on_check_all_clicked(self):
        """Coche toutes les disciplines visibles et leurs items."""
        self._updating_checks = True
        try:
            for parent in self.specialty_items.values():
                if not parent.isHidden():
                    parent.setCheckState(0, Qt.CheckState.Checked)
                    for i in range(parent.childCount()):
                        if not parent.child(i).isHidden():
                            parent.child(i).setCheckState(0, Qt.CheckState.Checked)
        finally:
            self._updating_checks = False
        self.update_selection_summary()

    def on_uncheck_all_clicked(self):
        """Décoche l'intégralité des disciplines et items."""
        self._updating_checks = True
        try:
            for parent in self.specialty_items.values():
                parent.setCheckState(0, Qt.CheckState.Unchecked)
                for i in range(parent.childCount()):
                    parent.child(i).setCheckState(0, Qt.CheckState.Unchecked)
        finally:
            self._updating_checks = False
        self.update_selection_summary()
        if self.filter_only_selected_cb.isChecked():
            self.apply_filter()

    def on_search_text_changed(self, text: str):
        """Déclenche le filtrage textuel dynamique lors de la frappe."""
        self.apply_filter()

    def on_filter_selected_toggled(self, checked: bool):
        """Active ou désactive l'affichage exclusif des éléments cochés."""
        self.apply_filter()

    def apply_filter(self):
        """Filtre l'arborescence selon la recherche textuelle et l'état de sélection."""
        query = normalize_tag_key(self.search_input.text())
        only_selected = self.filter_only_selected_cb.isChecked()

        for sp, parent in self.specialty_items.items():
            is_checked = parent.checkState(0) in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked)

            if only_selected and not is_checked:
                parent.setHidden(True)
                continue

            sp_norm = normalize_tag_key(sp)
            parent_matches = (not query) or (query in sp_norm)

            matching_children = 0
            child_count = parent.childCount()

            for i in range(child_count):
                child = parent.child(i)
                child_text_norm = normalize_tag_key(child.text(0))
                child_matches = (not query) or (query in child_text_norm)

                if only_selected:
                    child_checked = (child.checkState(0) == Qt.CheckState.Checked)
                    child_visible = child_checked and (parent_matches or child_matches)
                else:
                    child_visible = parent_matches or child_matches

                child.setHidden(not child_visible)
                if child_visible and (query and child_matches):
                    matching_children += 1

            if not query:
                parent.setHidden(False)
            else:
                if parent_matches or matching_children > 0:
                    parent.setHidden(False)
                    if matching_children > 0 and not parent_matches:
                        parent.setExpanded(True)
                else:
                    parent.setHidden(True)

    def on_threshold_changed(self):
        """Réactualise l'analyse du curriculum lors d'un changement de seuil."""
        self.load_data()

    def update_selection_summary(self):
        """Met à jour l'indicateur textuel de sélection en temps réel."""
        selected_specs_count = 0
        total_items = 0
        total_cards = 0

        for sp, parent in self.specialty_items.items():
            state = parent.checkState(0)
            if state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked):
                selected_specs_count += 1
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    if child.checkState(0) == Qt.CheckState.Checked:
                        total_items += 1
                        total_cards += getattr(child, "spec_cards", 0)

        if selected_specs_count == 0:
            self.summary_label.setText("Aucune discipline sélectionnée")
            self.summary_label.setStyleSheet("color: #a6adc8; font-weight: 500; font-size: 12px;")
        else:
            disc_str = f"{selected_specs_count} discipline{'s' if selected_specs_count > 1 else ''}"
            items_str = f"{total_items} item{'s' if total_items > 1 else ''}"
            cards_str = f"{total_cards} carte{'s' if total_cards > 1 else ''} estimée{'s' if total_cards > 1 else ''}"
            self.summary_label.setText(f"Sélection : {disc_str} • {items_str} • {cards_str}")
            self.summary_label.setStyleSheet("color: #89b4fa; font-weight: 600; font-size: 12px;")

    def get_selected_data(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """Retourne la liste des spécialités cochées et le dictionnaire des items sélectionnés."""
        selected_specs = []
        selected_items = {}

        for sp, parent in self.specialty_items.items():
            state = parent.checkState(0)
            if state in (Qt.CheckState.Checked, Qt.CheckState.PartiallyChecked):
                selected_specs.append(sp)
                checked_tags = []
                for i in range(parent.childCount()):
                    child = parent.child(i)
                    if child.checkState(0) == Qt.CheckState.Checked:
                        tag = getattr(child, "item_tag", "")
                        if tag:
                            checked_tags.append(tag)
                selected_items[sp] = checked_tags

        return selected_specs, selected_items

    def get_selected_specialties(self) -> List[str]:
        """Rétrocompatibilité : retourne la liste des spécialités sélectionnées."""
        return self.get_selected_data()[0]

    def collect_current_settings(self) -> Dict[str, Any]:
        """Collecte l'ensemble des réglages actuels de l'interface."""
        selected_specs, selected_items = self.get_selected_data()
        fully_checked = []
        for sp, parent in self.specialty_items.items():
            if parent.checkState(0) == Qt.CheckState.Checked:
                fully_checked.append(sp)

        scope = "volet_matiere" if self.radio_scope_matiere.isChecked() else "item_complet"
        card_filter = self.status_combo.currentData() or "due_and_new"
        rank_filter = self.rank_combo.currentData() or "all"
        order_val = self.order_combo.currentData() or "inherit"
        resched = self.resched_checkbox.isChecked()
        auto_sync = self.auto_sync_checkbox.isChecked()
        filter_selected = self.filter_only_selected_cb.isChecked()
        threshold = self.threshold_spin.value()

        return {
            "selected_specs": selected_specs,
            "selected_items": selected_items,
            "fully_checked_specs": fully_checked,
            "threshold": threshold,
            "scope": scope,
            "card_filter": card_filter,
            "rank_filter": rank_filter,
            "order": order_val,
            "resched": resched,
            "auto_sync": auto_sync,
            "filter_only_selected": filter_selected
        }

    def save_current_settings(self):
        """Enregistre les réglages actuels de l'utilisateur."""
        try:
            settings = self.collect_current_settings()
            save_filtered_decks_settings(settings)
            self.saved_settings = settings
        except Exception as e:
            log_error(f"Erreur sauvegarde réglages utilisateur : {e}")

    def reject(self):
        """Sauvegarde les réglages avant fermeture du dialogue."""
        self.save_current_settings()
        super().reject()

    def accept(self):
        """Sauvegarde les réglages lors de la validation du dialogue."""
        self.save_current_settings()
        super().accept()

    def closeEvent(self, event):
        """Sauvegarde les réglages lors de la fermeture de la fenêtre."""
        self.save_current_settings()
        super().closeEvent(event)

    def on_generate_clicked(self):
        """Déclenche la génération de l'arborescence des paquets filtrés."""
        self.save_current_settings()
        selected_specs, selected_items = self.get_selected_data()
        if not selected_specs:
            showWarning("Veuillez cocher au moins une discipline ou matière à générer.", parent=self)
            return

        total_items = sum(len(items) for items in selected_items.values())
        if total_items == 0:
            showWarning("Aucun item sélectionné dans les disciplines cochées.", parent=self)
            return

        scope = "volet_matiere" if self.radio_scope_matiere.isChecked() else "item_complet"
        card_filter = self.status_combo.currentData() or "due_and_new"
        rank_filter = self.rank_combo.currentData() or "all"
        resched = self.resched_checkbox.isChecked()

        order_val = self.order_combo.currentData() or "inherit"

        options = {
            "root_name": ROOT_DECK_NAME,
            "scope": scope,
            "card_filter": card_filter,
            "rank_filter": rank_filter,
            "order": order_val,
            "resched": resched,
            "rebuild": True
        }

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        def update_progress(current, total, deck_name):
            if total > 0:
                pct = int((current / total) * 100)
                self.progress_bar.setValue(pct)
            QApplication.processEvents()

        res = generate_filtered_hierarchy(
            selected_specialties=selected_specs,
            curriculum_data=self.curriculum_data,
            options=options,
            progress_callback=update_progress,
            selected_items=selected_items
        )

        self.progress_bar.setVisible(False)

        if res.get("success"):
            created = res.get("created_decks", 0)
            cards = res.get("rebuilt_cards", 0)
            preset_name = res.get("inherited_preset_name", "Par défaut")
            showInfo(
                f"Génération terminée avec succès.\n\n"
                f"• Paquets filtrés créés / mis à jour : {created}\n"
                f"• Cartes actuellement allouées : {cards}\n"
                f"• Options de révision héritées : Preset '{preset_name}'\n"
                f"• Emplacement : {ROOT_DECK_NAME}\n\n"
                f"L'arborescence est disponible dans la fenêtre principale d'Anki.",
                parent=self
            )
            if mw:
                mw.reset()
            self.accept()
        else:
            showWarning(f"Erreur lors de la génération : {res.get('error', 'Erreur inconnue')}", parent=self)

    def on_rebuild_clicked(self):
        """Reconstruit et réattribue les cartes dans tous les paquets filtrés existants."""
        self.save_current_settings()

        dids = get_edn_filtered_deck_ids()
        if not dids:
            showInfo(
                "Aucun paquet filtré actif n'a été détecté sous 'EDN - Paquets Filtrés'.\n\n"
                "Utilisez le bouton 'Générer les paquets filtrés' pour créer l'arborescence.",
                parent=self
            )
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        QApplication.processEvents()

        def update_progress(current, total, did):
            if total > 0:
                pct = int((current / total) * 100)
                self.progress_bar.setValue(pct)
            QApplication.processEvents()

        try:
            res = rebuild_all_edn_filtered_decks(progress_callback=update_progress)
            count = res.get("count", 0)
            total_cards = res.get("total_cards", 0)
            if mw:
                mw.reset()
            tooltip(f"{count} paquets filtrés régénérés ({total_cards} cartes allouées).")
        except Exception as e:
            log_error(f"Erreur lors de la régénération des paquets filtrés : {e}")
            showWarning(f"Erreur lors de la régénération : {e}", parent=self)
        finally:
            self.progress_bar.setVisible(False)

    def on_empty_clicked(self):
        """Vide tous les paquets filtrés EDN sans supprimer l'arborescence."""
        self.save_current_settings()
        if not askUser(
            "Voulez-vous vider tous les paquets filtrés sous 'EDN - Paquets Filtrés' ?\n\n"
            "Toutes les cartes réintégreront instantanément le paquet principal Anki EDN "
            "sans modifier vos échéances de révision.",
            parent=self
        ):
            return

        count = empty_all_edn_filtered_decks()
        if mw:
            mw.reset()
        tooltip(f"{count} paquets filtrés vidés avec succès.")

    def on_delete_clicked(self):
        """Supprime complètement l'arborescence des paquets filtrés après vidage."""
        if not askUser(
            "Êtes-vous certain de vouloir supprimer l'arborescence 'EDN - Paquets Filtrés' ?\n\n"
            "Toutes les cartes seront automatiquement réintégrées dans leur paquet d'origine.",
            parent=self
        ):
            return

        success = delete_all_edn_filtered_decks()
        if mw:
            mw.reset()
        if success:
            showInfo("L'arborescence des paquets filtrés a été supprimée.", parent=self)
            self.accept()
        else:
            showInfo("Aucune arborescence active à supprimer.", parent=self)


def open_filtered_decks_dialog(parent=None):
    """Ouvre la fenêtre du générateur de paquets filtrés."""
    dialog = FilteredDecksDialog(parent or mw)
    dialog.exec()
