"""
Module « Débloquer un item étudié » pour Anki EDN Installer.

Permet aux étudiants débutants et en progression de :
1. Rechercher rapidement un item EDN (ou SDD) par numéro ou intitulé (ex. 145 ou Endocardite) ;
2. Débloquer progressivement ses cartes selon 3 modes :
   - Essentiel (Cartes Sommaires + Tombé + Rang A) — pour commencer sans se noyer ;
   - Rang A complet ;
   - Item complet.
3. Appliquer nativement le tri « Scaffolding » (inspiré et connecté à Anki_Smart_Queue) :
   ordonner automatiquement les nouvelles cartes débloquées (ou déjà débloquées
   manuellement, sans débloquer de cartes supplémentaires) pour présenter d'abord
   la carte Sommaire, puis les définitions et la sémiologie, ensuite les examens
   complémentaires, et enfin la thérapeutique et les scores.
"""

from __future__ import annotations

import os
import re
import html
import time
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from aqt import mw, gui_hooks
from aqt.qt import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColor,
    QDialog,
    QEvent,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    Qt,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showWarning, tooltip

from .filtered_decks import (
    clean_item_base_label,
    clean_sdd_base_label,
    clean_specialty_name,
    is_specialty_tag,
    parse_item_tag,
    parse_sdd_tag,
    rebuild_all_edn_filtered_decks,
)
from .logger import log, log_error


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES PEDAGOGIQUES & SCAFFOLDING
# ─────────────────────────────────────────────────────────────────────────────

TIER_SOMMAIRE = 0
TIER_DEFINITIONS_SEMIO = 1
TIER_EXAMENS = 2
TIER_THERAPEUTIQUE_SCORES = 3

TIER_LABELS = {
    TIER_SOMMAIRE: "Sommaire",
    TIER_DEFINITIONS_SEMIO: "Définitions & Sémiologie",
    TIER_EXAMENS: "Examens complémentaires",
    TIER_THERAPEUTIQUE_SCORES: "Thérapeutique & Scores",
}

MODE_ESSENTIEL = "essentiel"
MODE_RANG_A = "rang_a"
MODE_COMPLET = "complet"

MODE_LABELS = {
    MODE_ESSENTIEL: "Essentiel (Sommaires + Tombé + Rang A)",
    MODE_RANG_A: "Rang A complet",
    MODE_COMPLET: "Item complet",
}

# Poids par défaut identiques à Anki_Smart_Queue (fallback si user_behavior.db absent)
DEFAULT_SMART_QUEUE_WEIGHTS: Dict[str, float] = {
    "has_signe_tag": 5.0,
    "has_score_tag": -3.0,
    "field_length": -0.5,
    "is_therapeutic": -1.0,
    "is_diagnostic": 0.5,
    "is_list": -2.0,
    "cloze_count": -0.5,
    "word_count": -0.1,
    "image_count": 0.5,
}

# Expressions régulières pour liens Anki_EDN_Lier_les_cartes (clickable_cards / Main)
_CLICKABLE_LINK_RE = re.compile(
    r'clickable_cards[^>]*?(?:nid=["\'](\d+)["\']|cards_ct_click\(\s*[\'"](\d+)[\'"]\s*\))'
    r'|clickable_cards[^>]*>(?:<[^>]+>)*\s*(\d{2,16})\s*(?:</[^>]+>)*',
    re.IGNORECASE,
)
_MAIN_LINE_RE = re.compile(
    r'\bMain\b(?:\s|&nbsp;|<[^>]+>|—|-|:){0,60}?(\d{2,16})',
    re.IGNORECASE,
)
_TAG_HTML_RE = re.compile(r'<[^>]+>')
_CLOZE_RE = re.compile(r'\{\{c\d+::(.*?)(?:::.*?)?\}\}', re.DOTALL)
_TOMBE_TAG_RE = re.compile(r'(?:^|::)tombe(?:$|::|_)')


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES TEXTE & SCORING SMART QUEUE
# ─────────────────────────────────────────────────────────────────────────────

def normalize_search_text(text: str) -> str:
    """Normalise une chaîne (minuscules sans accents) pour la recherche et le NLP."""
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.split())


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    txt = html.unescape(raw)
    txt = txt.replace("\xa0", " ")
    txt = _TAG_HTML_RE.sub(" ", txt)
    return " ".join(txt.split())


def _unwrap_clozes_preview(raw: str) -> str:
    return _CLOZE_RE.sub(r"\1", raw)


