# report_framework/file_io.py

import os
from typing import Optional


def save_file(project_root: str, file_path: str, content: str):
    """
    Save content into the file specified by project_root + file_path.

    Raises:
        ValueError: if parameters are invalid
        OSError: if filesystem operations fail
    """
    if not project_root or not file_path:
        raise ValueError("Missing project_root or file_path")

    if content is None:
        raise ValueError("Missing content to save")

    abs_root = os.path.abspath(project_root)
    abs_path = os.path.join(abs_root, file_path)

    # ensure directory exists
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    # write file
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)

    return abs_path

def refresh_prev_files(project_root):
    abs_root = os.path.abspath(project_root)
    history_root = os.path.join(abs_root, ".pygrate_history")

    if not os.path.isdir(history_root):
        return

    for dirpath, _, files in os.walk(history_root):
        for name in files:
            if not name.endswith(".prev"):
                continue

            prev_path = os.path.join(dirpath, name)

            rel_file = name[:-5]
            rel_dir = os.path.relpath(dirpath, history_root)

            if rel_dir != ".":
                rel_file = os.path.join(rel_dir, rel_file)

            real_path = os.path.join(abs_root, rel_file)

            if not os.path.exists(real_path):
                continue

            try:
                with open(real_path, "r", encoding="utf-8") as f:
                    real_text = f.read()

                os.makedirs(os.path.dirname(prev_path), exist_ok=True)
                with open(prev_path, "w", encoding="utf-8") as pf:
                    pf.write(real_text)

            except Exception:
                pass

def save_with_backup(project_root: str, file_path: str, source_text: str) -> Optional[str]:
    abs_root = os.path.abspath(project_root)
    abs_path = os.path.join(abs_root, file_path)

    history_root = os.path.join(abs_root, ".pygrate_history")
    prev_path = os.path.join(history_root, file_path + ".prev")

    if os.path.exists(abs_path):
        old_text = None
        with open(abs_path, "r", encoding="utf-8") as f:
            old_text = f.read()

        os.makedirs(os.path.dirname(prev_path), exist_ok=True)

        if not os.path.exists(prev_path):
            with open(prev_path, "w", encoding="utf-8") as pf:
                pf.write(old_text)
    
    return save_file(project_root, file_path, source_text)
