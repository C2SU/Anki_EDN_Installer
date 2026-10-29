"""
Module de génération automatisée et hiérarchique de paquets filtrés pour Anki EDN.
Garantit l'étanchéité totale vis-à-vis d'AnkiCollab et la gestion rigoureuse des cartes multi-taggées.
"""

import os
import re
import json
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple, Any, Callable

from aqt import mw, gui_hooks
from aqt.utils import showInfo, showWarning, tooltip

from .logger import log, log_error

ROOT_DECK_NAME = "EDN - Paquets Filtrés"

# Préfixes et mots-clés de tags à ignorer pour l'identification des spécialités
IGNORED_TAG_PREFIXES = (
    "années", "annee", "année", "1er-cycle", "2e-cycle", "3e-cycle",
    "dfasm1", "dfasm2", "dfasm3", "dfasm", "pass", "las", "paces",
    "d1", "d2", "d3", "d4", "r2c", "maj", "flag", "marked", "leech",
    "edn_nid", "source", "collèges", "colleges", "rang", "forme-compliquée",
    "grave", "iconographie", "new", "note", "img", "transport", "score", "scores",
    "edn", "ssdd", "sdd", "algorithme", "norme", "fondamentaux", "empty-nid",
    "trier", "incomplete", "dermato", "gestes", "nom-propre", "formule",
    "aigu-ou-chronique", "définition", "definition", "posologie", "marqueur",
    "ankicollab_protect", "mot-compliqué"
)

# Liste canonique ordonnée des principales disciplines de l'internat / EDN
CANONICAL_SPECIALTIES = [
    "Cardiologie",
    "Pneumologie",
    "Neurologie",
    "Gastro-entérologie",
    "Néphrologie",
    "Infectiologie",
    "Urgences",
    "Pédiatrie",
    "Gynécologie",
    "Psychiatrie",
    "Locomoteur",
    "Oncologie",
    "Dermatologie",
    "Hématologie",
    "Urologie",
    "Immunologie",
    "Endocrinologie",
    "ORL",
    "Ophtalmologie",
    "Gériatrie",
    "Santé-publique",
    "Pharmacologie",
    "MPR",
    "Douleur",
    "Sémiologie",
    "Imagerie",
    "Épidémiologie",
    "Nutrition"
]


def normalize_tag_key(tag: str) -> str:
    """Normalise un tag pour comparaison insensible à la casse et aux accents."""
    t = tag.lower().strip()
    t = t.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
    t = t.replace("à", "a").replace("â", "a").replace("î", "i").replace("ï", "i")
    t = t.replace("ô", "o").replace("ù", "u").replace("û", "u").replace("ç", "c")
    return t


def is_specialty_tag(tag: str) -> bool:
    """Vérifie si un tag correspond à une spécialité médicale candidate."""
    t = tag.lower().strip()
    if t.startswith("edn::") or t.startswith("item-") or t.startswith("item_"):
        return False
    for prefix in IGNORED_TAG_PREFIXES:
        if t == prefix or t.startswith(prefix + "::") or t.startswith(prefix + "-") or t.startswith(prefix + "_"):
            return False
    return True


def clean_specialty_name(raw_tag: str) -> str:
    """Convertit un tag brut de spécialité en libellé canonique soigné."""
    top = raw_tag.split("::")[0].strip()
    top_norm = normalize_tag_key(top)
    for canonical in CANONICAL_SPECIALTIES:
        if normalize_tag_key(canonical) == top_norm:
            return canonical
    return top.replace("-", " ").replace("_", " ").capitalize()


