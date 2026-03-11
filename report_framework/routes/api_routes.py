import os

from flask import Blueprint, current_app, jsonify, request

from apply_engine import ApplyError, preview_apply_warnings
from services.analysis_service import analyze_workspace, build_project_state
from services.diff_service import load_project_diff
from services.history_service import refresh_baseline, save_source_text


api_bp = Blueprint("api", __name__)


def _missing_params_error():
    return jsonify({"ok": False, "error": "missing parameters"}), 400


def _handle_save_like_request(save_func):
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    file_path = data.get("file")
    source_text = data.get("sourceText")

    if not project_root or not file_path or source_text is None:
        return _missing_params_error()

    try:
        save_func(project_root, file_path, source_text)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@api_bp.route("/save", methods=["POST"])
def save():
    return _handle_save_like_request(save_source_text)


@api_bp.route("/autosave", methods=["POST"])
def autosave():
    return _handle_save_like_request(save_source_text)


@api_bp.route("/preview_apply", methods=["POST"])
def preview_apply():
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    file_path = data.get("file")
    source_text = data.get("sourceText")
    warnings = data.get("warnings") or []

    if not project_root or not file_path or source_text is None:
        return _missing_params_error()

    try:
        result = preview_apply_warnings(
            source_text=source_text,
            warning_payloads=warnings,
            rel_filename=file_path,
        )
    except ApplyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "sourceText": result.source_text,
            "diffText": result.diff_text,
            "appliedCount": result.applied_count,
        }
    )


@api_bp.route("/save_and_reanalyze", methods=["POST"])
def save_and_reanalyze():
    data = request.get_json(force=True) or {}
    engine_root = data.get("engine") or current_app.config["DEFAULT_PROJECT_ROOT"]
    project_root = data.get("root")
    file_path = data.get("file")
    source_text = data.get("sourceText")

    if not project_root or not file_path or source_text is None:
        return _missing_params_error()

    try:
        save_source_text(project_root, file_path, source_text)
        workspace = analyze_workspace(engine_root, project_root, file_path)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify(
        {
            "ok": True,
            "sourceText": workspace["source_text"],
            "warnings": workspace["warnings_for_js"],
            "runOutput": workspace["run_output"],
            "warningCount": workspace["warning_count"],
        }
    )


@api_bp.route("/refreshprev", methods=["POST"])
def refreshprev():
    data = request.get_json(force=True) or {}
    project_root = data.get("root")
    if not project_root:
        return _missing_params_error()

    try:
        refresh_baseline(project_root)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


@api_bp.route("/api/project", methods=["GET"])
def api_project():
    engine_root = request.args.get("engine") or current_app.config["DEFAULT_PROJECT_ROOT"]
    project_root = request.args.get("root") or ""
    if not project_root:
        return _missing_params_error()
    return jsonify({"ok": True, **build_project_state(engine_root, project_root)})


@api_bp.route("/api/analyze_file", methods=["GET"])
def api_analyze_file():
    engine_root = request.args.get("engine") or current_app.config["DEFAULT_PROJECT_ROOT"]
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""
    if not project_root or not file_path:
        return _missing_params_error()

    workspace = analyze_workspace(engine_root, project_root, file_path)
    return jsonify(
        {
            "ok": True,
            "engineRoot": engine_root,
            "projectRoot": os.path.abspath(project_root),
            "currentFile": file_path,
            "sourceText": workspace["source_text"],
            "warnings": workspace["warnings_for_js"],
            "runOutput": workspace["run_output"],
            "warningCount": workspace["warning_count"],
        }
    )


@api_bp.route("/api/diff", methods=["GET"])
def api_diff():
    project_root = request.args.get("root") or ""
    if not project_root:
        return _missing_params_error()
    return jsonify({"ok": True, **load_project_diff(os.path.abspath(project_root))})
