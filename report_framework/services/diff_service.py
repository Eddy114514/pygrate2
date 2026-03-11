import os
from typing import Dict, List, Optional

from apply_engine import build_unified_diff


def load_project_diff(project_root: str) -> Dict[str, Optional[object]]:
    """
    Diff semantics:
    - each `.pygrate_history/<file>.prev` stores the on-disk file contents
      immediately before the latest save-like write for that file
    - `/diff` therefore shows the delta from that latest saved baseline
    """
    history_root = os.path.join(project_root, ".pygrate_history")
    add_count = None
    del_count = None

    if not os.path.isdir(history_root):
        return {"diff_text": None, "add_count": add_count, "del_count": del_count}

    all_diff_lines: List[str] = []
    for dirpath, _, files in os.walk(history_root):
        rel_dir = os.path.relpath(dirpath, history_root)
        for name in files:
            if not name.endswith(".prev"):
                continue

            rel_file = name[:-5]
            if rel_dir != ".":
                rel_file = os.path.join(rel_dir, rel_file)

            abs_current = os.path.join(project_root, rel_file)
            hist_path = os.path.join(dirpath, name)
            if not os.path.exists(abs_current):
                continue

            with open(hist_path, "r", encoding="utf-8") as f:
                old_text = f.read()
            with open(abs_current, "r", encoding="utf-8") as f:
                current_text = f.read()

            diff_text = build_unified_diff(old_text, current_text, rel_file)
            if diff_text:
                if all_diff_lines:
                    all_diff_lines.append("")
                all_diff_lines.extend(diff_text.splitlines())

    if not all_diff_lines:
        return {"diff_text": None, "add_count": add_count, "del_count": del_count}

    add = 0
    delete = 0
    for line in all_diff_lines:
        if line.startswith("+") and not line.startswith("+++"):
            add += 1
        elif line.startswith("-") and not line.startswith("---"):
            delete += 1

    return {
        "diff_text": "\n".join(all_diff_lines),
        "add_count": add,
        "del_count": delete,
    }
