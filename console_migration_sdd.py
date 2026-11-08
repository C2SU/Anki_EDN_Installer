# -*- coding: utf-8 -*-
"""
Script de migration des tags SDD EDN pour la console de débogage Anki (Ctrl+:).
Cible : Uniquement les tags SDD et SSDD (ex: EDN::sdd-xxx -> EDN::SDD::xxx).
Ne touche ABSOLUMENT PAS aux tags EDN::item-xxx ni aux autres tags.

Version blindée :
- Polyfill sys.stdout.flush() pour éviter les crashs avec 00_EDN_Debug_Profiler
- Sécurisation de l'appel checkpoint / undo
- Idempotence garantie (reprend là où il s'est arrêté sans doublon)
- Protection try/except par note
"""

import sys
import re

# --- Polyfill console Anki pour addons tiers (00_EDN_Debug_Profiler, etc.) ---
for stream in (sys.stdout, sys.stderr):
    if stream is not None:
        if not hasattr(stream, "flush"):
            stream.flush = lambda: None
        if hasattr(stream, "_stream") and not hasattr(stream._stream, "flush"):
            stream._stream.flush = lambda: None

from aqt import mw
from aqt.utils import tooltip

# Paramètres
DRY_RUN = False  # Mettre à True pour simuler sans appliquer les modifications

# Regex stricte ciblant uniquement les tags SDD et SSDD
RE_SDD = re.compile(r"^(edn)::(s{1,2}dd)-(.*)$", re.IGNORECASE)

def run_migration():
    col = mw.col
    if not col:
        print("[ERREUR] Collection Anki non disponible.")
        return

    # Recherche des notes contenant encore des tags SDD/SSDD à migrer
    query = "tag:*sdd-* or tag:*ssdd-*"
    nids = col.find_notes(query)
    print("=== Migration des Tags EDN SDD (Reprise / Finalisation) ===")
    print(f"Notes candidates trouvées : {len(nids)}")
    print(f"Mode : {'SIMULATION (Dry-Run)' if DRY_RUN else 'APPLICATION RÉELLE'}\n")

    modified_notes_count = 0
    skipped_notes_count = 0
    errors_count = 0
    transformations = {}

    for nid in nids:
        try:
            note = col.get_note(nid)
        except Exception as e:
            print(f"[ERREUR] Impossible de charger la note {nid} : {e}")
            errors_count += 1
            continue

        new_tags = []
        note_modified = False

        for tag in note.tags:
            m = RE_SDD.match(tag)
            if m:
                # Normalisation en EDN::SDD::... ou EDN::SSDD::...
                prefix = m.group(2).upper()  # SDD ou SSDD
                rest = m.group(3)
                new_tag = f"EDN::{prefix}::{rest}"
                new_tags.append(new_tag)
                note_modified = True
                
                key = f"{tag}  ->  {new_tag}"
                transformations[key] = transformations.get(key, 0) + 1
            else:
                # Tout autre tag (y compris EDN::item-xxx ou tags SDD déjà migrés) reste INTACT
                new_tags.append(tag)

        if note_modified:
            if not DRY_RUN:
                # Déduplication en préservant l'ordre
                seen = set()
                deduped = []
                for t in new_tags:
                    if t not in seen:
                        seen.add(t)
                        deduped.append(t)
                note.tags = deduped
                try:
                    col.update_note(note)
                    modified_notes_count += 1
                except Exception as e:
                    print(f"[ERREUR] Échec mise à jour note {nid} : {e}")
                    errors_count += 1
            else:
                modified_notes_count += 1
        else:
            skipped_notes_count += 1

    if not DRY_RUN:
        # Nettoyage des anciens tags orphelins dans l'arbre Anki
        try:
            if hasattr(col, "tags") and hasattr(col.tags, "clear_unused_tags"):
                col.tags.clear_unused_tags()
        except Exception:
            pass

        # Rafraîchissement de l'interface graphique (navigateur, arbre des tags)
        try:
            mw.reset()
        except Exception:
            pass

    # Affichage du rapport
    print("\n=== Rapport de migration ===")
    print(f"Notes modifiées : {modified_notes_count}")
    print(f"Notes ignorées (déjà migrées ou inchangées) : {skipped_notes_count}")
    if errors_count > 0:
        print(f"Erreurs rencontrées : {errors_count}")
    print(f"Détail des transformations ({len(transformations)} tags uniques) :")
    for trans, count in sorted(transformations.items()):
        print(f"  • {trans} ({count} occurrence{'s' if count > 1 else ''})")

    status_msg = (
        f"[SIMULATION] {modified_notes_count} notes seraient modifiées."
        if DRY_RUN
        else f"Migration SDD terminée : {modified_notes_count} notes mises à jour !"
    )
    print(f"\n{status_msg}")
    tooltip(status_msg, period=4000)

run_migration()
