#report_framework/framework.py

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from treelib import Node, Tree

from warning_fixes import WARNING_RULES, _should_collect_text_evidence

try:
    from lib2to3 import pygram, pytree
    from lib2to3.pgen2 import driver, token as pgen_token
    from lib2to3.pygram import python_symbols as syms
    _L2TO3_DRIVER = driver.Driver(pygram.python_grammar, convert=pytree.convert)
except Exception:
    _L2TO3_DRIVER = None
    pgen_token = None
    syms = None


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
    observed: Optional[dict] = None

HEADER_RE = re.compile(
    r'^(?P<filename>.*?):(?P<lineno>\d+): (?P<category>[^:]+): (?P<msgfix>.*)$'
)


def _extract_vars_from_tokens(tokens_line):
    data_vars = set()
    file_vars = set()
    if not tokens_line or pgen_token is None:
        return data_vars, file_vars

    for i, tok in enumerate(tokens_line[:-1]):
        if tok.type == pgen_token.NAME and tok.value == "as":
            nxt = tokens_line[i + 1]
            if nxt.type == pgen_token.NAME:
                file_vars.add(nxt.value)

    eq_idx = None
    for i, tok in enumerate(tokens_line):
        if tok.value == "=":
            eq_idx = i
            break

    assign_target = None
    if eq_idx is not None:
        j = eq_idx - 1
        while j >= 0:
            tok = tokens_line[j]
            if tok.type == pgen_token.NAME:
                if j > 0 and tokens_line[j - 1].value == ".":
                    j -= 1
                    continue
                assign_target = tok.value
                break
            j -= 1

    def rhs_has_read_call(start_idx):
        for k in range(start_idx, len(tokens_line) - 2):
            tok = tokens_line[k]
            if tok.value == ".":
                nxt = tokens_line[k + 1]
                if nxt.type == pgen_token.NAME and nxt.value in ("read", "readline", "readlines"):
                    return True
        return False

    if assign_target is not None and eq_idx is not None:
        if rhs_has_read_call(eq_idx + 1):
            data_vars.add(assign_target)
        else:
            file_vars.add(assign_target)

    return data_vars, file_vars


def _is_unicode_literal_token(value: str) -> bool:
    v = value.lstrip().lower()
    return (
        v.startswith("u'") or v.startswith('u"')
        or v.startswith("ur'") or v.startswith('ur"')
        or v.startswith("ru'") or v.startswith('ru"')
    )


def _lib2to3_tree(src: str):
    if _L2TO3_DRIVER is None:
        return None
    try:
        return _L2TO3_DRIVER.parse_string(src)
    except Exception:
        return None


def _lib2to3_leaves(src: str):
    tree = _lib2to3_tree(src)
    if tree is None:
        return []
    return list(tree.leaves())


def _node_span(node):
    min_ln = None
    max_ln = None
    for leaf in node.leaves():
        ln = getattr(leaf, "lineno", None)
        if ln is None:
            continue
        if min_ln is None or ln < min_ln:
            min_ln = ln
        if max_ln is None or ln > max_ln:
            max_ln = ln
    return min_ln, max_ln


def _find_enclosing_suite(tree, lineno: int):
    if tree is None or syms is None:
        return None
    best = None
    best_span = None
    exact = None
    exact_span = None
    for node in tree.pre_order():
        if not isinstance(node, pytree.Node):
            continue
        suite = None
        for child in node.children:
            if isinstance(child, pytree.Node) and child.type == syms.suite:
                suite = child
                break
        if suite is None:
            continue
        min_ln, max_ln = _node_span(node)
        if min_ln is None or max_ln is None:
            continue
        if min_ln == lineno:
            span = max_ln - min_ln
            if exact is None or span < exact_span:
                exact = suite
                exact_span = span
        if min_ln <= lineno <= max_ln:
            span = max_ln - min_ln
            if best is None or span < best_span:
                best = suite
                best_span = span
    return exact or best


def _var_in_call_args(tokens, start_idx: int, var_name: str) -> bool:
    depth = 0
    for j in range(start_idx, len(tokens)):
        tok = tokens[j]
        val = tok.value
        if val == "(":
            depth += 1
            continue
        if val == ")":
            if depth == 1:
                return False
            depth = max(0, depth - 1)
            continue
        if depth >= 1 and tok.type == pgen_token.NAME and tok.value == var_name:
            return True
    return False


def _tokens_have_text_evidence(tokens, vars_to_check) -> bool:
    if not tokens or pgen_token is None:
        return False
    for i, tok in enumerate(tokens):
        if tok.type == pgen_token.NAME and tok.value in vars_to_check:
            if i + 2 < len(tokens) and tokens[i + 1].value == ".":
                nxt = tokens[i + 2]
                if nxt.type == pgen_token.NAME and nxt.value in ("encode", "decode"):
                    return True

            if i + 2 < len(tokens) and tokens[i + 1].value == "+":
                nxt = tokens[i + 2]
                if nxt.type == pgen_token.STRING and _is_unicode_literal_token(nxt.value):
                    return True
            if i >= 2 and tokens[i - 1].value == "+":
                prev = tokens[i - 2]
                if prev.type == pgen_token.STRING and _is_unicode_literal_token(prev.value):
                    return True

            if i >= 2 and tokens[i - 1].value == "(":
                prev = tokens[i - 2]
                if prev.type == pgen_token.NAME and prev.value == "unicode":
                    return True

            if (
                i >= 2
                and tokens[i - 1].value == "("
                and tokens[i - 2].type == pgen_token.NAME
                and tokens[i - 2].value == "isinstance"
            ):
                if i + 2 < len(tokens) and tokens[i + 1].value == ",":
                    nxt = tokens[i + 2]
                    if nxt.type == pgen_token.NAME and nxt.value == "unicode":
                        return True

        if tok.type == pgen_token.STRING and _is_unicode_literal_token(tok.value):
            if i + 1 < len(tokens) and tokens[i + 1].value == "%":
                if i + 2 < len(tokens) and tokens[i + 2].type == pgen_token.NAME and tokens[i + 2].value in vars_to_check:
                    return True
                if i + 2 < len(tokens) and tokens[i + 2].value == "(":
                    for var in vars_to_check:
                        if _var_in_call_args(tokens, i + 2, var):
                            return True
            if i + 3 < len(tokens) and tokens[i + 1].value == ".":
                if tokens[i + 2].type == pgen_token.NAME and tokens[i + 2].value == "format" and tokens[i + 3].value == "(":
                    for var in vars_to_check:
                        if _var_in_call_args(tokens, i + 3, var):
                            return True
    return False


