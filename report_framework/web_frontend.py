# report_framework/web_frontend.py

import os
from typing import Dict, List

from flask import Flask, request, render_template, jsonify,  redirect, url_for

from markupsafe import Markup
from difflib import HtmlDiff

from file_io import save_with_backup

from framework import analyze_file_with_output, WarningRecord, build_tree_for_ui


# Default project root; adjust if you want a narrower scope.
DEFAULT_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

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


@app.route("/", methods=["GET"])
def index():
    # Read query parameters
    engine_root = request.args.get("engine") or DEFAULT_PROJECT_ROOT
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""
    
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
            "colStart": w.col_start,
            "colEnd": w.col_end,
        }
        for w in warnings
    ]
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
    
@app.route("/save", methods=["POST"])
def save():
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    file_path = data.get("file")
    source_text = data.get("sourceText")

    if not project_root or not file_path or source_text is None:
        return jsonify({"ok": False, "error": "missing parameters"}), 400

    try:
        save_with_backup(project_root, file_path, source_text)
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

    history_root = os.path.join(project_root, ".pygrate_history")

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
            diff_text = "\n".join(all_diff_lines)

    return render_template(
        "diff.html",
        project_root=project_root,
        file_path=file_path,
        diff_text=diff_text,
    )
    
@app.route("/project", methods=["GET"])
def project_view():
    engine_root = request.args.get("engine") or DEFAULT_PROJECT_ROOT
    project_root = request.args.get("root") or ""

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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    app.run(debug=True, port=args.port)