def clean_item_label(item_tag: str) -> Tuple[int, str]:
    """
    Extrait le numéro et génère un libellé propre d'item en préservant les acronymes médicaux.
    Exemple : 'EDN::item-224-HTA' -> (224, 'Item 224 - HTA')
    Exemple : 'EDN::item-236-Troubles-conduction::BAV' -> (236, 'Item 236 - Troubles Conduction - BAV')
    """
    tag = item_tag.strip()
    if tag.lower().startswith("edn::"):
        tag = tag[5:].strip()

    def _format_part(text: str) -> str:
        words = text.replace("-", " ").replace("_", " ").split()
        res = []
        for w in words:
            if w.isupper() and len(w) <= 6:
                res.append(w)
            else:
                res.append(w.capitalize())
        return " ".join(res)

    # Détection item et numéro
    m = re.match(r"^item[_-]?0*(\d+)[_-]?(.*)$", tag, re.IGNORECASE)
    if m:
        item_num = int(m.group(1))
        rest = m.group(2).strip()
        if rest:
            subparts = [p.strip() for p in rest.split("::") if p.strip()]
            formatted_parts = [_format_part(p) for p in subparts]
            formatted_rest = " - ".join(formatted_parts)
            return item_num, f"Item {item_num:03d} - {formatted_rest}"
        return item_num, f"Item {item_num:03d}"
    
    subparts = [p.strip() for p in tag.split("::") if p.strip()]
    return 9999, " - ".join(_format_part(p) for p in subparts)


def find_edn_deck_name(col=None) -> str:
    """Détecte dynamiquement le nom du paquet EDN principal."""
    if col is None:
        if mw is None or mw.col is None:
            return "Anki EDN"
        col = mw.col

    try:
        candidate_names = ["Anki EDN", "EDN", "EDN DFASM", "Anki-EDN"]
        for d in col.decks.all():
            name = d.get("name", "")
            for cand in candidate_names:
                if name.lower() == cand.lower():
                    return name
        for d in col.decks.all():
            name = d.get("name", "")
            if "edn" in name.lower() and not d.get("dyn", False) and not name.startswith(ROOT_DECK_NAME):
                return name
    except Exception as e:
        log_error(f"Erreur recherche deck EDN: {e}")
    return "Anki EDN"


def get_edn_deck_and_config(col=None) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[Dict[str, Any]]]:
    """
    Récupère le dictionnaire du deck EDN principal, son ID de configuration (conf)
    et le dictionnaire complet de la configuration de révision associée (preset).
    """
    if col is None:
        if mw is None or mw.col is None:
            return None, None, None
        col = mw.col

    edn_name = find_edn_deck_name(col)
    edn_did = col.decks.id_for_name(edn_name)
    if not edn_did:
        return None, None, None

    deck_dict = col.decks.get(edn_did)
    if not deck_dict:
        return None, None, None

    conf_id = deck_dict.get("conf")
    conf_dict = None
    if conf_id:
        try:
            conf_dict = col.decks.get_config(conf_id)
        except Exception:
            pass

    if not conf_dict:
        try:
            conf_dict = col.decks.config_dict_for_deck_id(edn_did)
        except Exception:
            pass

    return deck_dict, conf_id, conf_dict


def map_edn_review_order_to_filtered_order(edn_conf: Optional[Dict[str, Any]]) -> int:
    """
    Détermine l'ordre de tri pour le paquet filtré à partir des options de révision du deck EDN principal.
    Mapping officiel Anki ReviewCardOrder -> FilteredDeck SearchTerm Order :
      0: REVIEW_CARD_ORDER_DAY -> 6 (Order due)
      1: REVIEW_CARD_ORDER_DAY_THEN_DECK -> 6 (Order due)
      2: REVIEW_CARD_ORDER_DECK_THEN_DAY -> 6 (Order due)
      3: REVIEW_CARD_ORDER_INTERVALS_ASCENDING -> 2 (Increasing intervals)
      4: REVIEW_CARD_ORDER_INTERVALS_DESCENDING -> 3 (Decreasing intervals)
      5: REVIEW_CARD_ORDER_EASE_ASCENDING -> 0 (Oldest seen first)
      6: REVIEW_CARD_ORDER_EASE_DESCENDING -> 0 (Oldest seen first)
      7: REVIEW_CARD_ORDER_RETRIEVABILITY_ASCENDING -> 8 (Ascending retrievability)
      8: REVIEW_CARD_ORDER_RETRIEVABILITY_DESCENDING -> 9 (Descending retrievability)
      9: REVIEW_CARD_ORDER_RELATIVE_OVERDUENESS -> 10 (Relative overdueness)
      10: REVIEW_CARD_ORDER_RANDOM -> 1 (Random)
      11: REVIEW_CARD_ORDER_ADDED -> 5 (Order added)
      12: REVIEW_CARD_ORDER_REVERSE_ADDED -> 7 (Latest added first)
    """
    if not edn_conf:
        return 6  # Ordre d'échéance par défaut

    rev_order = edn_conf.get("reviewOrder", 0)
    mapping = {
        0: 6,
        1: 6,
        2: 6,
        3: 2,
        4: 3,
        5: 0,
        6: 0,
        7: 8,
        8: 9,
        9: 10,
        10: 1,
        11: 5,
        12: 7
    }
    return mapping.get(rev_order, 6)


