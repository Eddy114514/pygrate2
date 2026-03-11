import hashlib
import json
from typing import Dict, List

from apply_engine import canonicalize_imports_from_source, normalize_required_imports


def warning_to_payload(warning) -> Dict[str, object]:
    payload = {
        "file": warning.rel_filename,
        "line": warning.lineno,
        "type": warning.warning_type,
        "message": warning.message,
        "original": warning.line,
        "fix": warning.auto_fix_line,
        "fixText": warning.fix_text,
        "imports": getattr(warning, "required_imports", []),
        "importsNeeded": [],
        "colStart": warning.col_start,
        "colEnd": warning.col_end,
        "highlight": warning.highlight,
        "proposal": warning.fix_proposal,
        "resolutionStatus": getattr(warning, "resolution_status", None),
        "resolutionDetails": getattr(warning, "resolution_details", None),
        "metadata": getattr(warning, "metadata", None),
    }
    payload["warningId"] = build_warning_id(payload)
    return payload


def build_warning_id(payload: Dict[str, object]) -> str:
    proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else {}
    edit = proposal.get("edit") if isinstance(proposal, dict) else None
    if not isinstance(edit, dict):
        edit = {}
    seed = {
        "file": payload.get("file"),
        "line": payload.get("line"),
        "type": payload.get("type"),
        "message": payload.get("message"),
        "colStart": payload.get("colStart"),
        "colEnd": payload.get("colEnd"),
        "original": payload.get("original"),
        "scope": edit.get("scope"),
        "editOriginal": edit.get("original_text"),
        "editReplacement": edit.get("replacement_text"),
    }
    raw = json.dumps(seed, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return "warn-%s-%s" % (payload.get("line"), digest)


def serialize_warnings_for_client(
    warnings: List[object],
    files_map: Dict[str, str],
) -> List[Dict[str, object]]:
    warnings_for_js = [warning_to_payload(warning) for warning in warnings]
    existing_imports_map: Dict[str, set] = {}
    for rel_path, text in files_map.items():
        existing_imports_map[rel_path] = canonicalize_imports_from_source(text)

    for item in warnings_for_js:
        rel = item["file"]
        existing = existing_imports_map.get(rel, set())
        required = normalize_required_imports(item.get("imports") or [])
        item["importsNeeded"] = [imp for imp in required if imp not in existing]
    return warnings_for_js
