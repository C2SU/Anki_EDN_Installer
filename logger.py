import os
import sys
import datetime

ADDON_DIR = os.path.dirname(__file__)
LOG_FILE = os.path.join(ADDON_DIR, "ankiedn_assistant.log")

def log(message, level="INFO"):
    """
    Logs a message to the addon's log file.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] [{level}] {message}\n"
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted_message)
    except Exception as e:
        print(f"Error writing to log: {e}")

def log_error(message):
    log(message, level="ERROR")
