# report_framework/web_frontend.py

import os
from typing import Dict, List, Set
import ast

import atexit
import shutil
from flask import Flask, request, render_template, jsonify,  redirect, url_for

from markupsafe import Markup
from difflib import HtmlDiff

from file_io import *

from framework import analyze_file_with_output, WarningRecord, build_tree_for_ui


# Default project root; adjust if you want a narrower scope.
DEFAULT_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
CURRENT_PROJECT_ROOT = None

app = Flask(__name__, template_folder="templates", static_folder="static")


def _load_source_lines(abs_root: str, rel_path: str) -> List[str]:
    """
    Load the file content as a list of lines.
    """
    abs_path = os.path.join(abs_root, rel_path)
    if not os.path.exists(abs_path):
        return []
    try:
        with open(abs_path, "r") as f:
            return f.readlines()
    except Exception:
        return []


def _canonicalize_imports_from_ast(src: str) -> Set[str]:
    """
    Return a set of canonical import strings found in the source using AST parsing.
    """
    try:
        tree = ast.parse(src)
    except Exception:
        return set()

    results: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                alias_part = f" as {alias.asname}" if alias.asname else ""
                results.add(f"import {name}{alias_part}")
        elif isinstance(node, ast.ImportFrom):
            module = "." * (node.level or 0) + (node.module or "")
            for alias in node.names:
                name = alias.name
                alias_part = f" as {alias.asname}" if alias.asname else ""
                results.add(f"from {module} import {name}{alias_part}")
    return results


def _normalize_required_imports(import_lines: List[str]) -> List[str]:
    """
    Normalize required import strings into canonical single-import lines.
    Lines that cannot be parsed as imports are skipped.
    """
    canonicals: List[str] = []
    for line in import_lines:
        if not line or not isinstance(line, str):
            continue
        try:
            tree = ast.parse(line)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    alias_part = f" as {alias.asname}" if alias.asname else ""
                    canonicals.append(f"import {name}{alias_part}")
            elif isinstance(node, ast.ImportFrom):
                module = "." * (node.level or 0) + (node.module or "")
                for alias in node.names:
                    name = alias.name
                    alias_part = f" as {alias.asname}" if alias.asname else ""
                    canonicals.append(f"from {module} import {name}{alias_part}")
    return canonicals


@app.route("/", methods=["GET"])
def index():
    # Read query parameters
    engine_root = request.args.get("engine") or DEFAULT_PROJECT_ROOT
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""
    
    global CURRENT_PROJECT_ROOT
    if project_root:
        CURRENT_PROJECT_ROOT = os.path.abspath(project_root)
    
    if not engine_root or not project_root:
        return redirect(url_for("project_view"))

    warnings: List[WarningRecord] = []
    source_lines: List[str] = []
    warnings_by_line: Dict[int, List[WarningRecord]] = {}
    source_text = ""
    run_output = ""
    files_map: Dict[str, str] = {}

    if file_path:
        project_root = os.path.abspath(project_root)

        warnings, run_output = analyze_file_with_output(
            engine_root if engine_root else None,
            project_root,
            file_path,
        )

        rel_paths = set()
        for w in warnings:
            rel_paths.add(w.rel_filename)

        for rel in sorted(rel_paths):
            lines = _load_source_lines(project_root, rel)
            files_map[rel] = "".join(lines)

        if file_path in files_map:
            source_text = files_map[file_path]
        else:
            source_lines = _load_source_lines(project_root, file_path)
            source_text = "".join(source_lines)
            if source_text:
                files_map[file_path] = source_text

        for w in warnings:
            if w.rel_filename == file_path:
                warnings_by_line.setdefault(w.lineno, []).append(w)

    warnings_for_js = [
        {
            "file": w.rel_filename,
            "line": w.lineno,
            "type": w.warning_type,
            "message": w.message,
            "original": w.line,
            "fix": w.auto_fix_line,
            "fixText": w.fix_text,
            "imports": getattr(w, "required_imports", []),
            "importsNeeded": [],
            "colStart": w.col_start,
            "colEnd": w.col_end,
            "highlight": w.highlight,
        }
        for w in warnings
    ]

    # Compute missing imports per file, based on existing imports in that file.
    existing_imports_map: Dict[str, Set[str]] = {}
    for rel_path, text in files_map.items():
        existing_imports_map[rel_path] = _canonicalize_imports_from_ast(text)

    for item in warnings_for_js:
        rel = item["file"]
        existing = existing_imports_map.get(rel, set())
        required = _normalize_required_imports(item.get("imports") or [])
        missing = [imp for imp in required if imp not in existing]
        item["importsNeeded"] = missing
    return render_template(
        "report.html",
        engine_root=engine_root,
        project_root=project_root,
        file_path=file_path,
        source_text=source_text,
        files_map=files_map,
        warnings=warnings,
        warnings_for_js=warnings_for_js,
        warnings_by_line=warnings_by_line,
        run_output=run_output,
    )
    
    
    