def sync_hierarchy_deck_options(root_name: str = ROOT_DECK_NAME, col=None) -> int:
    """
    Applique systématiquement le groupe d'options (preset / conf) du deck EDN principal
    à tous les paquets normaux conteneurs de l'arborescence (racine et dossiers de spécialité).
    Retourne le nombre de paquets mis à jour.
    """
    if col is None:
        if mw is None or mw.col is None:
            return 0
        col = mw.col

    _, edn_conf_id, _ = get_edn_deck_and_config(col)
    if not edn_conf_id:
        return 0

    updated = 0
    prefix = root_name.lower()
    for d in col.decks.all():
        name = d.get("name", "")
        name_lower = name.lower()
        if (name_lower == prefix or name_lower.startswith(prefix + "::")) and not d.get("dyn", False):
            if d.get("conf") != edn_conf_id:
                col.decks.set_config_id_for_deck_dict(d, edn_conf_id)
                updated += 1

    if updated > 0:
        log(f"Options de révision héritées : {updated} paquet(s) conteneur(s) synchronisé(s) sur le preset EDN #{edn_conf_id}.")
    return updated


def analyze_edn_curriculum(col=None, threshold_pct: float = 40.0) -> Dict[str, Any]:
    """
    Analyse les notes EDN dans SQLite et calcule pour chaque spécialité les items
    ayant >= threshold_pct de leurs cartes portant le tag de la spécialité.
    """
    if col is None:
        if mw is None or mw.col is None:
            return {"specialties": {}, "total_items": 0, "total_notes": 0}
        col = mw.col

    db = col.db
    query = "SELECT id, tags FROM notes WHERE tags LIKE '%item-%' OR tags LIKE '%item_%'"
    rows = db.all(query)

    item_to_notes = defaultdict(set)
    item_to_specialties = defaultdict(Counter)
    all_detected_specs = Counter()

    for nid, tags_str in rows:
        if not tags_str:
            continue
        tags = [t for t in tags_str.strip().split() if t]
        
        # Tags d'items
        item_tags = [t for t in tags if re.match(r"^(?:edn::)?item[_-]\d+", t, re.IGNORECASE)]
        
        # Tags de spécialités
        spec_tags = set()
        for t in tags:
            if is_specialty_tag(t):
                spec_name = clean_specialty_name(t)
                spec_tags.add(spec_name)
                all_detected_specs[spec_name] += 1
                
        for it in item_tags:
            item_to_notes[it].add(nid)
            for sp in spec_tags:
                item_to_specialties[it][sp] += 1

    # Construction des spécialités et qualification des items
    specialties_data = {}
    for sp in CANONICAL_SPECIALTIES:
        specialties_data[sp] = {"item_count": 0, "total_cards": 0, "items": []}

    for it, spec_counts in item_to_specialties.items():
        total_notes_in_item = len(item_to_notes[it])
        item_num, label = clean_item_label(it)
        
        for sp, count in spec_counts.items():
            pct = (count / total_notes_in_item) * 100.0 if total_notes_in_item > 0 else 0.0
            if pct >= threshold_pct:
                if sp not in specialties_data:
                    specialties_data[sp] = {"item_count": 0, "total_cards": 0, "items": []}
                specialties_data[sp]["items"].append({
                    "tag": it,
                    "label": label,
                    "item_num": item_num,
                    "total_cards": total_notes_in_item,
                    "spec_cards": count,
                    "pct": pct
                })

    # Nettoyage et tri des spécialités
    final_specialties = {}
    for sp, data in specialties_data.items():
        if data["items"]:
            # Trier les items par numéro d'item
            data["items"].sort(key=lambda x: (x["item_num"], x["label"]))
            data["item_count"] = len(data["items"])
            data["total_cards"] = sum(it["spec_cards"] for it in data["items"])
            final_specialties[sp] = data

    return {
        "specialties": final_specialties,
        "total_items": len(item_to_notes),
        "total_notes": len(rows)
    }