def _collect_text_evidence(lines: List[str], lineno: int) -> bool:
    if lineno <= 0 or lineno > len(lines):
        return False

    tree = _lib2to3_tree("".join(lines))
    if tree is None:
        return False

    suite = _find_enclosing_suite(tree, lineno)
    suite_tokens = list(suite.leaves()) if suite is not None else list(tree.leaves())

    tokens_by_line = {}
    for t in suite_tokens:
        if hasattr(t, "lineno") and t.lineno is not None:
            tokens_by_line.setdefault(t.lineno, []).append(t)

    data_vars, file_vars = _extract_vars_from_tokens(tokens_by_line.get(lineno, []))

    for line_no in sorted(tokens_by_line.keys()):
        if line_no < lineno:
            continue
        line_tokens = tokens_by_line.get(line_no, [])
        new_data, new_files = _extract_vars_from_tokens(line_tokens)
        if new_files:
            file_vars.update(new_files)
        if new_data:
            data_vars.update(new_data)

    if not data_vars:
        return False

    scoped_tokens = [
        t for t in suite_tokens
        if hasattr(t, "lineno") and t.lineno is not None and t.lineno >= lineno
    ]
    return _tokens_have_text_evidence(scoped_tokens, data_vars)

def build_tree_for_ui(root):
    tree = {}

    for dirpath, dirs, files in os.walk(root):
        rel = os.path.relpath(dirpath, root)

        node = tree
        if rel != ".":
            for part in rel.split(os.sep):
                node = node.setdefault(part, {})

        file_list = node.setdefault("__files__", [])
        for f in files:
            if f.endswith(".py"):
                file_list.append(f)

    return tree


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
    observed_info = None
    observed_match = re.search(r'\(observed ([^)]*)\)', msgfix)
    if observed_match:
        observed_text = observed_match.group(1)
        observed_info = {}
        for part in observed_text.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                observed_info[k.strip()] = v.strip()
            elif part:
                observed_info[part] = True

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
        "observed": observed_info,
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
    print(msg)

    for rule in WARNING_RULES:
        if rule["message_contains"] not in msg:
            continue

        warning_type = rule["warning_type"]
        fix_kind = rule.get("fix_kind")
        fix_scope = rule.get("fix_scope", "line")
        pattern = rule.get("pattern")
        replacement = rule.get("replacement")
        replacement_func = rule.get("replacement_func")
        highlight_key = rule.get("highlight")
        rule_imports = rule.get("imports") or []
        if not isinstance(rule_imports, list):
            rule_imports = [str(rule_imports)]

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

            instances.append(
                (
                    warning_type,
                    auto_fix_line,
                    src,
                    highlight_start,
                    highlight_end,
                    highlight_key,
                    rule_imports,
                    raw.get("observed"),
                )
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

                    instances.append(
                        (
                            warning_type,
                            auto_fix_line,
                            expr,
                            start,
                            end,
                            highlight_key,
                            rule_imports,
                            raw.get("observed"),
                        )
                    )

            else:
                auto_fix_line = None
                if fix_kind == "regex_sub" and pattern is not None:
                    new_line = pattern.sub(replacement, src)
                    if new_line != src:
                        auto_fix_line = new_line

                instances.append(
                    (
                        warning_type,
                        auto_fix_line,
                        src,
                        0,
                        len(src),
                        highlight_key,
                        rule_imports,
                        raw.get("observed"),
                    )
                )

        break

    if not instances:
        instances.append(
            (default_warning_type, None, default_display_line, 0, len(default_display_line), "unknown", [], raw.get("observed"))
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
    file_lines_cache: dict = {}

    for blk in blocks:
        raw = _parse_warning_block(blk)
        if raw is None:
            continue

        abs_filename = os.path.abspath(raw["filename"])
        abs_root = os.path.abspath(project_root)
        if not abs_filename.startswith(abs_root):
            continue

        
        # Avoid warning to print()
        raw["line"] = re.sub(r' {2,}', ' ', raw["line"])
        if ("print must be called as a function" in raw["message"]
                and re.match(r'^\s*print\(', raw["line"])
            ):
            continue

        rel_filename = os.path.relpath(abs_filename, abs_root)

        if _should_collect_text_evidence(raw.get("message", "")):
            lines = file_lines_cache.get(abs_filename)
            if lines is None:
                try:
                    with open(abs_filename, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                except Exception:
                    lines = []
                file_lines_cache[abs_filename] = lines
            raw["text_evidence"] = _collect_text_evidence(lines, raw["lineno"])
        instances = _enrich_with_rule(raw)
        for (
            warning_type,
            auto_fix_line,
            display_line,
            col_start,
            col_end,
            highlight_key,
            required_imports,
            observed,
        ) in instances:
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
                highlight=highlight_key,
                required_imports=required_imports,
                observed=observed,
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