def _handle_save_like_request(save_func):
    global CURRENT_PROJECT_ROOT
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    file_path = data.get("file")
    source_text = data.get("sourceText")

    if project_root:
        CURRENT_PROJECT_ROOT = os.path.abspath(project_root)

    if not project_root or not file_path or source_text is None:
        return jsonify({"ok": False, "error": "missing parameters"}), 400

    try:
        save_func(project_root, file_path, source_text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})
    
@app.route("/save", methods=["POST"])
def save():
    def _impl(project_root, file_path, source_text):
        save_with_backup(project_root, file_path, source_text)

    return _handle_save_like_request(_impl)


@app.route("/autosave", methods=["POST"])
def autosave():
    def _impl(project_root, file_path, source_text):
        save(project_root, file_path, source_text)

    return _handle_save_like_request(_impl)

@app.route("/refreshprev", methods=["POST"])
def refreshprev():
    global CURRENT_PROJECT_ROOT
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    if project_root:
        CURRENT_PROJECT_ROOT = os.path.abspath(project_root)

    try:
        refresh_prev_files(project_root)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})

@app.route("/diff", methods=["GET"])
def diff_view():
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""

    if not project_root:
        return redirect(url_for("project_view"))
    project_root = os.path.abspath(project_root)

    global CURRENT_PROJECT_ROOT
    if project_root:
        CURRENT_PROJECT_ROOT = os.path.abspath(project_root)

    history_root = os.path.join(project_root, ".pygrate_history")

    add_count = None
    del_count = None

    if not os.path.isdir(history_root):
        diff_text = None
    else:
        import difflib

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

                diff_lines = list(
                    difflib.unified_diff(
                        old_text.splitlines(),
                        current_text.splitlines(),
                        fromfile=f"a/{rel_file}",
                        tofile=f"b/{rel_file}",
                        lineterm="",
                    )
                )

                if diff_lines:
                    if all_diff_lines:
                        all_diff_lines.append("")
                    all_diff_lines.extend(diff_lines)

        if not all_diff_lines:
            diff_text = None
        else:
            add = 0
            delete = 0
            for ln in all_diff_lines:
                if ln.startswith("+") and not ln.startswith("+++"):
                    add += 1
                elif ln.startswith("-") and not ln.startswith("---"):
                    delete += 1

            add_count = add
            del_count = delete

            diff_text = "\n".join(all_diff_lines)

    return render_template(
        "diff.html",
        project_root=project_root,
        file_path=file_path,
        diff_text=diff_text,
        add_count=add_count,
        del_count=del_count,
    )

    
@app.route("/project", methods=["GET"])
def project_view():
    global CURRENT_PROJECT_ROOT
    engine_root = request.args.get("engine") or DEFAULT_PROJECT_ROOT
    project_root = request.args.get("root") or ""
    if project_root != "":
        CURRENT_PROJECT_ROOT = os.path.abspath(project_root)

    file_tree = None
    abs_root = None

    if engine_root and project_root:
        abs_root = os.path.abspath(project_root)
        if os.path.isdir(abs_root):
            file_tree = build_tree_for_ui(abs_root)

    return render_template(
        "project.html",
        engine_root=engine_root,
        project_root=project_root,
        file_tree=file_tree,
    )


def cleanup_pygrate_history():
    try:
        global CURRENT_PROJECT_ROOT
        root = CURRENT_PROJECT_ROOT
        if not root:
            return
        history_root = os.path.join(root, ".pygrate_history")
        if os.path.isdir(history_root):
            shutil.rmtree(history_root)
            print("Removed .pygrate_history on exit.")
    except Exception as e:
        print("Failed to remove .pygrate_history:", e)

atexit.register(cleanup_pygrate_history)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    app.run(debug=False, port=args.port)