def build_filtered_query(
    edn_deck: str,
    item_tag: str,
    specialty: Optional[str] = None,
    scope: str = "volet_matiere",
    card_filter: str = "due_and_new",
    rank_filter: str = "all"
) -> str:
    """
    Construit la syntaxe exacte de la requête de recherche pour un paquet filtré.
    Le statut par défaut est 'due_and_new' : (is:due or is:new).
    """
    parts = [f'deck:"{edn_deck}"', f'"tag:{item_tag}*"']

    # Volet matière de l'item vs Item complet
    if scope == "volet_matiere" and specialty:
        spec_norm = specialty.replace(" ", "-")
        parts.append(f'tag:{spec_norm}*')

    # Rangs A/B
    if rank_filter == "A":
        parts.append('(tag:Rang_A* or tag:rang::a*)')
    elif rank_filter == "B":
        parts.append('(tag:Rang_B* or tag:rang::b*)')

    # Filtre d'échéance / statut
    if card_filter == "due_and_new":
        # Valeur par défaut essentielle : préserve à la fois les révisions dues et les bleues (nouvelles)
        parts.append('(is:due or is:new)')
    elif card_filter == "due_only":
        parts.append('is:due')
    elif card_filter == "new_only":
        parts.append('is:new')
    # Si card_filter == "all", aucune restriction d'état n'est ajoutée

    return " ".join(parts)


