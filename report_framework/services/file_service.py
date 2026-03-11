import os
from typing import Dict, List


IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".pygrate_history",
    "__pycache__",
    "node_modules",
}


def load_source_lines(abs_root: str, rel_path: str) -> List[str]:
    abs_path = os.path.join(abs_root, rel_path)
    if not os.path.exists(abs_path):
        return []
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.readlines()
    except Exception:
        return []


def load_source_text(abs_root: str, rel_path: str) -> str:
    return "".join(load_source_lines(abs_root, rel_path))


def build_tree_for_ui(root: str) -> Dict[str, object]:
    def _build(path: str) -> Dict[str, object]:
        node: Dict[str, object] = {"__files__": []}
        try:
            entries = sorted(os.scandir(path), key=lambda entry: entry.name)
        except OSError:
            return {}

        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name in IGNORED_DIR_NAMES or entry.name.startswith("."):
                    continue
                child = _build(entry.path)
                if child:
                    node[entry.name] = child
                continue

            if entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                node["__files__"].append(entry.name)

        if node["__files__"] or any(key != "__files__" for key in node):
            return node
        return {}

    return _build(root)


def build_antd_tree(node: Dict[str, object], prefix: str = "") -> List[Dict[str, object]]:
    result: List[Dict[str, object]] = []

    files = sorted(node.get("__files__", []))
    for fname in files:
        rel_path = "%s/%s" % (prefix, fname) if prefix else fname
        result.append(
            {
                "title": fname,
                "key": rel_path,
                "isLeaf": True,
                "path": rel_path,
            }
        )

    for dirname in sorted(key for key in node.keys() if key != "__files__"):
        child = node[dirname]
        rel_path = "%s/%s" % (prefix, dirname) if prefix else dirname
        result.append(
            {
                "title": dirname,
                "key": rel_path,
                "path": rel_path,
                "children": build_antd_tree(child, rel_path),
            }
        )

    return result
