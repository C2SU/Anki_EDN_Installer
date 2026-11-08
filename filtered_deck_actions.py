"""
Module d'actions rapides pour les paquets filtrés EDN (Anki_EDN_Installer).
Ajoute un bandeau sobre directement dans la page d'aperçu (Overview) du paquet filtré :
- 'Voir dans l'explorateur' (affiche toutes les cartes de l'item / volet)
- 'Dé-suspendre rangs A' (dé-suspend uniquement les cartes de rang A et régénère)
- 'Dé-suspendre tout' (dé-suspend toutes les cartes de l'item et régénère)
"""

import re
import html
from typing import Optional, Tuple, List, Any

from aqt import mw, gui_hooks
from aqt.utils import tooltip, showWarning
from aqt.overview import Overview, OverviewContent

from .logger import log, log_error
from .filtered_decks import ROOT_DECK_NAME


def is_edn_filtered_deck(deck: Optional[dict]) -> bool:
    """Vérifie si un paquet est un paquet filtré feuille issu de la hiérarchie EDN."""
    if not deck or not deck.get("dyn", False):
        return False
    name = deck.get("name", "")
    return name.startswith(ROOT_DECK_NAME) or ("EDN - Paquets Filtrés" in name)


def extract_action_queries(deck: dict) -> Optional[Tuple[str, str, str]]:
    """
    Extrait les requêtes de recherche depuis les termes du paquet filtré :
    Retourne (query_browser, query_rank_a_suspended, query_all_suspended).
    """
    terms = deck.get("terms", [])
    if not terms or not terms[0] or not terms[0][0]:
        return None

    raw_query = terms[0][0]

    # 1. Nettoyer les clauses de statut / échéance
    base = re.sub(
        r'\(is:due\s+or\s+is:new\)|is:due|is:new|is:suspended',
        '',
        raw_query,
        flags=re.IGNORECASE
    )

    # 2. Nettoyer les filtres de rang préexistants pour retrouver la base neutre de l'item
    base_no_rank = re.sub(
        r'\(tag:Rang_[ABC]\*\s+or\s+tag:rang::[abc]\*\)',
        '',
        base,
        flags=re.IGNORECASE
    )

    clean_base = " ".join(base_no_rank.split())
    if not clean_base:
        return None

    query_browser = clean_base
    query_rank_a_suspended = f"{clean_base} (tag:Rang_A* or tag:rang::a*) is:suspended"
    query_all_suspended = f"{clean_base} is:suspended"

    return query_browser, query_rank_a_suspended, query_all_suspended


def get_suspended_counts(col, query_rank_a_suspended: str, query_all_suspended: str) -> Tuple[int, int]:
    """Compte le nombre de cartes suspendues pour les rangs A et pour tout l'item."""
    if not col:
        return (0, 0)
    try:
        count_a = len(col.find_cards(query_rank_a_suspended))
        count_all = len(col.find_cards(query_all_suspended))
        return (count_a, count_all)
    except Exception as e:
        log_error(f"Erreur calcul compteurs cartes suspendues: {e}")
        return (0, 0)