def generate_filtered_hierarchy(
    selected_specialties: List[str],
    curriculum_data: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
    col=None,
    progress_callback=None,
    selected_items: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """
    Génère l'arborescence complète des paquets :
    - Paquet racine normal conteneur : 'EDN - Paquets Filtrés'
    - Paquets dossiers normaux : 'EDN - Paquets Filtrés::{Specialty}'
    - Paquets filtrés feuilles : 'EDN - Paquets Filtrés::{Specialty}::{Item_Label}'
    Si selected_items est fourni ({specialty: [item_tag, ...]}), génère uniquement les items cochés.
    """
    if col is None:
        if mw is None or mw.col is None:
            return {"success": False, "error": "Collection non disponible"}
        col = mw.col

    opts = options or {}
    root_name = opts.get("root_name", ROOT_DECK_NAME)
    scope = opts.get("scope", "volet_matiere")  # 'volet_matiere' ou 'item_complet'
    card_filter = opts.get("card_filter", "due_and_new")  # 'due_and_new' par défaut
    rank_filter = opts.get("rank_filter", "all")
    resched = opts.get("resched", True)
    rebuild = opts.get("rebuild", True)
    limit = opts.get("limit", 9999)

    edn_deck = find_edn_deck_name(col)
    edn_deck_dict, edn_conf_id, edn_conf = get_edn_deck_and_config(col)
    specialties_dict = curriculum_data.get("specialties", {})

    # Résolution de l'ordre de révision (hérité du deck EDN principal si 'inherit')
    order_opt = opts.get("order", "inherit")
    if order_opt == "inherit":
        resolved_order = map_edn_review_order_to_filtered_order(edn_conf)
    else:
        try:
            resolved_order = int(order_opt)
        except (ValueError, TypeError):
            resolved_order = 6

    created_decks = 0
    rebuilt_cards = 0

    try:
        # 1. Création sécurisée du paquet racine normal conteneur (dyn: 0)
        col.decks.add_normal_deck_with_name(root_name)
        root_did = col.decks.id_for_name(root_name)
        if root_did and edn_conf_id:
            root_deck = col.decks.get(root_did)
            if root_deck and root_deck.get("conf") != edn_conf_id:
                col.decks.set_config_id_for_deck_dict(root_deck, edn_conf_id)

        # Calculer le nombre total d'items effectifs à traiter
        total_items_to_process = 0
        for sp in selected_specialties:
            sp_data = specialties_dict.get(sp)
            if not sp_data or not sp_data.get("items"):
                continue
            if selected_items and sp in selected_items:
                allowed_tags = set(selected_items[sp])
                total_items_to_process += len([it for it in sp_data["items"] if it["tag"] in allowed_tags])
            else:
                total_items_to_process += len(sp_data["items"])

        processed = 0

        for sp in selected_specialties:
            sp_data = specialties_dict.get(sp)
            if not sp_data or not sp_data.get("items"):
                continue

            items_to_process = sp_data["items"]
            if selected_items and sp in selected_items:
                allowed_tags = set(selected_items[sp])
                items_to_process = [it for it in items_to_process if it["tag"] in allowed_tags]

            if not items_to_process:
                continue

            # 2. Création du dossier de spécialité normal conteneur (dyn: 0)
            sp_deck_name = f"{root_name}::{sp}"
            col.decks.add_normal_deck_with_name(sp_deck_name)
            sp_did = col.decks.id_for_name(sp_deck_name)
            if sp_did and edn_conf_id:
                sp_deck = col.decks.get(sp_did)
                if sp_deck and sp_deck.get("conf") != edn_conf_id:
                    col.decks.set_config_id_for_deck_dict(sp_deck, edn_conf_id)

            for item_info in items_to_process:
                item_tag = item_info["tag"]
                item_label = item_info["label"]
                leaf_deck_name = f"{sp_deck_name}::{item_label}"

                # 3. Récupération ou création du paquet filtré feuille
                did = col.decks.id_for_name(leaf_deck_name)
                if did:
                    # Vérifier si c'est bien un paquet filtré
                    if not col.decks.is_filtered(did):
                        col.decks.remove([did])
                        did = col.decks.new_filtered(leaf_deck_name)
                else:
                    did = col.decks.new_filtered(leaf_deck_name)

                # 4. Configuration de la requête de recherche
                query = build_filtered_query(
                    edn_deck=edn_deck,
                    item_tag=item_tag,
                    specialty=sp,
                    scope=scope,
                    card_filter=card_filter,
                    rank_filter=rank_filter
                )

                deck = col.decks.get(did)
                deck["terms"] = [[query, limit, resolved_order]]
                deck["resched"] = bool(resched)
                deck["delays"] = None  # Hérite des pas d'apprentissage du deck principal
                col.decks.save(deck)
                created_decks += 1

                # 5. Reconstruction optionnelle
                if rebuild:
                    try:
                        res = col.sched.rebuild_filtered_deck(did)
                        rebuilt_cards += res.count
                    except Exception as e:
                        log_error(f"Erreur reconstruction paquet {leaf_deck_name}: {e}")

                processed += 1
                if progress_callback:
                    progress_callback(processed, total_items_to_process, leaf_deck_name)

        # Harmonisation finale des options de tous les paquets conteneurs de l'arborescence
        sync_hierarchy_deck_options(root_name, col)

        preset_name = edn_conf.get("name", "Par défaut") if edn_conf else "Par défaut"
        log(f"Génération terminée : {created_decks} paquets créés/mis à jour, {rebuilt_cards} cartes réparties (Preset hérité : {preset_name}).")
        return {
            "success": True,
            "created_decks": created_decks,
            "rebuilt_cards": rebuilt_cards,
            "root_name": root_name,
            "inherited_conf_id": edn_conf_id,
            "inherited_preset_name": preset_name,
            "order_used": resolved_order
        }

    except Exception as e:
        log_error(f"Erreur lors de la génération de l'arborescence : {e}")
        return {"success": False, "error": str(e)}


def get_edn_filtered_deck_ids(root_name: str = ROOT_DECK_NAME, col=None) -> List[int]:
    """Renvoie la liste des identifiants des paquets filtrés sous l'arborescence EDN."""
    if col is None:
        import aqt
        if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None):
            col = aqt.mw.col
        elif mw and hasattr(mw, "col") and mw.col:
            col = mw.col
        else:
            return []

    prefix = root_name.lower()
    filtered_dids = []
    for d in col.decks.all():
        name = d.get("name", "").lower()
        if (name == prefix or name.startswith(prefix + "::")) and d.get("dyn", False):
            filtered_dids.append(d["id"])
    return filtered_dids


