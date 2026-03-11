import os

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from services.analysis_service import analyze_workspace, build_project_state
from services.diff_service import load_project_diff
from services.frontend_asset_service import frontend_template_context


pages_bp = Blueprint("pages", __name__)


def _render_frontend_shell(*, page_kind: str, bootstrap_data: dict, title: str):
    return render_template(
        "frontend_shell.html",
        page_kind=page_kind,
        bootstrap_data=bootstrap_data,
        page_title=title,
        **frontend_template_context()
    )


@pages_bp.route("/", methods=["GET"])
def index():
    engine_root = request.args.get("engine") or current_app.config["DEFAULT_PROJECT_ROOT"]
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""

    if not engine_root or not project_root:
        return redirect(url_for("pages.project_view"))

    project_state = build_project_state(engine_root, project_root)
    workspace = analyze_workspace(engine_root, project_root, file_path)
    bootstrap_data = {
        "pageKind": "workspace",
        **project_state,
        "currentFile": file_path,
        "sourceText": workspace["source_text"],
        "warnings": workspace["warnings_for_js"],
        "runOutput": workspace["run_output"],
        "warningCount": workspace["warning_count"],
        "previewDiffText": "",
    }
    return _render_frontend_shell(
        page_kind="workspace",
        bootstrap_data=bootstrap_data,
        title="Pygrate Workspace",
    )


@pages_bp.route("/project", methods=["GET"])
def project_view():
    engine_root = request.args.get("engine") or current_app.config["DEFAULT_PROJECT_ROOT"]
    project_root = request.args.get("root") or ""
    project_state = (
        build_project_state(engine_root, project_root)
        if project_root
        else {
            "engineRoot": engine_root,
            "projectRoot": project_root,
            "fileTree": {},
            "treeNodes": [],
        }
    )
    bootstrap_data = {
        "pageKind": "project",
        **project_state,
    }
    return _render_frontend_shell(
        page_kind="project",
        bootstrap_data=bootstrap_data,
        title="Pygrate Project",
    )


@pages_bp.route("/diff", methods=["GET"])
def diff_view():
    project_root = request.args.get("root") or ""
    file_path = request.args.get("file") or ""
    if not project_root:
        return redirect(url_for("pages.project_view"))

    diff_state = load_project_diff(os.path.abspath(project_root))
    return render_template(
        "diff.html",
        project_root=project_root,
        file_path=file_path,
        diff_text=diff_state["diff_text"],
        add_count=diff_state["add_count"],
        del_count=diff_state["del_count"],
    )