def render_action_panel(count_a: int, count_all: int) -> str:
    """Génère l'encart HTML/CSS sobre des actions rapides EDN (conforme kill-ai-slop)."""
    disabled_a = 'disabled="disabled"' if count_a == 0 else ""
    disabled_all = 'disabled="disabled"' if count_all == 0 else ""

    title_a = "Aucune carte de rang A suspendue restante" if count_a == 0 else f"Dé-suspendre les {count_a} carte(s) de rang A"
    title_all = "Aucune carte suspendue restante" if count_all == 0 else f"Dé-suspendre les {count_all} carte(s) suspendue(s)"

    return f"""
<style>
.edn-actions-card {{
  margin: 22px auto 12px auto;
  max-width: 540px;
  padding: 14px 18px;
  background-color: var(--canvas-elevated, #fcfcfc);
  border: 1px solid var(--border-subtle, #e0e0e0);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  text-align: center;
  font-family: inherit;
}}
.edn-actions-title {{
  font-size: 11px;
  font-weight: 700;
  color: var(--fg-subtle, #737373);
  text-transform: uppercase;
  letter-spacing: 0.6px;
  margin-bottom: 10px;
}}
.edn-actions-group {{
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}}
.edn-btn {{
  padding: 6px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--fg, #020202);
  background-color: var(--button-bg, #fcfcfc);
  border: 1px solid var(--border, #c4c4c4);
  border-radius: 5px;
  cursor: pointer;
  transition: background-color 150ms ease, border-color 150ms ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  user-select: none;
}}
.edn-btn:hover:not(:disabled) {{
  background-color: var(--canvas, #f5f5f5);
  border-color: var(--button-hover-border, #999999);
}}
.edn-btn:active:not(:disabled) {{
  transform: translateY(1px);
}}
.edn-btn:disabled {{
  opacity: 0.45;
  cursor: not-allowed;
  border-color: var(--border-subtle, #e4e4e4);
  background-color: var(--button-disabled, rgba(214, 214, 214, 0.5));
  color: var(--fg-disabled, #858585);
}}
.edn-badge {{
  font-size: 11px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  background-color: var(--canvas-inset, #f0f0f0);
  color: var(--fg-subtle, #737373);
}}
.edn-finished-notice {{
  margin: 16px auto 6px auto;
  font-size: 13px;
  color: var(--fg-subtle, #737373);
  font-style: italic;
  text-align: center;
}}
</style>
<div class="edn-actions-card">
  <div class="edn-actions-title">Actions rapides EDN</div>
  <div class="edn-actions-group">
    <button type="button" class="edn-btn" onclick="pycmd('edn_action:browse')" title="Ouvrir toutes les cartes de cet item dans l'explorateur">Voir dans l'explorateur</button>
    <button type="button" class="edn-btn" onclick="pycmd('edn_action:unsuspend_a')" {disabled_a} title="{title_a}">Dé-suspendre rangs A <span class="edn-badge">({count_a})</span></button>
    <button type="button" class="edn-btn" onclick="pycmd('edn_action:unsuspend_all')" {disabled_all} title="{title_all}">Dé-suspendre tout <span class="edn-badge">({count_all})</span></button>
  </div>
</div>
"""


def execute_unsuspend_and_rebuild_sync(col, did: int, cids: List[int]) -> int:
    """Exécution synchrone (utile pour les tests unitaires et opérations de fond)."""
    if not cids:
        return 0
    col.sched.unsuspend_cards(cids)
    res = col.sched.rebuild_filtered_deck(did)
    return getattr(res, "count", 0)


def unsuspend_and_rebuild_gui(parent_mw, did: int, cids: List[int], label: str):
    """Dé-suspend les cartes et reconstruit le paquet filtré via CollectionOp sécurisé."""
    if not cids:
        tooltip(f"Aucune carte suspendue pour {label}.")
        return

    from aqt.operations import CollectionOp

    def op(col):
        col.sched.unsuspend_cards(cids)
        return col.sched.rebuild_filtered_deck(did)

    def on_success(res):
        cnt = getattr(res, "count", 0)
        tooltip(f"{len(cids)} carte(s) dé-suspendue(s) ({cnt} carte(s) allouées au paquet).")
        if getattr(parent_mw, "overview", None):
            parent_mw.overview.refresh()
        else:
            parent_mw.reset()

    CollectionOp(parent=parent_mw, op=op).success(on_success).run_in_background()


def open_browser_for_deck(parent_mw, deck: dict):
    """Ouvre l'explorateur Anki sur toutes les cartes de l'item / sous-partie."""
    queries = extract_action_queries(deck)
    if not queries:
        return
    query_browser = queries[0]
    from aqt import dialogs
    dialogs.open("Browser", parent_mw, search=(query_browser,))


def handle_overview_action(overview: Overview, action: str) -> None:
    """Traite les actions cliquées depuis la page Overview."""
    if not overview or not overview.mw or not overview.mw.col:
        return

    deck = overview.mw.col.decks.current()
    if not is_edn_filtered_deck(deck):
        return

    queries = extract_action_queries(deck)
    if not queries:
        return

    q_browser, q_a, q_all = queries
    col = overview.mw.col
    did = deck["id"]

    if action == "browse":
        open_browser_for_deck(overview.mw, deck)

    elif action == "unsuspend_a":
        cids = col.find_cards(q_a)
        if not cids:
            tooltip("Aucune carte de rang A suspendue restante.")
            return
        unsuspend_and_rebuild_gui(overview.mw, did, cids, label="Rangs A")

    elif action == "unsuspend_all":
        cids = col.find_cards(q_all)
        if not cids:
            tooltip("Aucune carte suspendue restante pour cet item.")
            return
        unsuspend_and_rebuild_gui(overview.mw, did, cids, label="Item complet")


