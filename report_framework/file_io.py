# report_framework/file_io.py

import os

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