def get_active_edn_filtered_deck_ids(root_name: str = ROOT_DECK_NAME, col=None) -> List[int]:
    """
    Renvoie la liste des identifiants des paquets filtrés EDN qui contiennent
    actuellement au moins une carte (non vides).
    """
    if col is None:
        import aqt
        if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None):
            col = aqt.mw.col
        elif mw and hasattr(mw, "col") and mw.col:
            col = mw.col
        else:
            return []

    filtered_dids = get_edn_filtered_deck_ids(root_name, col)
    if not filtered_dids:
        return []

    active_ids = set()
    # Découpage par lots de 500 pour sécurité SQLite absolue
    batch_size = 500
    for i in range(0, len(filtered_dids), batch_size):
        batch = filtered_dids[i:i + batch_size]
        placeholders = ",".join("?" for _ in batch)
        res = col.db.list(
            f"SELECT DISTINCT did FROM cards WHERE did IN ({placeholders})",
            *batch
        )
        active_ids.update(res)

    return [int(did) for did in filtered_dids if did in active_ids]


def empty_all_edn_filtered_decks(root_name: str = ROOT_DECK_NAME, col=None) -> int:
    """
    Vide tous les paquets filtrés sous ROOT_DECK_NAME.
    Restaure instantanément l'ensemble des cartes dans le deck principal (odid=0).
    """
    global _EVACUATED_FILTERED_DECK_IDS
    _EVACUATED_FILTERED_DECK_IDS = None

    if col is None:
        import aqt
        if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None):
            col = aqt.mw.col
        elif mw and hasattr(mw, "col") and mw.col:
            col = mw.col
        else:
            return 0

    filtered_dids = get_edn_filtered_deck_ids(root_name, col)
    count = 0
    for did in filtered_dids:
        try:
            col.sched.empty_filtered_deck(did)
            count += 1
        except Exception as e:
            log_error(f"Erreur vidage paquet filtré {did}: {e}")

    log(f"Vidage automatique : {count} paquets filtrés EDN vidés.")
    return count