def on_overview_will_render_content(overview: Overview, content: OverviewContent) -> None:
    """Hook Anki : injecte l'encart d'actions dans le corps de la page Overview."""
    try:
        if not overview or not overview.mw or not overview.mw.col:
            return

        deck = overview.mw.col.decks.current()
        if not is_edn_filtered_deck(deck):
            return

        queries = extract_action_queries(deck)
        if not queries:
            return

        _, q_a, q_all = queries
        col = overview.mw.col
        count_a, count_all = get_suspended_counts(col, q_a, q_all)

        panel_html = render_action_panel(count_a=count_a, count_all=count_all)
        content.table += panel_html
    except Exception as e:
        log_error(f"Erreur injection bandeau actions EDN: {e}")


def on_webview_did_receive_js_message(handled: Tuple[bool, Any], message: str, context: Any) -> Tuple[bool, Any]:
    """Hook Anki : intercepte les messages pycmd('edn_action:...') envoyés par les boutons."""
    if not isinstance(message, str) or not message.startswith("edn_action:"):
        return handled

    action = message.split(":", 1)[1]

    try:
        if isinstance(context, Overview):
            handle_overview_action(context, action)
            return (True, None)

        if hasattr(context, "overview") and isinstance(context.overview, Overview):
            handle_overview_action(context.overview, action)
            return (True, None)

        if mw and getattr(mw, "overview", None):
            handle_overview_action(mw.overview, action)
            return (True, None)
    except Exception as e:
        log_error(f"Erreur traitement action pycmd ({message}): {e}")

    return (True, None)


_RENDER_PAGE_WRAPPED = False

def setup_overview_render_page_wrapper() -> None:
    """
    Empêche la redirection vers l'écran 'congrats' Sveltekit vide pour les paquets
    filtrés EDN terminés ou vides, afin de toujours afficher la page et le bandeau d'actions.
    """
    global _RENDER_PAGE_WRAPPED
    if _RENDER_PAGE_WRAPPED:
        return

    orig_render_page = Overview._renderPage

    def wrapped_render_page(self: Overview) -> None:
        try:
            deck = self.mw.col.decks.current()
            if is_edn_filtered_deck(deck) and self.mw.col.sched._is_finished():
                content = OverviewContent(
                    deck=deck["name"],
                    shareLink="",
                    desc=self._desc(deck),
                    table="<div class='edn-finished-notice'>Toutes les cartes actives de ce paquet ont été révisées.</div>",
                )
                gui_hooks.overview_will_render_content(self, content)
                content.deck = html.escape(content.deck)
                self.web.stdHtml(
                    self._body % content.__dict__,
                    css=["css/overview.css"],
                    js=["js/vendor/jquery.min.js"],
                    context=self,
                )
                return
        except Exception as e:
            log_error(f"Erreur rendu page overview EDN paquet terminé: {e}")

        return orig_render_page(self)

    Overview._renderPage = wrapped_render_page
    _RENDER_PAGE_WRAPPED = True
    log("Wrapper Overview._renderPage installé pour paquets filtrés EDN.")


_HOOKS_INITIALIZED = False

def init_filtered_deck_actions() -> None:
    """Installe tous les hooks et intercepteurs pour les actions de paquets filtrés EDN."""
    global _HOOKS_INITIALIZED
    if _HOOKS_INITIALIZED:
        return

    try:
        gui_hooks.overview_will_render_content.append(on_overview_will_render_content)
        gui_hooks.webview_did_receive_js_message.append(on_webview_did_receive_js_message)
        setup_overview_render_page_wrapper()
        _HOOKS_INITIALIZED = True
        log("Hooks d'actions rapides pour paquets filtrés EDN initialisés avec succès.")
    except Exception as e:
        log_error(f"Erreur initialisation actions paquets filtrés EDN: {e}")
