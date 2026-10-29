import os
import zipfile

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
DEST_PATH = os.path.join(SOURCE_DIR, "Anki_EDN_Installer.ankiaddon")

EXCLUDES = [
    "__pycache__",
    "meta.json",
    ".git",
    ".gitignore",
    ".vscode",
    ".idea",
    ".ankiaddon",
    ".log",
    "ankiedn_assistant.log",
    "test_filtered_decks.py",
    "test_ankicollab_safety.py",
    "test_field_protection.py",
    "test_setup_assistant.py"
]

def should_exclude(rel_path):
    parts = rel_path.split(os.sep)
    for part in parts:
        for exclude in EXCLUDES:
            if exclude in part or (exclude.startswith("*") and part.endswith(exclude.replace("*", ""))):
                return True
    return False

def create_addon_package():
    print(f"Packaging addon from: {SOURCE_DIR}")
    print(f"Destination: {DEST_PATH}")
    
    with zipfile.ZipFile(DEST_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            dirs[:] = [d for d in dirs if not should_exclude(d)]
            for file in files:
                if should_exclude(file):
                    continue
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, SOURCE_DIR)
                print(f"Adding: {rel_path}")
                zipf.write(abs_path, rel_path)
                
    print("\nPackage created successfully!")

if __name__ == "__main__":
    create_addon_package()
