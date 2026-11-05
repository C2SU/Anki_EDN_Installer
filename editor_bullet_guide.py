# -*- coding: utf-8 -*-
"""
Anki EDN Editor Bullet Guide
Pre-populates an initial bullet point (<ul><li><br></li></ul>) in fields that
conventionally require bulleted lists (such as 'Verso' / 'Answer' in Basique,
and 'Description' in Syndrome / Semiologie) to guide card creators.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

from aqt import mw, gui_hooks
from aqt.editor import Editor
from anki.hooks import wrap
try:
    from .logger import log
    from .shared_menu import get_config
except (ImportError, ValueError):
    try:
        from Anki_EDN_Installer.logger import log
        from Anki_EDN_Installer.shared_menu import get_config
    except (ImportError, ValueError):
        from logger import log
        from shared_menu import get_config

BULLET_TARGET_FIELDS = {
    "verso",
    "answer",
    "description",
    "infos supplémentaires",
    "infos supplementaires",
}
EMPTY_BULLET_PATTERNS = {
    "<ul><li><br></li></ul>",
    "<ul><li></li></ul>",
    "<ul><li>&nbsp;</li></ul>",
    "<div><ul><li><br></li></ul></div>",
    "<div><ul><li></li></ul></div>",
    "<ul><li><br/></li></ul>",
}

DEFAULT_INITIAL_BULLET = "<ul><li><br></li></ul>"


def is_bullet_guide_enabled() -> bool:
    """Check if the editor bullet guide is enabled in user settings."""
    cfg = get_config()
    return bool(cfg.get("auto_bullet_in_editor", True))


def is_edn_notetype_for_bullets(note) -> bool:
    """Check if note belongs to an EDN notetype where bullet lists are standard."""
    if not note:
        return False
    try:
        nt = note.note_type() if hasattr(note, "note_type") else None
        if nt:
            name = nt.get("name", "").lower()
            if any(k in name for k in ("edn", "picat", "syndrome", "sémiologie", "semiologie", "basique")):
                return True
    except Exception:
        pass
    # Check tags
    tags = getattr(note, "tags", [])
    if any(t.lower().startswith(("edn", "ankicollab")) for t in tags):
        return True
    return False


def is_field_empty(content: str) -> bool:
    """Return True if content has no meaningful text."""
    if not content:
        return True
    cleaned = content.strip()
    if cleaned in ("", "<br>", "<div><br></div>", "<p><br></p>", "<p></p>"):
        return True
    # If media (images, audio, video) exists, it is not empty
    if re.search(r"<(img|audio|video|iframe|svg|canvas)\b", cleaned, re.IGNORECASE) or "[sound:" in cleaned:
        return False
    # Strip basic html tags and whitespace
    text_only = re.sub(r"<[^>]+>", "", cleaned)
    text_only = text_only.replace("&nbsp;", "").strip()
    return len(text_only) == 0


def apply_initial_bullet_to_note(note, editor: Optional[Editor] = None) -> bool:
    """
    If note is an EDN note and target fields (Verso, Description, Answer) are empty,
    prefill them with an initial bullet list.
    """
    if not is_bullet_guide_enabled() or not note:
        return False

    if not is_edn_notetype_for_bullets(note):
        return False

    changed = False
    for fld_name in note.keys():
        if fld_name.lower() in BULLET_TARGET_FIELDS:
            cur_val = note[fld_name]
            if is_field_empty(cur_val):
                note[fld_name] = DEFAULT_INITIAL_BULLET
                changed = True

    return changed


def clean_empty_bullets_from_note(note) -> bool:
    """
    Before saving, clean fields that only contain empty bullet tags so that
    blank fields remain genuinely blank and do not trigger empty card errors.
    """
    if not note:
        return False

    changed = False
    for fld_name in note.keys():
        if fld_name.lower() in BULLET_TARGET_FIELDS:
            cur_val = (note[fld_name] or "").strip()
            if cur_val in EMPTY_BULLET_PATTERNS or (("<ul>" in cur_val or "<li>" in cur_val) and is_field_empty(cur_val)):
                if note[fld_name] != "":
                    note[fld_name] = ""
                    changed = True

    return changed


def _on_editor_set_note(editor: Editor, note: Any = None, *args, **kwargs) -> None:
    """Hook called when Editor.set_note is invoked (e.g. in Add Cards dialog)."""
    try:
        if getattr(editor, "addMode", False) and note:
            apply_initial_bullet_to_note(note, editor)
    except Exception as e:
        log(f"[editor_bullet_guide] Erreur set_note: {e}")


def _on_editor_load_note(editor: Editor, *args, **kwargs) -> None:
    """Hook called before Editor.loadNote is invoked (e.g. when switching notetypes in Add Cards)."""
    try:
        if getattr(editor, "addMode", False) and getattr(editor, "note", None):
            apply_initial_bullet_to_note(editor.note, editor)
    except Exception as e:
        log(f"[editor_bullet_guide] Erreur load_note: {e}")


def _on_editor_will_load_note(js: str, note: Any, editor: Editor) -> str:
    """Inject editor-side JavaScript to guide list creation upon field focus."""
    if not is_bullet_guide_enabled() or not is_edn_notetype_for_bullets(note):
        return js

    import json
    target_indices = []
    try:
        for idx, fld_name in enumerate(note.keys()):
            if fld_name.strip().lower() in BULLET_TARGET_FIELDS:
                target_indices.append(idx)
    except Exception:
        pass

    target_json = json.dumps(target_indices)

    # Client-side listener: When focusing an empty target field (Verso, Description,
    # Infos supplémentaires, Erreurs faites), automatically initialize an unordered list.
    bullet_js = f"""
    (function() {{
        try {{
            var targetIndices = {target_json};
            function attachBulletGuides() {{
                targetIndices.forEach(function(idx) {{
                    var container = document.querySelector('.field-container[data-index="' + idx + '"]');
                    if (!container) return;
                    var editable = container.querySelector('[contenteditable]');
                    if (!editable || editable._ednBulletHooked) return;
                    editable._ednBulletHooked = true;

                    function triggerList() {{
                        var text = editable.textContent.trim();
                        if (text === "" && !editable.querySelector("ul, ol")) {{
                            document.execCommand("insertUnorderedList", false, null);
                        }}
                    }}

                    editable.addEventListener("focus", triggerList);
                    editable.addEventListener("click", triggerList);
                    container.addEventListener("focusin", triggerList);
                }});
            }}
            attachBulletGuides();
            setTimeout(attachBulletGuides, 100);
            setTimeout(attachBulletGuides, 300);
        }} catch(e) {{}}
    }})();
    """
    return js + "\n" + bullet_js


def _on_add_cards_will_add_note(*args, **kwargs) -> Any:
    """Clean empty bullet tags before card creation.

    Anki filter hook signature: (problem: str | None, note: Note) -> str | None.
    If note is valid, returns problem (typically None).
    If note was already rejected by a prior filter, preserves problem.
    """
    problem: Optional[str] = None
    note: Any = None

    if len(args) >= 2:
        problem = args[0]
        note = args[1]
    elif len(args) == 1:
        arg = args[0]
        if hasattr(arg, "fields") or hasattr(arg, "note_type") or hasattr(arg, "keys"):
            note = arg
        elif isinstance(arg, str):
            problem = arg

    if "note" in kwargs:
        note = kwargs["note"]
    if "problem" in kwargs:
        problem = kwargs["problem"]

    # If already rejected by a prior hook, do not interfere
    if problem is not None:
        return problem

    try:
        if note:
            clean_empty_bullets_from_note(note)
    except Exception as e:
        log(f"[editor_bullet_guide] Erreur will_add_note: {e}")

    return problem


def init_editor_bullet_guide_hooks() -> None:
    """Register all hooks for the editor bullet guide."""
    Editor.set_note = wrap(Editor.set_note, _on_editor_set_note, "before")
    Editor.loadNote = wrap(Editor.loadNote, _on_editor_load_note, "before")
    gui_hooks.editor_will_load_note.append(_on_editor_will_load_note)
    gui_hooks.add_cards_will_add_note.append(_on_add_cards_will_add_note)
    log("[editor_bullet_guide] Module de guidage des puces initialise.")
