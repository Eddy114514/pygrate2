#report_framework/framework.py

import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

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

HEADER_RE = re.compile(
    r'^(?P<filename>.*?):(?P<lineno>\d+): (?P<category>[^:]+): (?P<msgfix>.*)$'
)


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
        "filename": filename,
        "lineno": lineno,
        "category": category,
        "message": message,
        "fix_text": fix_text,
        "line": code_line,
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
        if rule["message_contains"] not in msg:
            continue

        warning_type = rule["warning_type"]
        fix_kind = rule.get("fix_kind")
        fix_scope = rule.get("fix_scope", "line")
        pattern = rule.get("pattern")
        replacement = rule.get("replacement")

        if fix_scope == "line":
            auto_fix_line = None
            if fix_kind == "regex_sub" and pattern is not None:
                new_line = pattern.sub(replacement, src)
                if new_line != src:
                    auto_fix_line = new_line

            instances.append((warning_type, auto_fix_line, src, 0, len(src)))

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

                    instances.append((warning_type, auto_fix_line, expr, start, end))

            else:
                auto_fix_line = None
                if fix_kind == "regex_sub" and pattern is not None:
                    new_line = pattern.sub(replacement, src)
                    if new_line != src:
                        auto_fix_line = new_line

                instances.append((warning_type, auto_fix_line, src, 0, len(src)))

        break

    if not instances:
        instances.append((default_warning_type, None, default_display_line, 0, len(default_display_line)))

    return instances






def _run_pygrate(file_path: str):
    """
    Execute pygrate2's ./python -3 <file_path> and return (stdout, stderr).
    """
    here = os.path.abspath(os.path.dirname(__file__))         # pygrate2/report_framework
    pygrate_root = os.path.abspath(os.path.join(here, ".."))  # pygrate2/
    python_exec = os.path.join(pygrate_root, "python")

    proc = subprocess.Popen(
        [python_exec, "-3", file_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate()
    return stdout, stderr



def analyze_file_with_output(project_root: str, file_path: str) -> Tuple[List[WarningRecord], str]:
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

    stdout, stderr = _run_pygrate(abs_file)

    blocks = _extract_warning_blocks(stderr)
    results: List[WarningRecord] = []

    for blk in blocks:
        raw = _parse_warning_block(blk)
        if raw is None:
            continue

        abs_filename = os.path.abspath(raw["filename"])
        if abs_filename != abs_file:
            continue
        
        # Avoid warning to print()
        re.sub(r' {2,}', ' ', raw["line"])
        if ("print must be called as a function" in raw["message"]
                and re.match(r'^\s*print\(', raw["line"])
            ):
            continue

        rel_filename = os.path.relpath(abs_filename, abs_root)
        instances = _enrich_with_rule(raw)

        for warning_type, auto_fix_line, display_line, col_start, col_end in instances:
            rec = WarningRecord(
                filename=abs_filename,
                rel_filename=rel_filename,
                lineno=raw["lineno"],
                category=raw["category"],
                message=raw["message"],
                fix_text=raw["fix_text"],
                line=display_line,
                warning_type=warning_type,
                auto_fix_line=auto_fix_line,
                col_start=col_start,
                col_end=col_end,
            )
            results.append(rec)

    return results, stdout


def analyze_file(project_root: str, file_path: str) -> List[WarningRecord]:
    warnings, _ = analyze_file_with_output(project_root, file_path)
    return warnings


def analyze_directory(project_root: str) -> List[WarningRecord]:

    abs_root = os.path.abspath(project_root)
    all_results: List[WarningRecord] = []

    for root, _, files in os.walk(abs_root):
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(root, f)
            all_results.extend(analyze_file(abs_root, fp))

    return all_results
