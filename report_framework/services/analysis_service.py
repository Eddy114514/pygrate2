import os
from typing import Dict, List

from framework import WarningRecord, analyze_file_with_output
from services.file_service import build_antd_tree, build_tree_for_ui, load_source_text
from services.warning_payload_service import serialize_warnings_for_client


def analyze_workspace(engine_root: str, project_root: str, file_path: str) -> Dict[str, object]:
    abs_root = os.path.abspath(project_root)
    warnings: List[WarningRecord] = []
    source_text = ""
    run_output = ""
    files_map: Dict[str, str] = {}

    if file_path:
        warnings, run_output = analyze_file_with_output(
            engine_root if engine_root else None,
            abs_root,
            file_path,
        )
        rel_paths = {warning.rel_filename for warning in warnings}
        for rel in sorted(rel_paths):
            files_map[rel] = load_source_text(abs_root, rel)

        if file_path in files_map:
            source_text = files_map[file_path]
        else:
            source_text = load_source_text(abs_root, file_path)
            if source_text:
                files_map[file_path] = source_text

    current_warnings = [warning for warning in warnings if warning.rel_filename == file_path]
    warnings_for_js = serialize_warnings_for_client(current_warnings, {file_path: source_text})
    return {
        "source_text": source_text,
        "run_output": run_output,
        "warnings": current_warnings,
        "warnings_for_js": warnings_for_js,
        "files_map": {file_path: source_text} if file_path else {},
        "warning_count": len(warnings_for_js),
    }


def build_project_state(engine_root: str, project_root: str) -> Dict[str, object]:
    abs_root = os.path.abspath(project_root)
    raw_tree = build_tree_for_ui(abs_root) if os.path.isdir(abs_root) else {}
    return {
        "engineRoot": engine_root,
        "projectRoot": project_root,
        "fileTree": raw_tree,
        "treeNodes": build_antd_tree(raw_tree),
    }
