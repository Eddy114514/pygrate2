# report_framework/web_frontend.py

import os
from typing import Dict, List

from flask import Flask, request, render_template, jsonify

from file_io import save_file 

from framework import analyze_file_with_output, WarningRecord


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
    project_root = request.args.get("root") or DEFAULT_PROJECT_ROOT
    file_path = request.args.get("file") or ""

    warnings: List[WarningRecord] = []
    source_lines: List[str] = []
    warnings_by_line: Dict[int, List[WarningRecord]] = {}
    source_text = ""
    run_output = ""

    if file_path:
        project_root = os.path.abspath(project_root)

        # backend analysis
        warnings, run_output = analyze_file_with_output(project_root, file_path)
        source_lines = _load_source_lines(project_root, file_path)
        source_text = "".join(source_lines)

        for w in warnings:
            warnings_by_line.setdefault(w.lineno, []).append(w)

    # prepare a lean JSON-friendly structure for JS
    warnings_for_js = [
        {
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
        project_root=project_root,
        file_path=file_path,
        source_text=source_text,
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

    try:
        save_file(project_root, file_path, source_text)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    return jsonify({"ok": True})

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    app.run(debug=True, port=args.port)
