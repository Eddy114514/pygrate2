#report_framework/framework.py

import os
import re
import subprocess
import importlib.util
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from apply_engine import build_fix_proposal
from services.file_service import build_tree_for_ui as _build_project_tree
from warning_fixes import WARNING_RULES


@dataclass
class WarningRecord:
    filename: str
    rel_filename: str
    lineno: int

    category: str
    message: str
    fix_text: Optional[str]
    line: str

    warning_type: str
    auto_fix_line: Optional[str] = None
    col_start: Optional[int] = None
    col_end: Optional[int] = None
    highlight: str = "unknown"
    required_imports: List[str] = field(default_factory=list)
    fix_proposal: Optional[Dict[str, object]] = None
    resolution_status: Optional[str] = None
    resolution_details: Optional[Dict[str, object]] = None

HEADER_RE = re.compile(
    r'^(?P<filename>.*?):(?P<lineno>\d+): (?P<category>[^:]+): (?P<msgfix>.*)$'
)


def _load_callsite_resolver():
    here = os.path.abspath(os.path.dirname(__file__))
    resolver_path = os.path.join(here, "resolve_warning_calls.py")
    if not os.path.exists(resolver_path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("resolve_warning_calls", resolver_path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except (SystemExit, Exception):
        return None


_CALLSITE_RESOLVER = _load_callsite_resolver()

def build_tree_for_ui(root):
    return _build_project_tree(root)


def _parse_warning_block(lines: List[str]):
    if not lines:
        return None

    m = HEADER_RE.match(lines[0])
    if not m:
        return None

    filename = m.group("filename")
    lineno = int(m.group("lineno"))
    category = m.group("category")
    msgfix = m.group("msgfix").strip()

    fix_text = None

    if "[fix=" in msgfix:
        msg_part, fix_part = msgfix.split("[fix=", 1)
        message = msg_part.strip()
        fix_text = fix_part.rstrip("]").strip()
    else:
        message = msgfix

    code_line = ""
    if len(lines) > 1 and lines[1].startswith("  "):
        code_line = lines[1].strip()

    return {
        "header": lines[0],
        "filename": filename,
        "lineno": lineno,
        "category": category,
        "message": message,
        "fix_text": fix_text,
        "line": code_line,
    }


def _resolve_warning_callsite(raw: dict, abs_filename: str, pygrate_root: Optional[str]):
    if _CALLSITE_RESOLVER is None:
        return None

    header = raw.get("header", "")
    if not header:
        return None

    py2_bin = None
    if pygrate_root:
        candidate = os.path.join(pygrate_root, "python")
        if os.path.exists(candidate):
            py2_bin = candidate

    try:
        resolved = _CALLSITE_RESOLVER.resolve_warning_callsite(
            header,
            py2_bin=py2_bin,
            source_path=abs_filename,
        )
    except Exception:
        return None
    return resolved


def _resolve_cmp_method_instance(raw: dict, resolved_callsite: Optional[dict]):
    if "the cmp method is not supported in 3.x" not in raw.get("message", ""):
        return None

    display_filename = raw.get("filename")
    display_lineno = raw.get("lineno")
    display_line = raw.get("line", "")
    col_start = 0
    col_end = len(display_line)
    resolution_status = "unresolved"
    resolution_details = None

    if resolved_callsite:
        resolved_call = resolved_callsite.get("resolved_call") or {}
        display_filename = resolved_callsite.get("source") or display_filename
        display_lineno = (
            resolved_call.get("line_start")
            or resolved_callsite.get("lineno")
            or display_lineno
        )
        call_line_text = resolved_callsite.get("line_text") or raw.get("line", "")
        if (
            resolved_call.get("line_start")
            and resolved_call.get("line_end")
            and resolved_call.get("line_start") != resolved_call.get("line_end")
        ):
            statement_text = resolved_callsite.get("statement_text") or ""
            display_line = statement_text.splitlines()[0] if statement_text else call_line_text
        else:
            display_line = (
                resolved_call.get("text")
                or resolved_callsite.get("callee")
                or call_line_text
                or raw.get("line", "")
            )
        col_start = resolved_call.get("col_start")
        col_end = resolved_call.get("col_end")
        resolution_status = resolved_callsite.get("resolution_status") or "resolved"
        resolution_details = {
            "callee": resolved_callsite.get("callee"),
            "knownCallees": resolved_callsite.get("known_callees"),
            "statementText": resolved_callsite.get("statement_text"),
            "offset": resolved_callsite.get("offset"),
        }

    if not isinstance(col_start, int) or not isinstance(col_end, int) or col_end < col_start:
        col_start = 0
        col_end = len(display_line)

    return {
        "filename": display_filename,
        "lineno": display_lineno,
        "warning_type": "CMP_METHOD_WARNING",
        "auto_fix_line": None,
        "display_line": display_line,
        "col_start": col_start,
        "col_end": col_end,
        "highlight": "cmp",
        "required_imports": [],
        "fix_proposal": None,
        "resolution_status": resolution_status,
        "resolution_details": resolution_details,
    }


def _extract_warning_blocks(stderr_text: str) -> List[List[str]]:
    """
    Split stderr text into a list of warning blocks.
    Each block is 1–2 lines corresponding to a single warning.
    """
    lines = stderr_text.splitlines()
    blocks: List[List[str]] = []
    cur: List[str] = []

    for line in lines:
        if HEADER_RE.match(line):
            if cur:
                blocks.append(cur)
            cur = [line]
        else:
            if cur:
                cur.append(line)

    if cur:
        blocks.append(cur)

    return blocks


def _read_source_line(path: str, lineno: int) -> str:
    if lineno <= 0:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for current_lineno, line in enumerate(f, start=1):
                if current_lineno == lineno:
                    return line.rstrip("\n")
    except Exception:
        return ""
    return ""


def _enrich_with_rule(raw: dict):
    """
    Given a raw parsed warning dict, apply WARNING_RULES to:
      - assign warning_type
      - compute auto_fix_line (if applicable)
      - decide which substring to highlight (highlight_span)
    """
    msg = raw.get("message", "")
    src = raw.get("line", "")

    instances = []

    default_warning_type = "GENERIC_WARNING"
    default_display_line = src

    for rule in WARNING_RULES:
        if rule.message_match not in msg:
            continue

        warning_type = rule.warning_type
        fix_kind = rule.fix_kind
        fix_scope = rule.fix_scope or "line"
        pattern = rule.pattern
        replacement = rule.replacement
        replacement_func = rule.replacement_func
        highlight_key = rule.highlight_mode
        rule_imports = list(rule.imports or [])

        if fix_scope == "line":
            auto_fix_line = None
            if fix_kind == "regex_sub" and pattern is not None:
                if callable(replacement):
                    new_line = pattern.sub(lambda m: replacement(m, raw), src)
                else:
                    new_line = pattern.sub(replacement, src)
                if new_line != src:
                    auto_fix_line = new_line
            elif fix_kind == "callable" and callable(replacement_func):
                new_line = replacement_func(src, raw)
                if isinstance(new_line, str) and new_line != src:
                    auto_fix_line = new_line

            highlight_start = 0
            highlight_end = len(src)
            if pattern is not None:
                m = pattern.search(src)
                if m:
                    highlight_start, highlight_end = m.start(), m.end()

            proposal = build_fix_proposal(
                filename=raw["filename"],
                rel_filename="",
                lineno=raw["lineno"],
                warning_type=warning_type,
                message=raw["message"],
                scope="line",
                original_text=src,
                replacement_text=auto_fix_line,
                col_start=None,
                col_end=None,
                required_imports=rule_imports,
            )

            instances.append(
                {
                    "warning_type": warning_type,
                    "auto_fix_line": auto_fix_line,
                    "display_line": src,
                    "col_start": highlight_start,
                    "col_end": highlight_end,
                    "highlight": highlight_key,
                    "required_imports": rule_imports,
                    "fix_proposal": proposal,
                }
            )

        elif fix_scope == "expression":
            matches = list(pattern.finditer(src)) if pattern is not None else []

            if matches:
                for m in matches:
                    expr = m.group(0)
                    start, end = m.start(), m.end()

                    auto_fix_line = None
                    if fix_kind == "regex_sub":
                        fixed_expr = pattern.sub(replacement, expr)
                        if fixed_expr != expr:
                            auto_fix_line = fixed_expr

                    proposal = build_fix_proposal(
                        filename=raw["filename"],
                        rel_filename="",
                        lineno=raw["lineno"],
                        warning_type=warning_type,
                        message=raw["message"],
                        scope="expression",
                        original_text=expr,
                        replacement_text=auto_fix_line,
                        col_start=start,
                        col_end=end,
                        required_imports=rule_imports,
                    )

                    instances.append(
                        {
                            "warning_type": warning_type,
                            "auto_fix_line": auto_fix_line,
                            "display_line": expr,
                            "col_start": start,
                            "col_end": end,
                            "highlight": highlight_key,
                            "required_imports": rule_imports,
                            "fix_proposal": proposal,
                        }
                    )

            else:
                auto_fix_line = None
                if fix_kind == "regex_sub" and pattern is not None:
                    new_line = pattern.sub(replacement, src)
                    if new_line != src:
                        auto_fix_line = new_line

                proposal = build_fix_proposal(
                    filename=raw["filename"],
                    rel_filename="",
                    lineno=raw["lineno"],
                    warning_type=warning_type,
                    message=raw["message"],
                    scope="expression",
                    original_text=src,
                    replacement_text=auto_fix_line,
                    col_start=0,
                    col_end=len(src),
                    required_imports=rule_imports,
                )

                instances.append(
                    {
                        "warning_type": warning_type,
                        "auto_fix_line": auto_fix_line,
                        "display_line": src,
                        "col_start": 0,
                        "col_end": len(src),
                        "highlight": highlight_key,
                        "required_imports": rule_imports,
                        "fix_proposal": proposal,
                    }
                )

        break

    if not instances:
        instances.append(
            {
                "warning_type": default_warning_type,
                "auto_fix_line": None,
                "display_line": default_display_line,
                "col_start": 0,
                "col_end": len(default_display_line),
                "highlight": "unknown",
                "required_imports": [],
                "fix_proposal": None,
            }
        )

    return instances






def _run_pygrate(file_path: str, pygrate_root: Optional[str] = None):
    """
    Execute pygrate2's ./python -3 <file_path> and return (stdout, stderr).
    """
    here = os.path.abspath(os.path.dirname(__file__))         # pygrate2/report_framework
    if pygrate_root is None:
        pygrate_root = os.path.abspath(os.path.join(here, ".."))  # pygrate2/

    python_exec = os.path.join(pygrate_root, "python")

    proc = subprocess.Popen(
        [python_exec, "-3", "-B", file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate()
    return stdout, stderr



def analyze_file_with_output(pygrate_root: Optional[str], project_root: str, file_path: str) -> Tuple[List[WarningRecord], str]:
    """
    Run pygrate on a single file and return (warnings, stdout).
    - project_root: root directory that defines the project (for relative paths).
    - file_path: absolute path or path relative to project_root.

    Only warnings whose filename lies under project_root are returned.
    """
    abs_root = os.path.abspath(project_root)
    if not os.path.isabs(file_path):
        abs_file = os.path.abspath(os.path.join(abs_root, file_path))
    else:
        abs_file = os.path.abspath(file_path)

    stdout, stderr = _run_pygrate(abs_file, pygrate_root)

    blocks = _extract_warning_blocks(stderr)
    results: List[WarningRecord] = []

    for blk in blocks:
        raw = _parse_warning_block(blk)
        if raw is None:
            continue

        abs_filename = os.path.abspath(raw["filename"])
        abs_root = os.path.abspath(project_root)
        if not abs_filename.startswith(abs_root):
            continue

        actual_line = _read_source_line(abs_filename, raw["lineno"])
        if actual_line:
            raw["line"] = actual_line

        # Avoid warning to print()
        if ("print must be called as a function" in raw["message"]
                and re.match(r'^\s*print\(', raw["line"])
            ):
            continue

        rel_filename = os.path.relpath(abs_filename, abs_root)
        resolved_callsite = _resolve_warning_callsite(raw, abs_filename, pygrate_root)
        cmp_instance = _resolve_cmp_method_instance(raw, resolved_callsite)
        instances = [cmp_instance] if cmp_instance else _enrich_with_rule(raw)
        for instance in instances:
            record_filename = abs_filename
            record_rel_filename = rel_filename
            instance_filename = instance.get("filename")
            if instance_filename:
                candidate_filename = os.path.abspath(instance_filename)
                if candidate_filename.startswith(abs_root):
                    record_filename = candidate_filename
                    record_rel_filename = os.path.relpath(candidate_filename, abs_root)

            record_lineno = instance.get("lineno", raw["lineno"])
            if not isinstance(record_lineno, int):
                record_lineno = raw["lineno"]

            proposal = instance.get("fix_proposal")
            if proposal is not None:
                proposal.rel_filename = record_rel_filename
            rec = WarningRecord(
                filename=record_filename,
                rel_filename=record_rel_filename,
                lineno=record_lineno,
                category=raw["category"],
                message=raw["message"],
                fix_text=raw["fix_text"],
                line=instance["display_line"],
                warning_type=instance["warning_type"],
                auto_fix_line=instance["auto_fix_line"],
                col_start=instance["col_start"],
                col_end=instance["col_end"],
                highlight=instance["highlight"],
                required_imports=instance["required_imports"],
                fix_proposal=proposal.to_dict() if proposal is not None else None,
                resolution_status=instance.get("resolution_status"),
                resolution_details=instance.get("resolution_details"),
            )
            results.append(rec)

    return results, stdout


def analyze_file(pygrate_root: Optional[str], project_root: str, file_path: str) -> List[WarningRecord]:
    warnings, _ = analyze_file_with_output(pygrate_root, project_root, file_path)
    return warnings


def analyze_directory(pygrate_root: Optional[str], project_root: str) -> List[WarningRecord]:
    abs_root = os.path.abspath(project_root)
    all_results: List[WarningRecord] = []

    for root, _, files in os.walk(abs_root):
        for f in files:
            if not f.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(root, f), abs_root)
            all_results.extend(analyze_file(pygrate_root, project_root, rel))

    return all_results
