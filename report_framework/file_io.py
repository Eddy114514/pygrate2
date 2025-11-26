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

def save_with_backup(project_root: str, file_path: str, source_text: str) -> Optional[str]:
    abs_root = os.path.abspath(project_root)
    abs_path = os.path.join(abs_root, file_path)

    old_content = None
    if os.path.exists(abs_path):
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                old_content = f.read()
        except Exception:
            old_content = None

    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(source_text)

    if old_content is None:
        return None

    history_root = os.path.join(abs_root, ".pygrate_history")
    hist_path = os.path.join(history_root, file_path + ".prev")

    os.makedirs(os.path.dirname(hist_path), exist_ok=True)
    with open(hist_path, "w", encoding="utf-8") as hf:
        hf.write(old_content)

    return hist_path