def _load_smart_queue_weights() -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Charge les poids appris depuis Anki_Smart_Queue/user_behavior.db s'ils existent,
    ainsi que les moyennes historiques pour la normalisation.
    Retourne (weights_dict, avgs_dict).
    """
    weights = dict(DEFAULT_SMART_QUEUE_WEIGHTS)
    avgs = {
        "field_length": 200.0,
        "word_count": 30.0,
    }
    try:
        addons_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(addons_root, "Anki_Smart_Queue", "user_behavior.db")
        if os.path.isfile(db_path):
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT feature_name, weight FROM model_weights")
            for feat, w in cur.fetchall():
                if w is not None:
                    weights[feat] = float(w)
            cur.execute("SELECT AVG(field_length), AVG(word_count) FROM learning_events")
            row = cur.fetchone()
            if row and row[0] is not None:
                avgs["field_length"] = float(row[0])
                if row[1]:
                    avgs["word_count"] = float(row[1])
            conn.close()
    except Exception:
        pass
    return weights, avgs


def _extract_clickable_links_and_main(flds_str: str) -> Tuple[Set[int], Set[int]]:
    """
    Extrait :
    - outgoing_nids : l'ensemble des NIDs ciblés via clickable_cards sur cette note
    - main_nids : l'ensemble des NIDs désignés comme 'Main' (carte mère / sommaire)
    """
    outgoing_nids: Set[int] = set()
    main_nids: Set[int] = set()
    if not flds_str:
        return outgoing_nids, main_nids

    fields = flds_str.split("\x1f")
    # Analyser en priorité les champs susceptibles de contenir les cartes liées
    for part in fields:
        if "clickable_cards" in part or "cards_ct_click" in part or "nid=" in part.lower():
            for g1, g2, g3 in _CLICKABLE_LINK_RE.findall(part):
                raw_id = g1 or g2 or g3
                if raw_id:
                    try:
                        outgoing_nids.add(int(raw_id))
                    except ValueError:
                        pass

        # Détecter explicitement 'Main — <NID>' dans les liens ou texte structuré
        if "main" in part.lower():
            for segment in re.split(r'<br\s*/?>|\n', part, flags=re.IGNORECASE):
                m_main = re.search(r'\bMain\b', segment, re.IGNORECASE)
                if not m_main:
                    continue
                tail = segment[m_main.start():m_main.start() + 220]
                has_link_markup = (
                    "clickable_cards" in tail
                    or "cards_ct_click" in tail
                    or "<kbd" in tail.lower()
                    or "nid=" in tail.lower()
                    or "—" in tail
                    or "->" in tail
                )
                if not has_link_markup:
                    continue
                for g1, g2, g3 in _CLICKABLE_LINK_RE.findall(tail):
                    raw_id = g1 or g2 or g3
                    if raw_id:
                        try:
                            nid_val = int(raw_id)
                            main_nids.add(nid_val)
                            outgoing_nids.add(nid_val)
                        except ValueError:
                            pass
                for m_id in _MAIN_LINE_RE.findall(tail):
                    try:
                        nid_val = int(m_id)
                        main_nids.add(nid_val)
                        outgoing_nids.add(nid_val)
                    except ValueError:
                        pass

    return outgoing_nids, main_nids


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION PEDAGOGIQUE (SOMMAIRE / RANG / SCAFFOLDING)
# ─────────────────────────────────────────────────────────────────────────────

_SOMMAIRE_KEYWORDS = (
    "(sommaire)",
    "sommaire",
    "plan du cours",
    "arbre decisionnel",
    "algorithme",
    "vue d'ensemble",
    "synthese",
    "generalites sur",
    "fondamentaux",
)

_DEFINITION_SEMIO_RECTO_CUES = (
    "definition",
    "qu'est-ce que",
    "qu est ce que",
    "est defini",
    "se definit",
    "semiologie",
    "signes cliniques",
    "signes de",
    "signes d'",
    "signe de",
    "symptomes",
    "examen clinique",
    "examen physique",
    "interrogatoire",
    "auscultation",
    "palpation",
    "percussion",
    "inspection",
    "triade",
    "syndrome",
    "physiopathologie",
    "mecanisme",
    "etiologie",
    "causes de",
    "causes d'",
    "facteurs de risque",
    "fdcv",
    "porte d'entree",
    "epidemiologie",
)

_EXAMENS_RECTO_CUES = (
    "examen complementaire",
    "examens complementaires",
    "paraclinique",
    "bilan biologique",
    "bilan d'",
    "bilan de",
    "biologie",
    "imagerie",
    "irm",
    "scanner",
    "tdm",
    "echographie",
    "echocardiographie",
    "ett",
    "eto",
    "radiographie",
    "radio du",
    "radio de",
    "ecg",
    "electrocardiogramme",
    "eeg",
    "enmg",
    "efr",
    "endoscopie",
    "fibroscopie",
    "coloscopie",
    "ponction",
    "biopsie",
    "anatomopathologie",
    "anapath",
    "hemoculture",
    "ecbu",
    "dosage",
    "serologie",
    "pcr ",
    "diagnostic positif",
    "criteres diagnostiques",
    "confirmation diagnostique",
    "seuil d",
    "mapa",
    "automesure",
)

_THERAPEUTIQUE_SCORE_RECTO_CUES = (
    "traitement",
    "therapeutique",
    "prise en charge",
    "pec ",
    "pec d",
    "posologie",
    "medicament",
    "chirurgie",
    "chirurgical",
    "antibiotherapie",
    "antibiotique",
    "corticotherapie",
    "corticoide",
    "chimiotherapie",
    "immunotherapie",
    "prevention",
    "prophylaxie",
    "surveillance",
    "contre-indication",
    "contre indication",
    "indication",
    "score",
    "criteres de duke",
    "classification",
    "stade",
    "grade",
    "diagnostic differentiel",
    "complication",
    "pronostic",
    "mortalite",
    "gravite",
)


def classify_edn_note(
    flds_str: str,
    tags_str: str,
    notetype_name: str = "",
    is_main_target: bool = False,
    outgoing_links_count: int = 0,
    weights: Optional[Dict[str, float]] = None,
    avgs: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Classifie une note EDN pour :
    - Déterminer son rang ('A', 'B', 'other') ;
    - Identifier s'il s'agit d'une carte Sommaire ou d'un cœur essentiel de Rang A ;
    - Affecter son palier pédagogique Scaffolding (0..3) ;
    - Calculer son score d'accessibilité Anki_Smart_Queue.
    """
    fields = flds_str.split("\x1f") if flds_str else [""]
    nt_lower = normalize_search_text(notetype_name)
    tags_list = [t for t in (tags_str or "").split() if t]
    tags_norm = [normalize_search_text(t) for t in tags_list]
    tags_joined = " ".join(tags_norm)

    # Champs principaux pour déterminer la question posée à l'étudiant
    if "semiologie" in nt_lower and len(fields) > 1:
        recto_raw = f"{fields[1]} {fields[0]}"
    elif len(fields) > 0:
        recto_raw = fields[0]
    else:
        recto_raw = ""

    recto_plain = _strip_html(_unwrap_clozes_preview(recto_raw))
    recto_norm = normalize_search_text(recto_plain)
    all_text_raw = " ".join(fields)
    all_text_plain = _strip_html(_unwrap_clozes_preview(all_text_raw))

    # 1. Rang A / B / autre
    is_rang_a = any(
        "rang::a" in t or t == "rang_a" or t == "rang a"
        for t in tags_norm
    )
    is_rang_b = any(
        "rang::b" in t or t == "rang_b" or t == "rang a_b" or t == "rang b"
        for t in tags_norm
    )
    rank = "A" if is_rang_a else ("B" if is_rang_b else "other")

    # 2. Indices NLP (compatibles Anki_Smart_Queue)
    txt_lower = all_text_raw.lower()
    is_list = 1 if ("<ul>" in txt_lower or "<ol>" in txt_lower or txt_lower.count("<br>") > 3) else 0
    cloze_count = len(re.findall(r"\{\{c\d+::", all_text_raw))
    word_count = len(all_text_plain.split())
    image_count = txt_lower.count("<img")
    field_length = len(all_text_raw)

    has_signe_tag = any("signe" in t or "semiologie" in t for t in tags_norm)
    has_imagerie_tag = any("imagerie" in t for t in tags_norm)
    has_score_tag = any("score" in t or "differentiel" in t or "differential" in t for t in tags_norm)
    has_atb_tag = any("antibiotherapie" in t or "pharmacologie" in t for t in tags_norm)
    has_sommaire_tag = any(
        k in t for t in tags_norm for k in ("sommaire", "fondamentaux", "synthese", "arbre", "algorithme")
    )
    has_tombe_tag = any(bool(_TOMBE_TAG_RE.search(t)) for t in tags_norm)

    # 3. Détection « Carte Sommaire »
    has_sommaire_title = any(k in recto_norm for k in _SOMMAIRE_KEYWORDS)
    is_syndrome_nt = "syndrome" in nt_lower
    is_semio_nt = "semiologie" in nt_lower
    is_hub_note = outgoing_links_count >= 3

    is_sommaire = bool(
        is_syndrome_nt
        or is_main_target
        or has_sommaire_tag
        or has_sommaire_title
        or is_hub_note
    )

    # 4. Détermination du palier Scaffolding (0 -> 3)
    has_tx_recto = any(k in recto_norm for k in _THERAPEUTIQUE_SCORE_RECTO_CUES)
    has_exam_recto = any(k in recto_norm for k in _EXAMENS_RECTO_CUES)
    has_semio_recto = any(k in recto_norm for k in _DEFINITION_SEMIO_RECTO_CUES)

    # Pattern typique de définition en texte à trous : "L'X est {{c1::...}}"
    is_cloze_def = (
        ("text" in nt_lower or "trou" in nt_lower or cloze_count >= 1)
        and bool(re.search(r'\best\s+(?:une?|la|le|l\'|des|defini|caracterise)', recto_norm))
        and not has_tx_recto
        and not has_exam_recto
    )

    if is_sommaire:
        scaffolding_tier = TIER_SOMMAIRE
    elif is_semio_nt and not has_tx_recto and not has_score_tag:
        scaffolding_tier = TIER_DEFINITIONS_SEMIO
    elif (has_score_tag or has_atb_tag) and not has_exam_recto:
        scaffolding_tier = TIER_THERAPEUTIQUE_SCORES
    elif has_tx_recto and not (has_exam_recto and "diagnostic" in recto_norm):
        scaffolding_tier = TIER_THERAPEUTIQUE_SCORES
    elif has_imagerie_tag or has_exam_recto:
        scaffolding_tier = TIER_EXAMENS
    elif has_signe_tag or has_semio_recto or is_cloze_def:
        scaffolding_tier = TIER_DEFINITIONS_SEMIO
    else:
        # Heuristique douce sur le reste : définitions / notions courtes -> Palier 1, bilans / listes -> Palier 2
        if not is_list and word_count <= 22 and cloze_count <= 2:
            scaffolding_tier = TIER_DEFINITIONS_SEMIO
        else:
            scaffolding_tier = TIER_EXAMENS

    # Sous-ordre au sein de chaque palier :
    # - Palier Sommaire : sommaires généraux / sémiologiques -> diagnostiques -> thérapeutiques
    # - Palier Définitions & Sémiologie : définitions & sémiologie clinique -> physiopath/étiologie -> notions générales
    if scaffolding_tier == TIER_SOMMAIRE:
        if has_tx_recto or has_score_tag or has_atb_tag:
            tier_suborder = 2
        elif has_exam_recto:
            tier_suborder = 1
        else:
            tier_suborder = 0
    elif scaffolding_tier == TIER_DEFINITIONS_SEMIO:
        is_explicit_def_or_semio = (
            is_cloze_def
            or is_semio_nt
            or has_signe_tag
            or any(
                k in recto_norm
                for k in ("definition", "se definit", "est defini", "qu'est-ce que", "signes", "semiologie", "symptomes", "triade")
            )
        )
        if is_explicit_def_or_semio:
            tier_suborder = 0
        elif has_semio_recto:
            tier_suborder = 1
        else:
            tier_suborder = 2
    else:
        tier_suborder = 0

    # 5. Score d'accessibilité Anki_Smart_Queue
    w = weights or DEFAULT_SMART_QUEUE_WEIGHTS
    a = avgs or {"field_length": 200.0, "word_count": 30.0}

    score = 0.0
    if is_rang_a:
        score += 3.0
    elif is_rang_b:
        score += 1.0

    for t in tags_norm:
        tf = f"tag_{t}"
        if tf in w:
            score += w[tf]

    if has_signe_tag:
        score += w.get("has_signe_tag", 5.0)
    if has_score_tag:
        score += w.get("has_score_tag", -3.0)
    if is_list:
        score += w.get("is_list", -2.0)
    if has_tx_recto or has_atb_tag:
        score += w.get("is_therapeutic", -1.0)
    if has_exam_recto or has_semio_recto:
        score += w.get("is_diagnostic", 0.5)
    if cloze_count > 1:
        score += w.get("cloze_count", -0.5) * (cloze_count - 1)
    if image_count > 0:
        score += w.get("image_count", 0.5) * image_count
    if a.get("field_length"):
        score += w.get("field_length", -0.5) * ((field_length - a["field_length"]) / 100.0)
    if a.get("word_count"):
        score += w.get("word_count", -0.1) * ((word_count - a["word_count"]) / 20.0)

    # 6. Éligibilité au mode « Essentiel (Sommaires + Tombé + Rang A) »
    is_essential_core = bool(
        is_sommaire
        or has_tombe_tag
        or (
            is_rang_a
            and not has_score_tag
            and (
                scaffolding_tier == TIER_DEFINITIONS_SEMIO
                or (scaffolding_tier == TIER_EXAMENS and not is_list and word_count <= 35)
                or is_semio_nt
            )
        )
    )

    return {
        "rank": rank,
        "is_rang_a": is_rang_a,
        "is_rang_b": is_rang_b,
        "is_sommaire": is_sommaire,
        "has_tombe_tag": has_tombe_tag,
        "is_essential_core": is_essential_core,
        "scaffolding_tier": scaffolding_tier,
        "tier_suborder": tier_suborder,
        "smart_queue_score": round(score, 2),
        "recto_preview": recto_plain[:140] or "(Sans titre)",
        "is_list": bool(is_list),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODELES DE DONNEES & INDEXATION DES ITEMS EDN
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EdnItemEntry:
    """Représente un item EDN (ou SDD) avec ses statistiques et ses 3 modes de déblocage."""
    key: str
    title: str
    short_title: str
    number: str
    num_int: int
    is_sdd: bool
    specialties: List[str]
    search_blob: str
    all_cids: List[int]
    active_cids: Set[int]
    suspended_cids: Set[int]
    mode_cids: Dict[str, Set[int]] = field(default_factory=dict)
    mode_to_unlock_cids: Dict[str, Set[int]] = field(default_factory=dict)
    card_meta: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        return len(self.all_cids)

    @property
    def active_count(self) -> int:
        return len(self.active_cids)

    @property
    def suspended_count(self) -> int:
        return len(self.suspended_cids)

    @property
    def active_new_count(self) -> int:
        """Nombre de cartes actives encore nouvelles (type=0, queue=0) dans l'item."""
        return sum(
            1
            for cid in self.active_cids
            if self.card_meta.get(cid, {}).get("card_type") == 0
            and self.card_meta.get(cid, {}).get("card_queue") == 0
        )

    def get_mode_counts(self, mode: str) -> Tuple[int, int, int]:
        """Retourne (a_debloquer, total_mode, deja_actives_dans_mode)."""
        total_mode = len(self.mode_cids.get(mode, set()))
        to_unlock = len(self.mode_to_unlock_cids.get(mode, set()))
        already_active = max(0, total_mode - to_unlock)
        return to_unlock, total_mode, already_active

    def get_tier_breakdown(self, mode: str) -> Dict[int, int]:
        """Retourne le nombre de cartes par palier Scaffolding pour le mode demandé."""
        counts = {
            TIER_SOMMAIRE: 0,
            TIER_DEFINITIONS_SEMIO: 0,
            TIER_EXAMENS: 0,
            TIER_THERAPEUTIQUE_SCORES: 0,
        }
        for cid in self.mode_cids.get(mode, set()):
            meta = self.card_meta.get(cid)
            if meta:
                tier = meta["scaffolding_tier"]
                counts[tier] = counts.get(tier, 0) + 1
        return counts


def _build_main_and_outgoing_index(col) -> Tuple[Set[int], Dict[int, int]]:
    """
    Parcourt les notes liées (clickable_cards / Main) pour identifier :
    - main_targets : l'ensemble des NIDs désignés comme cartes mères / Sommaires ;
    - outgoing_counts : nombre de liens sortants distincts par NID.
    """
    main_targets: Set[int] = set()
    outgoing_counts: Dict[int, int] = {}
    rows = col.db.all(
        "SELECT id, flds FROM notes "
        "WHERE flds LIKE '%clickable_cards%' OR flds LIKE '%cards_ct_click%' OR flds LIKE '%Main%'"
    )
    for nid, flds in rows:
        out_nids, mains = _extract_clickable_links_and_main(flds)
        if out_nids:
            outgoing_counts[nid] = len(out_nids)
        if mains:
            main_targets.update(mains)
    return main_targets, outgoing_counts


def get_all_edn_items(col=None) -> List[EdnItemEntry]:
    """
    Indexe l'ensemble des items EDN et Situations de Départ (SDD) de la collection
    et calcule pour chacun les cartes des 3 modes de déblocage progressif :
      - 'essentiel' : Cartes Sommaires + cœur Rang A (sans se noyer)
      - 'rang_a'    : Cartes Sommaires + intégralité du Rang A
      - 'complet'   : Toutes les cartes de l'item (Rang A + Rang B + autres)
    """
    if col is None:
        if mw is None or mw.col is None:
            return []
        col = mw.col

    notetype_names: Dict[int, str] = {}
    try:
        for m in col.models.all():
            notetype_names[int(m["id"])] = str(m.get("name", ""))
    except Exception:
        pass

    main_targets, outgoing_counts = _build_main_and_outgoing_index(col)
    weights, avgs = _load_smart_queue_weights()

    rows = col.db.all("""
        SELECT c.id, c.nid, c.ord, c.type, c.queue, c.due, n.mid, n.tags, n.flds
        FROM cards c
        JOIN notes n ON c.nid = n.id
        WHERE n.tags LIKE '%item-%'
           OR n.tags LIKE '%item_%'
           OR n.tags LIKE '%item::%'
           OR n.tags LIKE '%sdd%'
           OR n.tags LIKE '%SDD%'
    """)

    note_meta_cache: Dict[int, Dict[str, Any]] = {}
    items_buckets: Dict[str, Dict[str, Any]] = {}

    for cid, nid, card_ord, c_type, c_queue, c_due, mid, tags_str, flds_str in rows:
        if not tags_str:
            continue
        tags = [t for t in tags_str.strip().split() if t]

        if nid not in note_meta_cache:
            note_meta_cache[nid] = classify_edn_note(
                flds_str=flds_str,
                tags_str=tags_str,
                notetype_name=notetype_names.get(mid, ""),
                is_main_target=(nid in main_targets),
                outgoing_links_count=outgoing_counts.get(nid, 0),
                weights=weights,
                avgs=avgs,
            )
        meta = note_meta_cache[nid]

        spec_names = [clean_specialty_name(t) for t in tags if is_specialty_tag(t)]

        matched_keys: List[Tuple[str, bool]] = []
        seen_keys: Set[str] = set()
        for t in tags:
            b_tag, _ = parse_item_tag(t)
            if b_tag:
                canonical_k = b_tag.lower()
                if canonical_k not in seen_keys:
                    seen_keys.add(canonical_k)
                    matched_keys.append((b_tag, False))
                continue
            b_sdd, _ = parse_sdd_tag(t)
            if b_sdd:
                canonical_k = b_sdd.lower()
                if canonical_k not in seen_keys:
                    seen_keys.add(canonical_k)
                    matched_keys.append((b_sdd, True))

        for raw_base, is_sdd in matched_keys:
            norm_k = raw_base.lower()
            bucket = items_buckets.get(norm_k)
            if bucket is None:
                if is_sdd:
                    num_int, label = clean_sdd_base_label(raw_base)
                    num_str = f"SDD {num_int:03d}" if num_int < 9000 else "SDD"
                else:
                    num_int, label = clean_item_base_label(raw_base)
                    num_str = str(num_int) if num_int < 9999 else ""

                if " - " in label:
                    short_title = label.split(" - ", 1)[1].strip()
                else:
                    short_title = label

                bucket = {
                    "key": raw_base,
                    "title": label,
                    "short_title": short_title,
                    "number": num_str,
                    "num_int": num_int,
                    "is_sdd": is_sdd,
                    "spec_counts": {},
                    "cards": [],
                    "card_meta": {},
                    "active_cids": set(),
                    "suspended_cids": set(),
                }
                items_buckets[norm_k] = bucket

            for sp in spec_names:
                bucket["spec_counts"][sp] = bucket["spec_counts"].get(sp, 0) + 1

            bucket["cards"].append((cid, nid, card_ord, c_type, c_queue, c_due))
            bucket["card_meta"][cid] = {
                **meta,
                "card_ord": card_ord,
                "card_type": c_type,
                "card_queue": c_queue,
                "card_due": c_due,
            }
            if c_queue == -1:
                bucket["suspended_cids"].add(cid)
            else:
                bucket["active_cids"].add(cid)

    entries: List[EdnItemEntry] = []
    for bucket in items_buckets.values():
        card_meta = bucket["card_meta"]
        all_cids = [c[0] for c in bucket["cards"]]
        if not all_cids:
            continue

        sommaire_cids = {cid for cid in all_cids if card_meta[cid]["is_sommaire"]}
        tombe_cids = {cid for cid in all_cids if card_meta[cid].get("has_tombe_tag")}
        always_essential_cids = sommaire_cids | tombe_cids
        rang_a_only_cids = {cid for cid in all_cids if card_meta[cid]["is_rang_a"]}
        essential_non_sommaire_a = [
            cid for cid in all_cids
            if cid not in always_essential_cids
            and card_meta[cid]["is_essential_core"]
            and card_meta[cid]["is_rang_a"]
        ]

        # Trier les candidats Rang A par accessibilité Scaffolding (pour sélection anti-noyade)
        rang_a_sorted = sorted(
            [cid for cid in rang_a_only_cids if cid not in always_essential_cids],
            key=lambda c: (
                card_meta[c]["scaffolding_tier"],
                card_meta[c]["tier_suborder"],
                -card_meta[c]["smart_queue_score"],
                card_meta[c]["card_ord"],
                c,
            ),
        )

        # Sélection « Essentiel (Sommaires + Tombé + Rang A) — pour commencer sans se noyer » :
        # 1. Garder toutes les cartes Sommaires et toutes les cartes taggées « tombé » ;
        # 2. Ajouter le cœur essentiel de Rang A (définitions, sémiologie, diagnostic clé) ;
        # 3. Si l'item a beaucoup de cartes de Rang A (>= 8) et que le cœur dépasse 65% ou égale tout le Rang A,
        #    plafonner la portion non-sommaire/non-tombé à ~55% afin d'offrir un vrai palier progressif avant « Rang A complet » ;
        # 4. À l'inverse, si le mode Essentiel serait vide alors que des Rang A existent, prendre le top 50% de Rang A.
        ess_cids: Set[int] = set(always_essential_cids) | set(essential_non_sommaire_a)
        non_sommaire_a_total = len(rang_a_sorted)
        if non_sommaire_a_total >= 4:
            ess_a_non_sommaire = [c for c in rang_a_sorted if c in ess_cids]
            max_cap = max(2, int(non_sommaire_a_total * 0.6))
            if len(ess_a_non_sommaire) >= non_sommaire_a_total:
                kept = ess_a_non_sommaire[:max_cap]
                ess_cids = set(always_essential_cids) | set(kept)
            elif len(ess_a_non_sommaire) == 0 and len(ess_cids) == 0:
                ess_cids = set(rang_a_sorted[:max_cap])
        elif len(ess_cids) == 0 and rang_a_sorted:
            ess_cids = set(rang_a_sorted[:max(1, (len(rang_a_sorted) + 1) // 2)])
        elif len(ess_cids) == 0:
            # Item sans aucun tag Rang A ni Sommaire : prendre le palier le plus accessible
            fallback_sorted = sorted(
                all_cids,
                key=lambda c: (
                    card_meta[c]["scaffolding_tier"],
                    -card_meta[c]["smart_queue_score"],
                    c,
                ),
            )
            ess_cids = set(fallback_sorted[:max(1, min(5, (len(all_cids) + 1) // 2))])

        # Garantir la monotonie stricte des 3 paliers : Essentiel ⊆ Rang A complet ⊆ Item complet
        mode_ess = ess_cids
        mode_rang_a = mode_ess | rang_a_only_cids
        if not mode_rang_a:
            mode_rang_a = set(mode_ess)
        mode_complet = set(all_cids)

        suspended_cids = bucket["suspended_cids"]
        top_specs = [
            sp for sp, _ in sorted(bucket["spec_counts"].items(), key=lambda x: (-x[1], x[0]))[:3]
        ]

        search_parts = [
            bucket["number"],
            f"{bucket['num_int']:03d}" if bucket["num_int"] < 9000 else "",
            bucket["title"],
            bucket["key"],
            " ".join(top_specs),
        ]
        if bucket["is_sdd"]:
            search_parts.append("ecos sdd situation de depart")

        entry = EdnItemEntry(
            key=bucket["key"],
            title=bucket["title"],
            short_title=bucket["short_title"],
            number=bucket["number"],
            num_int=bucket["num_int"],
            is_sdd=bucket["is_sdd"],
            specialties=top_specs,
            search_blob=normalize_search_text(" ".join(search_parts)),
            all_cids=all_cids,
            active_cids=bucket["active_cids"],
            suspended_cids=suspended_cids,
            mode_cids={
                MODE_ESSENTIEL: mode_ess,
                MODE_RANG_A: mode_rang_a,
                MODE_COMPLET: mode_complet,
            },
            mode_to_unlock_cids={
                MODE_ESSENTIEL: mode_ess & suspended_cids,
                MODE_RANG_A: mode_rang_a & suspended_cids,
                MODE_COMPLET: mode_complet & suspended_cids,
            },
            card_meta=card_meta,
        )
        entries.append(entry)

    entries.sort(key=lambda it: (1 if it.is_sdd else 0, it.num_int, it.title))
    return entries


def search_edn_items(items: List[EdnItemEntry], query: str) -> List[EdnItemEntry]:
    """
    Filtre et classe les items par numéro ou intitulé (ex. '145', '152', 'Endocardite').
    Priorise les correspondances exactes sur le numéro d'item puis l'intitulé.
    """
    q_norm = normalize_search_text(query)
    if not q_norm:
        return list(items)

    tokens = [tok for tok in q_norm.split() if tok not in ("item", "n", "no")]
    if not tokens:
        tokens = q_norm.split()

    q_num = q_norm.lstrip("0") if q_norm.isdigit() else None
    scored: List[Tuple[Tuple[int, int, int, str], EdnItemEntry]] = []

    for it in items:
        if not all(tok in it.search_blob for tok in tokens):
            continue

        title_norm = normalize_search_text(it.short_title)
        full_title_norm = normalize_search_text(it.title)
        it_num_clean = it.number.lstrip("0") if it.number.isdigit() else it.number.lower()

        if q_num and not it.is_sdd and it_num_clean == q_num:
            prio = 0
        elif q_num and not it.is_sdd and it_num_clean.startswith(q_num):
            prio = 1
        elif title_norm.startswith(q_norm) or full_title_norm.startswith(q_norm):
            prio = 2
        elif q_norm in title_norm:
            prio = 3
        else:
            prio = 4

        scored.append(((prio, 1 if it.is_sdd else 0, it.num_int, it.title), it))

    scored.sort(key=lambda pair: pair[0])
    return [pair[1] for pair in scored]


# ─────────────────────────────────────────────────────────────────────────────
# TRI SCAFFOLDING NATIF & DEBLOCAGE DES CARTES
# ─────────────────────────────────────────────────────────────────────────────

def compute_scaffolding_order(
    col,
    cids: List[int],
    item_entry: Optional[EdnItemEntry] = None,
) -> Tuple[List[int], Dict[int, int]]:
    """
    Calcule l'ordre pédagogique « Scaffolding » sur une liste de card_ids :
      0. Carte Sommaire (Syndrome, Main / Hub, Sommaire)
      1. Définitions et Sémiologie (Sémiologie, Définitions, Signes cliniques, Étiologies)
      2. Examens complémentaires (Paraclinique, Biologie, Imagerie, Diagnostic positif)
      3. Thérapeutique / Scores (Traitement, Antibiothérapie, Scores, Classifications)
    À palier égal : Rang A avant Rang B, puis score d'accessibilité Anki_Smart_Queue décroissant.
    Retourne (sorted_cids, tier_breakdown).
    """
    if not cids:
        return [], {0: 0, 1: 0, 2: 0, 3: 0}

    meta_map: Dict[int, Dict[str, Any]] = {}
    missing_cids: List[int] = []
    for cid in cids:
        if item_entry and cid in item_entry.card_meta:
            meta_map[cid] = item_entry.card_meta[cid]
        else:
            missing_cids.append(cid)

    if missing_cids and col is not None:
        notetype_names = {}
        try:
            for m in col.models.all():
                notetype_names[int(m["id"])] = str(m.get("name", ""))
        except Exception:
            pass

        main_targets, outgoing_counts = _build_main_and_outgoing_index(col)
        weights, avgs = _load_smart_queue_weights()

        placeholders = ",".join(str(int(c)) for c in missing_cids)
        rows = col.db.all(f"""
            SELECT c.id, c.nid, c.ord, c.type, c.queue, c.due, n.mid, n.tags, n.flds
            FROM cards c
            JOIN notes n ON c.nid = n.id
            WHERE c.id IN ({placeholders})
        """)
        for cid, nid, card_ord, c_type, c_queue, c_due, mid, tags_str, flds_str in rows:
            m_info = classify_edn_note(
                flds_str=flds_str,
                tags_str=tags_str,
                notetype_name=notetype_names.get(mid, ""),
                is_main_target=(nid in main_targets),
                outgoing_links_count=outgoing_counts.get(nid, 0),
                weights=weights,
                avgs=avgs,
            )
            meta_map[cid] = {
                **m_info,
                "card_ord": card_ord,
                "card_type": c_type,
                "card_queue": c_queue,
                "card_due": c_due,
            }

    rank_priority = {"A": 0, "B": 1, "other": 2}

    def sort_key(cid: int) -> Tuple[int, int, int, float, int, int]:
        m = meta_map.get(cid)
        if not m:
            return (9, 9, 9, 0.0, 0, cid)
        return (
            int(m["scaffolding_tier"]),
            int(m["tier_suborder"]),
            rank_priority.get(m["rank"], 2),
            -float(m["smart_queue_score"]),
            int(m.get("card_ord", 0)),
            cid,
        )

    sorted_cids = sorted([c for c in cids if c in meta_map], key=sort_key)
    # Préserver d'éventuels cids absents de meta_map en fin de file
    for c in cids:
        if c not in meta_map:
            sorted_cids.append(c)

    breakdown = {
        TIER_SOMMAIRE: 0,
        TIER_DEFINITIONS_SEMIO: 0,
        TIER_EXAMENS: 0,
        TIER_THERAPEUTIQUE_SCORES: 0,
    }
    for cid in sorted_cids:
        m = meta_map.get(cid)
        if m:
            t = m["scaffolding_tier"]
            breakdown[t] = breakdown.get(t, 0) + 1

    return sorted_cids, breakdown


def _reposition_new_cards_safe(col, sorted_cids: List[int], starting_from: int = 0) -> None:
    """Repositionne les nouvelles cartes en tête de file dans l'ordre Scaffolding exact."""
    if not col or not sorted_cids:
        return
    try:
        col.sched.reposition_new_cards(
            card_ids=sorted_cids,
            starting_from=starting_from,
            step_size=1,
            randomize=False,
            shift_existing=True,
        )
    except TypeError:
        # Compatibilité éventuelle si l'ordre positionnel diffère
        col.sched.reposition_new_cards(sorted_cids, starting_from, 1, False, True)
    except Exception as e:
        log_error(f"Repositionnement via sched échoué ({e}), repli SQLite direct.")
        for idx, cid in enumerate(sorted_cids):
            col.db.execute(
                "UPDATE cards SET due = ?, usn = -1 WHERE id = ? AND type = 0",
                starting_from + idx,
                cid,
            )


def scaffolding_sort_cards(
    col,
    cids: List[int],
    item_entry: Optional[EdnItemEntry] = None,
    starting_from: int = 0,
) -> Dict[str, Any]:
    """
    Filtre les cartes nouvelles actives parmi `cids`, les trie selon le Scaffolding
    pédagogique (Sommaire -> Définitions & Sémiologie -> Examens complémentaires -> Thérapeutique/Scores)
    et les place en tête de file (dès `starting_from`).
    """
    if not col or not cids:
        return {"sorted_cids": [], "sorted_count": 0, "tier_breakdown": {0: 0, 1: 0, 2: 0, 3: 0}}

    placeholders = ",".join(str(int(c)) for c in cids)
    # type == 0 : carte nouvelle, queue == 0 : active (non suspendue)
    new_active_cids = col.db.list(
        f"SELECT id FROM cards WHERE id IN ({placeholders}) AND type = 0 AND queue = 0"
    )
    if not new_active_cids:
        return {"sorted_cids": [], "sorted_count": 0, "tier_breakdown": {0: 0, 1: 0, 2: 0, 3: 0}}

    sorted_cids, breakdown = compute_scaffolding_order(col, new_active_cids, item_entry=item_entry)
    _reposition_new_cards_safe(col, sorted_cids, starting_from=starting_from)

    return {
        "sorted_cids": sorted_cids,
        "sorted_count": len(sorted_cids),
        "tier_breakdown": breakdown,
    }


def put_cards_in_learn_now(col, ordered_cids: List[int]) -> int:
    """
    Place les cartes nouvelles actives (`type == 0, queue == 0`) de `ordered_cids`
    directement dans la file d'apprentissage immédiat (« Learn Now », `type=1, queue=1`).

    Point critique sur l'ordre :
    Anki trie les cartes en apprentissage (`queue = 1`) par `due` croissant (`due ASC`).
    Si on affectait un `due` décroissant ou si on appelait « Learn Now » en boucle sans
    inverser les timestamps, l'ordre serait inversé à l'étude.
    On attribue donc `due = now - (n - 1 - idx)` pour que `ordered_cids[0]` ait le plus
    petit timestamp (étudié en 1er) et `ordered_cids[-1]` ait `now` (étudié en dernier),
    tout en restant tous immédiatement dus (`<= now`).
    """
    if not col or not ordered_cids:
        return 0

    cards_to_learn = []
    for cid in ordered_cids:
        try:
            card = col.get_card(cid)
        except Exception:
            continue
        if getattr(card, "type", None) == 0 and getattr(card, "queue", None) == 0:
            cards_to_learn.append(card)

    n = len(cards_to_learn)
    if n == 0:
        return 0

    now = int(time.time())
    for idx, card in enumerate(cards_to_learn):
        deck_id = card.odid if getattr(card, "odid", 0) > 0 else card.did
        conf: Dict[str, Any] = {}
        try:
            conf = col.decks.config_dict_for_deck_id(deck_id) or {}
        except Exception:
            conf = {}
        new_conf = conf.get("new") or {}
        delays = new_conf.get("delays") or [1, 10]
        reps_left = max(1, len(delays))
        initial_factor = int(new_conf.get("initialFactor") or 2500)

        card.type = 1
        card.queue = 1
        card.ivl = 0
        if hasattr(card, "original_position"):
            card.original_position = card.odue if getattr(card, "odid", 0) else card.due
        # Ordre croissant strict : idx=0 a le plus petit `due` -> présenté en premier
        card.due = now - (n - 1 - idx)
        card.left = reps_left * 1000 + reps_left
        card.reps = 0
        card.lapses = 0
        card.factor = initial_factor

    if hasattr(col, "update_cards"):
        col.update_cards(cards_to_learn)
    else:
        for card in cards_to_learn:
            col.update_card(card)

    return n


def unlock_studied_item(
    col,
    item_entry: EdnItemEntry,
    mode: str = MODE_ESSENTIEL,
    apply_scaffolding: bool = True,
    learn_now: bool = True,
    rebuild_filtered: bool = True,
    starting_from: int = 0,
    unsuspend: bool = True,
) -> Dict[str, Any]:
    """
    Débloque (si `unsuspend=True`) les cartes suspendues de `item_entry` correspondant à `mode`,
    applique éventuellement le tri « Scaffolding » aux nouvelles cartes actives de cet item,
    et les place si demandé en apprentissage immédiat (« Learn Now ») dans le bon ordre.

    Lorsque `unsuspend=False`, aucune carte n'est débloquée : le tri Scaffolding (et Learn Now)
    s'applique uniquement aux nouvelles cartes déjà actives de l'item (ex. débloquées manuellement).
    """
    if col is None:
        if mw is None or mw.col is None:
            return {"success": False, "error": "Collection non disponible"}
        col = mw.col

    if mode not in (MODE_ESSENTIEL, MODE_RANG_A, MODE_COMPLET):
        mode = MODE_ESSENTIEL

    if unsuspend:
        target_cids = sorted(item_entry.mode_cids.get(mode, set()))
        to_unsuspend = sorted(item_entry.mode_to_unlock_cids.get(mode, set()))
    else:
        target_cids = sorted(item_entry.all_cids)
        to_unsuspend = []

    if to_unsuspend:
        col.sched.unsuspend_cards(to_unsuspend)

    sort_res = {
        "sorted_cids": [],
        "sorted_count": 0,
        "tier_breakdown": {0: 0, 1: 0, 2: 0, 3: 0},
    }
    if apply_scaffolding and target_cids:
        sort_res = scaffolding_sort_cards(
            col=col,
            cids=target_cids,
            item_entry=item_entry,
            starting_from=starting_from,
        )

    learn_now_count = 0
    if learn_now and target_cids:
        ordered_for_learn = list(sort_res["sorted_cids"])
        if not ordered_for_learn:
            placeholders = ",".join(str(int(c)) for c in target_cids)
            ordered_for_learn = col.db.list(
                f"SELECT id FROM cards WHERE id IN ({placeholders}) "
                f"AND type = 0 AND queue = 0 ORDER BY due ASC, id ASC"
            )
        learn_now_count = put_cards_in_learn_now(col, ordered_for_learn)

    rebuilt_filtered = 0
    if rebuild_filtered:
        try:
            reb = rebuild_all_edn_filtered_decks(col=col)
            rebuilt_filtered = int(reb.get("count", 0))
        except Exception as e:
            log_error(f"Erreur reconstruction paquets filtrés après déblocage : {e}")

    log(
        f"Item débloqué ({item_entry.title}, mode={mode}) : "
        f"{len(to_unsuspend)} débloquées, {sort_res['sorted_count']} nouvelles triées (Scaffolding), "
        f"{learn_now_count} en apprentissage immédiat (Learn Now)."
    )

    return {
        "success": True,
        "item_key": item_entry.key,
        "item_title": item_entry.title,
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "unsuspended_count": len(to_unsuspend),
        "total_mode_cards": len(target_cids),
        "already_active_count": max(0, len(target_cids) - len(to_unsuspend)),
        "sorted_new_count": sort_res["sorted_count"],
        "sorted_cids": sort_res["sorted_cids"],
        "learn_now_count": learn_now_count,
        "tier_breakdown": sort_res["tier_breakdown"],
        "rebuilt_filtered_decks": rebuilt_filtered,
    }


# ─────────────────────────────────────────────────────────────────────────────
# THEME & INTERFACE GRAPHIQUE (ZERO EMOJI, STYLES SCOPES, PROTECTION TOOLTIPS)
# ─────────────────────────────────────────────────────────────────────────────

def _is_dark_mode() -> bool:
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
    if app:
        return app.palette().color(app.palette().ColorRole.Window).lightness() < 128
    return False


def _get_unlock_theme_colors(is_dark: bool) -> Dict[str, Any]:
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
            "selection_bg": "#1c385c",
            "selection_text": "#79b8ff",
            "success_bg": "#0f2e22",
            "success_border": "#34d399",
            "success_text": "#a7f3d0",
            "tooltip_bg": "#2b2b2b",
            "tooltip_text": "#ffffff",
            "tooltip_border": "#555555",
        }
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
        "selection_bg": "#eff6ff",
        "selection_text": "#0969da",
        "success_bg": "#ecfdf5",
        "success_border": "#10b981",
        "success_text": "#065f46",
        "tooltip_bg": "#2b2b2b",
        "tooltip_text": "#ffffff",
        "tooltip_border": "#555555",
    }


def _build_unlock_dialog_qss(c: Dict[str, Any]) -> str:
    """Feuille de style QSS scopée à QDialog#unlockItemDialog avec protection des tooltips."""
    return f"""
    QDialog#unlockItemDialog {{
        background-color: {c['bg_window']};
        color: {c['text_primary']};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
    }}
    QDialog#unlockItemDialog QLabel {{
        color: {c['text_primary']};
        background: transparent;
    }}
    QDialog#unlockItemDialog QLabel#DialogTitle {{
        font-size: 16px;
        font-weight: 700;
        color: {c['accent']};
    }}
    QDialog#unlockItemDialog QLabel#DialogSubtitle {{
        font-size: 12.5px;
        color: {c['text_secondary']};
    }}
    QDialog#unlockItemDialog QLabel#SectionTitle {{
        font-size: 12.5px;
        font-weight: 600;
        color: {c['text_primary']};
    }}
    QDialog#unlockItemDialog QLabel#MutedLabel {{
        font-size: 12px;
        color: {c['text_secondary']};
    }}
    QDialog#unlockItemDialog QLineEdit {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 11px;
        font-size: 13px;
    }}
    QDialog#unlockItemDialog QLineEdit:focus {{
        border: 1px solid {c['accent']};
    }}
    QDialog#unlockItemDialog QTreeWidget {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        outline: none;
    }}
    QDialog#unlockItemDialog QTreeWidget::item {{
        padding: 6px 4px;
        border-bottom: 1px solid {c['border_subtle']};
    }}
    QDialog#unlockItemDialog QTreeWidget::item:hover {{
        background-color: {c['bg_subtle']};
    }}
    QDialog#unlockItemDialog QTreeWidget::item:selected {{
        background-color: {c['selection_bg']};
        color: {c['selection_text']};
    }}
    QDialog#unlockItemDialog QHeaderView::section {{
        background-color: {c['bg_subtle']};
        color: {c['text_secondary']};
        padding: 6px 10px;
        border: none;
        border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border']};
        font-weight: 600;
        font-size: 12px;
    }}
    QDialog#unlockItemDialog QFrame#SelectedItemHeader {{
        background-color: {c['bg_card']};
        border: 1px solid {c['border']};
        border-radius: 6px;
    }}
    QDialog#unlockItemDialog QLabel#SelectedItemTitle {{
        font-size: 13.5px;
        font-weight: 700;
        color: {c['text_primary']};
    }}
    QDialog#unlockItemDialog QFrame#ModeCard {{
        background-color: {c['bg_card']};
        border: 1px solid {c['border']};
        border-radius: 6px;
    }}
    QDialog#unlockItemDialog QFrame#ModeCardSelected {{
        background-color: {c['accent_subtle']};
        border: 1px solid {c['accent']};
        border-left: 4px solid {c['accent']};
        border-radius: 6px;
    }}
    QDialog#unlockItemDialog QFrame#ScaffoldingBox {{
        background-color: {c['bg_card']};
        border: 1px solid {c['border']};
        border-radius: 6px;
    }}
    QDialog#unlockItemDialog QFrame#FeedbackBanner {{
        background-color: {c['success_bg']};
        border: 1px solid {c['success_border']};
        border-left: 4px solid {c['success_border']};
        border-radius: 6px;
    }}
    QDialog#unlockItemDialog QLabel#FeedbackLabel {{
        color: {c['success_text']};
        font-size: 12.5px;
        font-weight: 600;
    }}
    QDialog#unlockItemDialog QRadioButton {{
        color: {c['text_primary']};
        font-weight: 600;
        font-size: 13px;
        spacing: 8px;
        background: transparent;
    }}
    QDialog#unlockItemDialog QCheckBox {{
        color: {c['text_primary']};
        font-weight: 600;
        font-size: 12.5px;
        spacing: 8px;
        background: transparent;
    }}
    QDialog#unlockItemDialog QLabel#CountBadge {{
        background-color: {c['bg_subtle']};
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QDialog#unlockItemDialog QLabel#CountBadgeActive {{
        background-color: {c['accent_subtle']};
        color: {c['accent']};
        border: 1px solid {c['accent']};
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11.5px;
        font-weight: 600;
    }}
    QDialog#unlockItemDialog QPushButton {{
        background-color: {c['bg_card']};
        color: {c['text_primary']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 7px 14px;
        font-weight: 500;
        font-size: 13px;
    }}
    QDialog#unlockItemDialog QPushButton:hover {{
        background-color: {c['bg_subtle']};
    }}
    QDialog#unlockItemDialog QPushButton:disabled {{
        background-color: {c['bg_subtle']};
        color: {c['text_muted']};
        border-color: {c['border']};
    }}
    QDialog#unlockItemDialog QPushButton#PrimaryButton {{
        background-color: {c['accent']};
        color: {c['accent_text']};
        border: 1px solid {c['accent']};
        font-weight: 600;
        padding: 8px 18px;
    }}
    QDialog#unlockItemDialog QPushButton#PrimaryButton:hover {{
        background-color: {c['accent_hover']};
        border-color: {c['accent_hover']};
    }}
    QDialog#unlockItemDialog QPushButton#PrimaryButton:disabled {{
        background-color: {c['bg_subtle']};
        color: {c['text_muted']};
        border-color: {c['border']};
    }}
    QToolTip, CustomLabel, QLabel[customTooltip="true"] {{
        background-color: {c['tooltip_bg']};
        color: {c['tooltip_text']};
        border: 1px solid {c['tooltip_border']};
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
    }}
    """


class _ModeOptionCard(QFrame):
    """Carte cliquable présentant un mode de déblocage progressif et son compteur."""

    def __init__(self, mode_id: str, title: str, description: str, parent=None):
        super().__init__(parent)
        self.mode_id = mode_id
        self.setObjectName("ModeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 9, 12, 9)
        outer.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(2)

        self.radio = QRadioButton(title)
        left.addWidget(self.radio)

        self.desc_label = QLabel(description)
        self.desc_label.setObjectName("MutedLabel")
        self.desc_label.setWordWrap(True)
        self.desc_label.setContentsMargins(24, 0, 0, 0)
        left.addWidget(self.desc_label)

        outer.addLayout(left, 1)

        self.badge_label = QLabel("0 carte")
        self.badge_label.setObjectName("CountBadge")
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.badge_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.radio.setChecked(True)
        super().mousePressEvent(event)

    def set_selected_visual(self, selected: bool):
        self.setObjectName("ModeCardSelected" if selected else "ModeCard")
        self.style().unpolish(self)
        self.style().polish(self)

    def update_counts(self, to_unlock: int, total_mode: int, already_active: int):
        if to_unlock > 0:
            self.badge_label.setText(f"+{to_unlock} à débloquer ({total_mode} total)")
            self.badge_label.setObjectName("CountBadgeActive")
        elif total_mode > 0:
            self.badge_label.setText(f"Déjà actif ({already_active}/{total_mode})")
            self.badge_label.setObjectName("CountBadge")
        else:
            self.badge_label.setText("0 carte")
            self.badge_label.setObjectName("CountBadge")
        self.badge_label.style().unpolish(self.badge_label)
        self.badge_label.style().polish(self.badge_label)


class UnlockItemDialog(QDialog):
    """Boîte de dialogue intuitive pour débloquer un item étudié avec tri Scaffolding."""

    def __init__(self, parent=None, col=None, initial_query: str = ""):
        super().__init__(parent or mw)
        self.col = col if col is not None else (mw.col if mw else None)
        self.setObjectName("unlockItemDialog")
        self.setWindowTitle("Débloquer un item étudié - Anki EDN")
        self.resize(980, 620)
        self.setMinimumSize(860, 560)

        self.all_items: List[EdnItemEntry] = []
        self.filtered_items: List[EdnItemEntry] = []
        self.selected_item: Optional[EdnItemEntry] = None
        self.did_unlock: bool = False

        self._setup_ui()
        self.update_theme()
        self.reload_items(initial_query=initial_query)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # En-tête
        title_lbl = QLabel("Débloquer un item étudié")
        title_lbl.setObjectName("DialogTitle")
        main_layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Outil réclamé par la communauté pour débloquer et ordonner rapidement un item. "
            "Nous vous encourageons toutefois à suivre le tutoriel : aller dans « Parcourir » "
            "et sélectionner vous-même les cartes à apprendre."
        )
        sub_lbl.setObjectName("DialogSubtitle")
        sub_lbl.setWordWrap(True)
        main_layout.addWidget(sub_lbl)

        # Corps en 2 colonnes (recherche + liste à gauche | réglages + action à droite)
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        # --- Colonne gauche : recherche + liste ---
        left_col = QVBoxLayout()
        left_col.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher (ex. 145, 182, Endocardite, HTA)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.on_search_changed)
        search_row.addWidget(self.search_input, 1)

        self.match_count_label = QLabel("")
        self.match_count_label.setObjectName("MutedLabel")
        search_row.addWidget(self.match_count_label)
        left_col.addLayout(search_row)

        self.items_tree = QTreeWidget()
        self.items_tree.setHeaderLabels(["Item / SDD", "Discipline", "Actives"])
        self.items_tree.setRootIsDecorated(False)
        self.items_tree.setUniformRowHeights(True)
        self.items_tree.setAlternatingRowColors(False)
        self.items_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.items_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.items_tree.currentItemChanged.connect(self.on_item_selected)
        self.items_tree.itemDoubleClicked.connect(lambda *_: self.on_unlock_clicked())
        left_col.addWidget(self.items_tree, 1)

        content_row.addLayout(left_col, 11)

        # --- Colonne droite : fiche item + 3 modes + Scaffolding + bannière ---
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        self.selected_header_box = QFrame()
        self.selected_header_box.setObjectName("SelectedItemHeader")
        sel_hdr_layout = QVBoxLayout(self.selected_header_box)
        sel_hdr_layout.setContentsMargins(12, 10, 12, 10)
        sel_hdr_layout.setSpacing(3)

        self.selected_title_label = QLabel("Aucun item sélectionné")
        self.selected_title_label.setObjectName("SelectedItemTitle")
        self.selected_title_label.setWordWrap(True)
        sel_hdr_layout.addWidget(self.selected_title_label)

        self.selected_meta_label = QLabel("Sélectionnez un item dans la liste de gauche.")
        self.selected_meta_label.setObjectName("MutedLabel")
        self.selected_meta_label.setWordWrap(True)
        sel_hdr_layout.addWidget(self.selected_meta_label)

        right_col.addWidget(self.selected_header_box)

        mode_header = QLabel("Mode de déblocage progressif")
        mode_header.setObjectName("SectionTitle")
        right_col.addWidget(mode_header)

        self.mode_group = QButtonGroup(self)
        self.mode_cards: Dict[str, _ModeOptionCard] = {}

        modes_spec = [
            (
                MODE_ESSENTIEL,
                "Essentiel (Sommaires + Tombé + Rang A)",
                "Pour commencer sans se noyer : cartes Sommaires, cartes tombées, définitions et sémiologie de Rang A.",
            ),
            (
                MODE_RANG_A,
                "Rang A complet",
                "Toutes les cartes Sommaires, les cartes tombées et l'intégralité des connaissances indispensables de Rang A.",
            ),
            (
                MODE_COMPLET,
                "Item complet",
                "L'intégralité des cartes de l'item (tous rangs et cartes sans rang).",
            ),
        ]
        for idx, (m_id, m_title, m_desc) in enumerate(modes_spec):
            card = _ModeOptionCard(m_id, m_title, m_desc, parent=self)
            self.mode_group.addButton(card.radio, idx)
            self.mode_cards[m_id] = card
            right_col.addWidget(card)

        # Encart Scaffolding
        scaff_box = QFrame()
        scaff_box.setObjectName("ScaffoldingBox")
        scaff_layout = QVBoxLayout(scaff_box)
        scaff_layout.setContentsMargins(12, 10, 12, 10)
        scaff_layout.setSpacing(5)

        self.scaffolding_cb = QCheckBox(
            "Activer le tri pédagogique « Scaffolding »"
        )
        self.scaffolding_cb.setChecked(True)
        self.scaffolding_cb.toggled.connect(self._update_action_state)
        scaff_layout.addWidget(self.scaffolding_cb)

        self.scaffolding_preview_label = QLabel(
            "1. Sommaire  ->  2. Définitions & Sémiologie\n"
            "3. Examens complémentaires  ->  4. Thérapeutique & Scores"
        )
        self.scaffolding_preview_label.setObjectName("MutedLabel")
        self.scaffolding_preview_label.setWordWrap(True)
        self.scaffolding_preview_label.setContentsMargins(24, 0, 0, 0)
        scaff_layout.addWidget(self.scaffolding_preview_label)

        self.learn_now_cb = QCheckBox(
            "Mettre immédiatement en apprentissage (« Learn Now »)"
        )
        self.learn_now_cb.setChecked(True)
        self.learn_now_cb.setToolTip(
            "Place les nouvelles cartes débloquées directement en file d'apprentissage immédiat "
            "(sans limite journalière), en conservant l'ordre exact du Scaffolding."
        )
        self.learn_now_cb.toggled.connect(self._update_action_state)
        scaff_layout.addWidget(self.learn_now_cb)

        right_col.addWidget(scaff_box)

        # Bannière de confirmation inline (remplace la bulle noire flottante)
        self.feedback_banner = QFrame()
        self.feedback_banner.setObjectName("FeedbackBanner")
        fb_layout = QHBoxLayout(self.feedback_banner)
        fb_layout.setContentsMargins(12, 8, 12, 8)
        self.feedback_label = QLabel("")
        self.feedback_label.setObjectName("FeedbackLabel")
        self.feedback_label.setWordWrap(True)
        fb_layout.addWidget(self.feedback_label, 1)
        self.feedback_banner.setVisible(False)
        right_col.addWidget(self.feedback_banner)

        right_col.addStretch(1)
        content_row.addLayout(right_col, 12)
        main_layout.addLayout(content_row, 1)

        # Barre inférieure
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.close_btn = QPushButton("Fermer")
        self.close_btn.clicked.connect(self.reject)
        footer.addWidget(self.close_btn)

        self.filtered_decks_btn = QPushButton("Générateur de paquets filtrés...")
        self.filtered_decks_btn.setToolTip(
            "Ouvrir le générateur de paquets filtrés (pré-filtré sur l'item sélectionné) "
            "pour organiser ou régénérer vos sous-paquets."
        )
        self.filtered_decks_btn.clicked.connect(self.on_open_filtered_decks_clicked)
        footer.addWidget(self.filtered_decks_btn)

        footer.addStretch()

        self.scaffold_only_btn = QPushButton("Scaffolder sans débloquer")
        self.scaffold_only_btn.setToolTip(
            "Applique le tri Scaffolding (et Learn Now si coché) uniquement aux nouvelles cartes "
            "déjà actives de cet item (ex. débloquées manuellement dans Parcourir), sans débloquer "
            "de cartes supplémentaires."
        )
        self.scaffold_only_btn.clicked.connect(self.on_scaffold_only_clicked)
        footer.addWidget(self.scaffold_only_btn)

        self.unlock_btn = QPushButton("Débloquer et ordonner l'item")
        self.unlock_btn.setObjectName("PrimaryButton")
        self.unlock_btn.clicked.connect(self.on_unlock_clicked)
        footer.addWidget(self.unlock_btn)

        main_layout.addLayout(footer)

        # Sélection initiale et connexion des signaux après construction de tous les widgets
        self.mode_cards[MODE_ESSENTIEL].radio.setChecked(True)
        for card in self.mode_cards.values():
            card.radio.toggled.connect(self.on_mode_changed)

        self.search_input.setFocus()

    def update_theme(self, force: bool = False):
        if getattr(self, "_updating_theme", False):
            return
        is_dark = _is_dark_mode()
        if not force and hasattr(self, "_current_is_dark") and self._current_is_dark == is_dark:
            return
        self._updating_theme = True
        try:
            self._current_is_dark = is_dark
            c = _get_unlock_theme_colors(is_dark)
            self.setStyleSheet(_build_unlock_dialog_qss(c))
        finally:
            self._updating_theme = False

    def changeEvent(self, event: QEvent):
        if not getattr(self, "_updating_theme", False):
            if event.type() in (QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
                self.update_theme()
        super().changeEvent(event)

    def reload_items(self, initial_query: str = "", preserve_key: Optional[str] = None):
        if self.col is None:
            self.all_items = []
        else:
            self.all_items = get_all_edn_items(self.col)

        if initial_query and not self.search_input.text():
            self.search_input.blockSignals(True)
            self.search_input.setText(initial_query)
            self.search_input.blockSignals(False)

        self._apply_search_filter(preserve_key=preserve_key)

    def on_search_changed(self, _text: str):
        prev_key = self.selected_item.key if self.selected_item else None
        self._apply_search_filter(preserve_key=prev_key)

    def _apply_search_filter(self, preserve_key: Optional[str] = None):
        query = self.search_input.text()
        self.filtered_items = search_edn_items(self.all_items, query)

        self.items_tree.blockSignals(True)
        self.items_tree.clear()

        target_row_item: Optional[QTreeWidgetItem] = None
        for entry in self.filtered_items:
            row = QTreeWidgetItem(self.items_tree)
            row.setText(0, entry.title)
            row.setData(0, Qt.ItemDataRole.UserRole, entry)
            row.setText(1, ", ".join(entry.specialties[:2]) if entry.specialties else "EDN")
            status_txt = f"{entry.active_count} / {entry.total_count}"
            if entry.suspended_count == 0 and entry.total_count > 0:
                status_txt += " (Complet)"
            row.setText(2, status_txt)
            if preserve_key and entry.key == preserve_key:
                target_row_item = row

        if target_row_item is None and self.items_tree.topLevelItemCount() > 0:
            target_row_item = self.items_tree.topLevelItem(0)

        self.items_tree.blockSignals(False)

        total_n = len(self.all_items)
        shown_n = len(self.filtered_items)
        if query.strip():
            self.match_count_label.setText(f"{shown_n} résultat{'s' if shown_n > 1 else ''}")
        else:
            self.match_count_label.setText(f"{total_n} items indexés")

        if target_row_item is not None:
            self.items_tree.setCurrentItem(target_row_item)
            self.selected_item = target_row_item.data(0, Qt.ItemDataRole.UserRole)
        else:
            self.selected_item = None

        self._update_mode_cards_and_preview()

    def on_item_selected(self, current: Optional[QTreeWidgetItem], _prev: Optional[QTreeWidgetItem]):
        new_entry = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        prev_key = self.selected_item.key if self.selected_item else None
        new_key = new_entry.key if new_entry else None
        if prev_key != new_key and hasattr(self, "feedback_banner"):
            self.feedback_banner.setVisible(False)
        self.selected_item = new_entry
        self._update_mode_cards_and_preview()

    def current_mode(self) -> str:
        for m_id, card in self.mode_cards.items():
            if card.radio.isChecked():
                return m_id
        return MODE_ESSENTIEL

    def on_mode_changed(self):
        self._update_mode_cards_and_preview()

    def _update_mode_cards_and_preview(self):
        selected_mode = self.current_mode()
        for m_id, card in self.mode_cards.items():
            card.set_selected_visual(m_id == selected_mode)
            if self.selected_item:
                to_unlock, total_m, active_m = self.selected_item.get_mode_counts(m_id)
                card.update_counts(to_unlock, total_m, active_m)
            else:
                card.update_counts(0, 0, 0)

        self._update_action_state()

    def _update_action_state(self):
        if not self.selected_item:
            self.selected_title_label.setText("Aucun item sélectionné")
            self.selected_meta_label.setText("Sélectionnez un item dans la liste de gauche.")
            self.scaffold_only_btn.setEnabled(False)
            self.scaffold_only_btn.setText("Scaffolder sans débloquer")
            self.unlock_btn.setEnabled(False)
            self.unlock_btn.setText("Sélectionnez un item")
            self.scaffolding_preview_label.setText(
                "1. Sommaire  ->  2. Définitions & Sémiologie\n"
                "3. Examens complémentaires  ->  4. Thérapeutique & Scores"
            )
            return

        spec_str = ", ".join(self.selected_item.specialties[:3]) if self.selected_item.specialties else "EDN"
        self.selected_title_label.setText(self.selected_item.title)
        self.selected_meta_label.setText(
            f"{spec_str}  |  {self.selected_item.active_count} / {self.selected_item.total_count} cartes actives"
        )

        mode = self.current_mode()
        tiers = self.selected_item.get_tier_breakdown(mode)
        self.scaffolding_preview_label.setText(
            f"Répartition ({MODE_LABELS[mode]}) :\n"
            f"1. Sommaire ({tiers[TIER_SOMMAIRE]})  ->  2. Définitions & Sémiologie ({tiers[TIER_DEFINITIONS_SEMIO]})\n"
            f"3. Examens complémentaires ({tiers[TIER_EXAMENS]})  ->  4. Thérapeutique & Scores ({tiers[TIER_THERAPEUTIQUE_SCORES]})"
        )

        to_unlock, total_m, _ = self.selected_item.get_mode_counts(mode)
        apply_scaff = self.scaffolding_cb.isChecked()
        learn_now = self.learn_now_cb.isChecked()
        active_new_n = self.selected_item.active_new_count

        self.scaffold_only_btn.setEnabled(active_new_n > 0 and (apply_scaff or learn_now))
        if active_new_n > 0:
            if not apply_scaff and learn_now:
                self.scaffold_only_btn.setText(f"Learn Now sans débloquer ({active_new_n})")
            else:
                self.scaffold_only_btn.setText(f"Scaffolder sans débloquer ({active_new_n})")
        else:
            self.scaffold_only_btn.setText("Scaffolder sans débloquer")

        self.unlock_btn.setEnabled(to_unlock > 0 or (total_m > 0 and (apply_scaff or learn_now)))

        if to_unlock > 0:
            s_suffix = " (Scaffolding)" if apply_scaff else ""
            self.unlock_btn.setText(
                f"Débloquer {to_unlock} carte{'s' if to_unlock > 1 else ''}{s_suffix}"
            )
        elif total_m > 0 and apply_scaff:
            self.unlock_btn.setText("Appliquer le tri Scaffolding à l'item")
        elif total_m > 0 and learn_now:
            self.unlock_btn.setText("Mettre l'item en apprentissage immédiat")
        else:
            self.unlock_btn.setText("Item déjà débloqué")

    def on_unlock_clicked(self):
        self._execute_action(unsuspend=True)

    def on_scaffold_only_clicked(self):
        self._execute_action(unsuspend=False)

    def _execute_action(self, unsuspend: bool):
        if not self.selected_item or not self.col:
            return

        mode = self.current_mode()
        apply_scaff = self.scaffolding_cb.isChecked()
        learn_now = self.learn_now_cb.isChecked()

        try:
            if mw and hasattr(mw, "checkpoint"):
                action_lbl = "Déblocage" if unsuspend else "Scaffolding"
                mw.checkpoint(f"{action_lbl} {self.selected_item.title}")

            res = unlock_studied_item(
                col=self.col,
                item_entry=self.selected_item,
                mode=mode,
                apply_scaffolding=apply_scaff,
                learn_now=learn_now,
                rebuild_filtered=True,
                starting_from=0,
                unsuspend=unsuspend,
            )
            self.did_unlock = True

            current_key = self.selected_item.key
            self.reload_items(preserve_key=current_key)
            if mw:
                mw.reset()
        except Exception as e:
            log_error(f"Erreur lors du déblocage de l'item : {e}")
            if mw is not None:
                showWarning(f"Impossible de débloquer cet item : {e}", parent=self)
            else:
                raise
            return

        unsusp = res.get("unsuspended_count", 0)
        sorted_n = res.get("sorted_new_count", 0)
        learn_now_n = res.get("learn_now_count", 0)
        msg_parts = []
        if unsuspend:
            if unsusp > 0:
                msg_parts.append(f"{unsusp} carte{'s' if unsusp > 1 else ''} débloquée{'s' if unsusp > 1 else ''}")
            else:
                msg_parts.append("cartes déjà actives")
        else:
            msg_parts.append("aucune carte débloquée")
        if apply_scaff and sorted_n > 0:
            msg_parts.append(f"{sorted_n} nouvelle{'s' if sorted_n > 1 else ''} ordonnée{'s' if sorted_n > 1 else ''} en tête (Scaffolding)")
        if learn_now and learn_now_n > 0:
            msg_parts.append(f"{learn_now_n} en apprentissage immédiat (Learn Now)")
        rebuilt_n = res.get("rebuilt_filtered_decks", 0)
        if rebuilt_n > 0:
            msg_parts.append(f"{rebuilt_n} paquet{'s' if rebuilt_n > 1 else ''} filtré{'s' if rebuilt_n > 1 else ''} actualisé{'s' if rebuilt_n > 1 else ''}")
        scope_lbl = MODE_LABELS[mode] if unsuspend else "Scaffolding sans déblocage"
        self.feedback_label.setText(f"{res['item_title']} ({scope_lbl}) : {', '.join(msg_parts)}.")
        self.feedback_banner.setVisible(True)

    def on_open_filtered_decks_clicked(self):
        """Ouvre le générateur de paquets filtrés (ou y revient s'il est le parent)."""
        parent = self.parent()
        if parent is not None and hasattr(parent, "on_generate_clicked"):
            self.accept()
            return
        query = ""
        if self.selected_item is not None:
            query = self.selected_item.number or self.selected_item.short_title or self.selected_item.title
        self.accept()
        from .filtered_decks_dialog import open_filtered_decks_dialog
        open_filtered_decks_dialog(parent=mw, initial_query=query)


def show_unlock_item_dialog(parent=None, initial_query: str = "") -> bool:
    """Ouvre la fenêtre de déblocage d'item étudié et retourne True si un déblocage a eu lieu."""
    if not mw or not getattr(mw, "col", None):
        showWarning("Veuillez d'abord ouvrir un profil Anki.", parent=parent)
        return False
    dlg = UnlockItemDialog(parent=parent or mw, col=mw.col, initial_query=initial_query)
    dlg.exec()
    return dlg.did_unlock


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION ECRAN D'ACCUEIL (DECK BROWSER)
# ─────────────────────────────────────────────────────────────────────────────

HOME_BUTTON_ELEMENT_ID = "edn-unlock-item-home-bar"


def is_unlock_item_enabled() -> bool:
    """Indique si l'outil « Débloquer un item étudié » est activé dans les paramètres EDN."""
    try:
        from .card_styles import load_prefs
        return bool(load_prefs().get("enableUnlockItemTool", True))
    except Exception:
        return True


def set_unlock_item_menu_visibility(enabled: bool) -> None:
    """Met à jour la visibilité de l'entrée « Débloquer un item étudié... » dans le menu EDN."""
    if mw is None:
        return
    try:
        from .shared_menu import get_edn_menu
        menu = get_edn_menu()
        if menu is not None:
            for act in menu.actions():
                if "Débloquer un item étudié" in (act.text() or ""):
                    act.setVisible(bool(enabled))
    except Exception:
        pass


def render_deck_browser_unlock_button(stats_html: str) -> str:
    """
    Insère de façon idempotente un bouton sobre « Débloquer un item étudié »
    dans le bloc stats du DeckBrowser (hors de la balise <table> des paquets).
    """
    if HOME_BUTTON_ELEMENT_ID in (stats_html or ""):
        return stats_html or ""

    button_block = f"""
<div id="{HOME_BUTTON_ELEMENT_ID}" style="margin: 14px auto 10px auto; text-align: center;">
  <button type="button"
          onclick="pycmd('edn_unlock_item'); return false;"
          title="Rechercher un item étudié, le débloquer progressivement et appliquer le tri Scaffolding"
          style="cursor: pointer; padding: 7px 16px; border-radius: 6px; border: 1px solid var(--border, #94a3b8); background: var(--button-bg, rgba(37, 99, 235, 0.12)); color: var(--fg, inherit); font-size: 13px; font-weight: 600; font-family: inherit;">
    Débloquer un item étudié
  </button>
</div>
"""
    return f"{button_block}{stats_html or ''}"


def on_deck_browser_will_render_content(deck_browser: Any, content: Any) -> None:
    """Hook DeckBrowser : injecte le bouton « Débloquer un item étudié » sur l'écran d'accueil."""
    try:
        if not is_unlock_item_enabled():
            return
        if hasattr(content, "stats"):
            content.stats = render_deck_browser_unlock_button(content.stats or "")
    except Exception as e:
        log_error(f"Erreur injection bouton Débloquer item sur DeckBrowser : {e}")


def on_unlock_webview_js_message(handled: Tuple[bool, Any], message: str, context: Any) -> Tuple[bool, Any]:
    """Intercepte pycmd('edn_unlock_item') depuis l'écran d'accueil d'Anki."""
    if message == "edn_unlock_item":
        try:
            show_unlock_item_dialog(parent=mw)
        except Exception as e:
            log_error(f"Erreur ouverture dialogue Débloquer un item étudié : {e}")
        return (True, None)
    return handled


_UNLOCK_HOOKS_INITIALIZED = False


def init_unlock_item_hooks() -> None:
    """Enregistre les hooks DeckBrowser pour l'accès direct depuis l'écran d'accueil."""
    global _UNLOCK_HOOKS_INITIALIZED
    if _UNLOCK_HOOKS_INITIALIZED:
        return
    try:
        gui_hooks.deck_browser_will_render_content.append(on_deck_browser_will_render_content)
        gui_hooks.webview_did_receive_js_message.append(on_unlock_webview_js_message)
        _UNLOCK_HOOKS_INITIALIZED = True
        log("Hooks DeckBrowser pour 'Débloquer un item étudié' initialisés.")
    except Exception as e:
        log_error(f"Erreur initialisation hooks unlock_item : {e}")