def rebuild_all_edn_filtered_decks(
    root_name: str = ROOT_DECK_NAME,
    col=None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
    deck_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Reconstruit les paquets filtrés sous ROOT_DECK_NAME.
    Si deck_ids est fourni, reconstruit uniquement ces paquets spécifiques.
    """
    if col is None:
        import aqt
        if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None):
            col = aqt.mw.col
        elif mw and hasattr(mw, "col") and mw.col:
            col = mw.col
        else:
            return {"count": 0, "total_cards": 0}

    if deck_ids is not None:
        filtered_dids = list(deck_ids)
    else:
        filtered_dids = get_edn_filtered_deck_ids(root_name, col)

    rebuilt_count = 0
    total_cards = 0
    total_decks = len(filtered_dids)
    for idx, did in enumerate(filtered_dids, 1):
        try:
            deck = col.decks.get(did, default=False)
            if not deck or not deck.get("dyn", False):
                continue
            res = col.sched.rebuild_filtered_deck(did)
            rebuilt_count += 1
            total_cards += res.count
        except Exception as e:
            log_error(f"Erreur reconstruction paquet {did}: {e}")
        if progress_callback:
            progress_callback(idx, total_decks, did)

    # Synchronisation des options de révision sur l'ensemble des conteneurs
    sync_hierarchy_deck_options(root_name, col)

    log(f"Reconstruction : {rebuilt_count} paquets reconstruits ({total_cards} cartes).")
    return {"count": rebuilt_count, "total_cards": total_cards}


def delete_all_edn_filtered_decks(root_name: str = ROOT_DECK_NAME, col=None) -> bool:
    """
    Supprime entièrement l'arborescence des paquets filtrés.
    Vide impérativement les paquets au préalable pour garantir qu'aucune carte n'est perdue.
    """
    global _EVACUATED_FILTERED_DECK_IDS
    _EVACUATED_FILTERED_DECK_IDS = None

    if col is None:
        import aqt
        if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None):
            col = aqt.mw.col
        elif mw and hasattr(mw, "col") and mw.col:
            col = mw.col
        else:
            return False

    try:
        # 1. Vider d'abord tous les paquets filtrés pour réintégrer les cartes
        empty_all_edn_filtered_decks(root_name, col)

        # 2. Trouver et supprimer le paquet racine
        root_id = col.decks.id_for_name(root_name)
        if root_id:
            col.decks.remove([root_id])
            log(f"Suppression réussie de l'arborescence '{root_name}'.")
            return True
        return False
    except Exception as e:
        log_error(f"Erreur suppression arborescence '{root_name}': {e}")
        return False


# ── Persistance des Réglages Utilisateur ──

CONFIG_KEY = "filtered_decks_settings"

DEFAULT_FILTERED_DECKS_SETTINGS: Dict[str, Any] = {
    "threshold": 40,
    "scope": "volet_matiere",
    "card_filter": "due_and_new",
    "rank_filter": "all",
    "order": "inherit",
    "resched": True,
    "auto_sync": False,
    "filter_only_selected": False,
    "selected_specs": [],
    "selected_items": {},
    "fully_checked_specs": []
}


def load_filtered_decks_settings() -> Dict[str, Any]:
    """
    Charge les derniers réglages utilisateur pour les paquets filtrés.
    Consulte en priorité la configuration partagée EDN, avec secours local.
    """
    settings = dict(DEFAULT_FILTERED_DECKS_SETTINGS)
    try:
        from .shared_menu import get_config
        cfg = get_config()
        if cfg and isinstance(cfg, dict) and CONFIG_KEY in cfg:
            stored = cfg[CONFIG_KEY]
            if isinstance(stored, dict):
                settings.update(stored)
                return settings
    except Exception as e:
        log_error(f"Erreur chargement réglages paquets filtrés (shared_menu): {e}")

    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        user_files_dir = os.path.join(cur_dir, "user_files")
        fallback_file = os.path.join(user_files_dir, "filtered_decks_settings.json")
        if os.path.exists(fallback_file):
            with open(fallback_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings.update(data)
    except Exception as e:
        log_error(f"Erreur chargement réglages paquets filtrés (fallback): {e}")

    return settings


def save_filtered_decks_settings(settings: Dict[str, Any]) -> bool:
    """
    Enregistre les derniers réglages utilisateur pour les paquets filtrés.
    Sauvegarde dans la configuration partagée EDN et en miroir dans user_files.
    """
    saved = False
    try:
        from .shared_menu import get_config, save_config
        cfg = get_config()
        if isinstance(cfg, dict):
            cfg[CONFIG_KEY] = dict(settings)
            save_config(cfg)
            saved = True
    except Exception as e:
        log_error(f"Erreur sauvegarde réglages paquets filtrés (shared_menu): {e}")

    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        user_files_dir = os.path.join(cur_dir, "user_files")
        os.makedirs(user_files_dir, exist_ok=True)
        fallback_file = os.path.join(user_files_dir, "filtered_decks_settings.json")
        with open(fallback_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        saved = True
    except Exception as e:
        log_error(f"Erreur sauvegarde réglages paquets filtrés (fallback): {e}")

    return saved


# ── Hooks de Synchronisation Sécurisée ──

_EVACUATED_FILTERED_DECK_IDS: Optional[List[int]] = None


def on_sync_will_start(col=None):
    """
    Garde-fou AnkiCollab/AnkiWeb : vider temporairement les paquets filtrés
    qui contiennent des cartes actives avant la synchronisation.
    Si les sous-paquets sont déjà vides (ex. vidés par l'utilisateur), rien n'est évacué.
    """
    global _EVACUATED_FILTERED_DECK_IDS
    _EVACUATED_FILTERED_DECK_IDS = None
    try:
        settings = load_filtered_decks_settings()
        if not settings.get("auto_sync", False):
            log("Protection AnkiCollab désactivée : vidage avant synchronisation ignoré.")
            return

        import aqt
        target_col = col or (aqt.mw.col if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None) else None)
        if target_col is None and mw and hasattr(mw, "col") and mw.col:
            target_col = mw.col
        if target_col:
            active_dids = get_active_edn_filtered_deck_ids(col=target_col)
            _EVACUATED_FILTERED_DECK_IDS = active_dids
            if active_dids:
                log(f"Synchronisation : {len(active_dids)} paquet(s) filtré(s) avec cartes actives détecté(s), vidage préventif...")
                for did in active_dids:
                    try:
                        target_col.sched.empty_filtered_deck(did)
                    except Exception as e:
                        log_error(f"Erreur vidage préventif paquet filtré {did}: {e}")
            else:
                log("Synchronisation : aucun paquet filtré actif (tous déjà vides). Aucun vidage ni reconstruction nécessaire.")
    except Exception as e:
        log_error(f"Erreur hook on_sync_will_start: {e}")


def on_sync_did_finish(col=None):
    """
    Restauration automatique : reconstruire UNIQUEMENT les paquets filtrés
    qui contenaient des cartes et avaient été évacués lors du début de la synchro.
    Si l'utilisateur avait vidé ses sous-paquets, aucun n'est reconstruit.
    """
    global _EVACUATED_FILTERED_DECK_IDS
    try:
        evacuated = _EVACUATED_FILTERED_DECK_IDS
        _EVACUATED_FILTERED_DECK_IDS = None

        if not evacuated:
            log("Fin de synchronisation : aucun paquet filtré à restaurer (arborescence vide ou vidée par l'utilisateur).")
            return

        settings = load_filtered_decks_settings()
        if not settings.get("auto_sync", False):
            return

        import aqt
        target_col = col or (aqt.mw.col if getattr(aqt, "mw", None) and getattr(aqt.mw, "col", None) else None)
        if target_col is None and mw and hasattr(mw, "col") and mw.col:
            target_col = mw.col
        if target_col:
            res = rebuild_all_edn_filtered_decks(col=target_col, deck_ids=evacuated)
            count = res.get("count", 0)
            if count > 0:
                tooltip(f"Paquets filtrés EDN restaurés après synchronisation ({count} paquet(s)).", period=2000)
    except Exception as e:
        log_error(f"Erreur hook on_sync_did_finish: {e}")


def _install_ankicollab_pull_guard():
    """Garde-fou : vider les paquets filtrés actifs avant un pull AnkiCollab direct et reconstruire après."""
    try:
        import sys
        for mod_name in ("1957538407.import_manager", "AnkiCollab.import_manager"):
            im = sys.modules.get(mod_name)
            if im and hasattr(im, "handle_pull") and not hasattr(im, "_edn_orig_handle_pull"):
                orig = im.handle_pull
                im._edn_orig_handle_pull = orig
                def wrapped_pull(*args, **kwargs):
                    active_dids = []
                    target_col = getattr(mw, "col", None) if mw else None
                    try:
                        settings = load_filtered_decks_settings()
                        if settings.get("auto_sync", False) and target_col:
                            active_dids = get_active_edn_filtered_deck_ids(col=target_col)
                            if active_dids:
                                for did in active_dids:
                                    try:
                                        target_col.sched.empty_filtered_deck(did)
                                    except Exception as e:
                                        log_error(f"Erreur vidage avant pull AnkiCollab ({did}): {e}")
                    except Exception as e:
                        log_error(f"Erreur vérification/vidage avant pull AnkiCollab: {e}")

                    try:
                        return orig(*args, **kwargs)
                    finally:
                        try:
                            if active_dids and target_col:
                                settings = load_filtered_decks_settings()
                                if settings.get("auto_sync", False):
                                    rebuild_all_edn_filtered_decks(col=target_col, deck_ids=active_dids)
                        except Exception as e:
                            log_error(f"Erreur reconstruction après pull AnkiCollab: {e}")
                im.handle_pull = wrapped_pull
                log("Garde-fou AnkiCollab installé sur import_manager.handle_pull.")
                break
    except Exception as e:
        log_error(f"Erreur installation pull guard AnkiCollab: {e}")


_HOOKS_INSTALLED = False

def init_filtered_decks():
    """Initialise le module et installe les écouteurs de synchronisation."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    
    gui_hooks.sync_will_start.append(on_sync_will_start)
    gui_hooks.sync_did_finish.append(on_sync_did_finish)
    _install_ankicollab_pull_guard()
    try:
        gui_hooks.main_window_did_init.append(_install_ankicollab_pull_guard)
    except Exception:
        pass
    _HOOKS_INSTALLED = True
    log("Module Paquets Filtrés EDN initialisé (hooks de synchronisation actifs).")
