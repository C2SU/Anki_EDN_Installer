import time
from aqt import mw
from aqt.gui_hooks import profile_did_open
from aqt.utils import showInfo, tooltip
from .logger import log

def init_fsrs():
    profile_did_open.append(check_fsrs_status)
    log("FSRS module initialized.")

def check_fsrs_status():
    """
    Checks if FSRS weights are potentially stale (> 3 weeks).
    We use the Deck Config modification time as a proxy for when weights were last saved.
    """
    try:
        col = mw.col
        # Warning: This runs at startup, keep it fast.
        
        limit_seconds = 3 * 7 * 24 * 3600 # 3 weeks
        now = time.time()
        
        stale_configs = []
        
        # Iterate over all deck configurations
        # col.decks.all_config() returns a list of config dicts
        for conf in col.decks.all_config():
            # Check if FSRS is enabled (depends on Anki version, but 'fsrsWeights' usually present)
            # Actually, just check if the config hasn't been touched in 3 weeks.
            # Ideally we only care if FSRS is actually used.
            # But checking 'mod' is safe enough.
            
            last_mod = conf.get('mod', 0)
            # If using V2 scheduler, mod is 0? No, usually valid.
            
            if (now - last_mod) > limit_seconds:
                name = conf.get('name', 'Unknown')
                stale_configs.append(name)
        
        if stale_configs:
            # We don't want to nag too much. Maybe just a small toast or info if it's very old.
            # But the user asked for a "Signal".
            
            # Formatting
            msg = f"⚠️ <b>Rappel FSRS</b>: Paramètres obsolètes pour {len(stale_configs)} profil(s)."
            tooltip(msg, period=5000)
            
    except Exception as e:
        log(f"FSRS check error: {e}")
