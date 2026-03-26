import io
import os
import re
import sys
import tokenize

from apply_engine import build_fix_proposal
from models.rule_models import WarningRule, method_rename_rule

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENDOR_DIR = os.path.join(_ROOT_DIR, ".vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)

try:
    import parso

    _GRAMMAR27 = parso.load_grammar(version="2.7")
except Exception:
    _GRAMMAR27 = None


# ---------------------------------------------------------------------------
# Tiny generic helpers
# ---------------------------------------------------------------------------

def _children(node):
    return getattr(node, "children", ())


def _value(node):
    return getattr(node, "value", None)


def _node_type(node):
    return getattr(node, "type", None)


# ---------------------------------------------------------------------------
# BytesIO.truncate(0) structured fixer
# ---------------------------------------------------------------------------

def _trailer_is_attr(node, attr_name):
    if _node_type(node) != "trailer":
        return False
    kids = _children(node)
    return len(kids) >= 2 and _value(kids[0]) == "." and _value(kids[1]) == attr_name


def _number_is_zero(node):
    if _node_type(node) != "number":
        return False
    text = (_value(node) or "").strip().lower()
    if text.endswith("l"):
        text = text[:-1]
    try:
        return int(text, 0) == 0
    except Exception:
        return False


def _trailer_is_zero_call(node):
    if _node_type(node) != "trailer":
        return False
    kids = _children(node)
    return (
        len(kids) == 3
        and _value(kids[0]) == "("
        and _value(kids[2]) == ")"
        and _number_is_zero(kids[1])
    )


def _match_truncate_zero_call_on_power(node, line_text):
    if _node_type(node) != "power":
        return None

    kids = _children(node)
    if len(kids) < 3:
        return None

    for index in range(1, len(kids) - 1):
        attr = kids[index]
        call = kids[index + 1]
        if not _trailer_is_attr(attr, "truncate"):
            continue
        if not _trailer_is_zero_call(call):
            continue

        obj_start = kids[0].start_pos[1]
        attr_start = attr.start_pos[1]
        call_start = attr.start_pos[1]
        call_end = call.end_pos[1]
        obj_text = line_text[obj_start:attr_start].strip()
        if not obj_text:
            continue
        return {
            "obj": obj_text,
            "call_start": call_start,
            "call_end": call_end,
        }
    return None


def _collect_truncate_zero_calls(node, line_text, out):
    match = _match_truncate_zero_call_on_power(node, line_text)
    if match is not None:
        out.append(match)
    for child in _children(node):
        _collect_truncate_zero_calls(child, line_text, out)


def bytesio_truncate_fix(line: str, raw: dict):
    del raw
    if _GRAMMAR27 is None or not line:
        return line

    module = _GRAMMAR27.parse(line + "\n")
    top = _children(module)
    if not top:
        return line

    stmt = top[0]
    if _node_type(stmt) != "simple_stmt":
        return line

    matches = []
    _collect_truncate_zero_calls(stmt, line, matches)
    unique = {(m["call_start"], m["call_end"]): m for m in matches}
    matches = list(unique.values())
    if len(matches) != 1:
        return line

    match = matches[0]
    call_start = match["call_start"]
    call_end = match["call_end"]
    obj = match["obj"]
    if call_end <= call_start:
        return line

    replaced = line[:call_start] + ".truncate()" + line[call_end:]
    indent_len = len(replaced) - len(replaced.lstrip())
    indent = replaced[:indent_len]
    body = replaced[indent_len:]
    return f"{indent}{obj}.seek(0); {body}"


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def _warning_metadata(raw: dict):
    metadata = raw.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _metadata_bool(raw: dict, key: str):
    value = _warning_metadata(raw).get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes"):
            return True
        if lowered in ("0", "false", "no"):
            return False
    return None


def _decision_from_metadata_or_heuristic(raw: dict, info: dict, explicit_key: str, heuristic):
    explicit = _metadata_bool(raw, explicit_key)
    if explicit is not None:
        return explicit
    return heuristic(raw, info, _warning_metadata(raw))


# ---------------------------------------------------------------------------
# Token helpers for single-line statement parsing
# ---------------------------------------------------------------------------

def _iter_significant_tokens(line_text: str):
    try:
        stream = io.StringIO(line_text).readline
        for tok in tokenize.generate_tokens(stream):
            if tok.type in (
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.ENDMARKER,
                tokenize.COMMENT,
            ):
                continue
            yield tok
    except (tokenize.TokenError, IndentationError):
        return


def _token_slice_text(line_text: str, tokens):
    if not tokens:
        return ""
    return line_text[tokens[0].start[1] : tokens[-1].end[1]]


def _next_token_depth(depth: int, tok):
    if tok.type != tokenize.OP:
        return depth
    if tok.string in "([{":
        return depth + 1
    if tok.string in ")]}":
        return max(0, depth - 1)
    return depth


def _iter_top_level_tokens(tokens):
    depth = 0
    for tok in tokens:
        yield tok, depth
        depth = _next_token_depth(depth, tok)


def _consume_parenthesized_tokens(tokens, start_index: int):
    if start_index >= len(tokens) or tokens[start_index].string != "(":
        return None

    depth = 1
    inner = []
    index = start_index + 1
    while index < len(tokens):
        tok = tokens[index]
        if tok.type == tokenize.OP and tok.string in "([{" :
            depth += 1
            inner.append(tok)
            index += 1
            continue
        if tok.type == tokenize.OP and tok.string in ")]}":
            depth -= 1
            if depth == 0:
                return inner, index + 1
            inner.append(tok)
            index += 1
            continue
        inner.append(tok)
        index += 1
    return None


# ---------------------------------------------------------------------------
# Statement parsers (single physical line only)
# ---------------------------------------------------------------------------

def _parse_exec_statement(source_line: str):
    if not source_line:
        return None

    tokens = list(_iter_significant_tokens(source_line) or [])
    if not tokens or tokens[0].string != "exec":
        return None

    expr_tokens = []
    globals_tokens = []
    locals_tokens = []
    state = "expr"

    for tok, depth in _iter_top_level_tokens(tokens[1:]):
        if depth == 0 and tok.type == tokenize.NAME and tok.string == "in" and state == "expr":
            state = "globals"
            continue
        if depth == 0 and tok.type == tokenize.OP and tok.string == "," and state == "globals":
            state = "locals"
            continue

        if state == "expr":
            expr_tokens.append(tok)
        elif state == "globals":
            globals_tokens.append(tok)
        else:
            locals_tokens.append(tok)

    if not expr_tokens:
        return None
    if state != "expr" and not globals_tokens:
        return None
    if state == "locals" and not locals_tokens:
        return None

    tail = locals_tokens or globals_tokens or expr_tokens
    col_start = tokens[0].start[1]
    col_end = tail[-1].end[1]
    return {
        "statement_text": source_line[col_start:col_end],
        "col_start": col_start,
        "col_end": col_end,
        "expr_text": _token_slice_text(source_line, expr_tokens).strip(),
        "globals_text": _token_slice_text(source_line, globals_tokens).strip() or None,
        "locals_text": _token_slice_text(source_line, locals_tokens).strip() or None,
    }


def _parse_class_statement(source_line: str):
    if not source_line:
        return None

    tokens = list(_iter_significant_tokens(source_line) or [])
    if len(tokens) < 3 or tokens[0].string != "class" or tokens[1].type != tokenize.NAME:
        return None

    class_tok = tokens[0]
    name_tok = tokens[1]
    index = 2
    bases_tokens = []

    if tokens[index].string == ":":
        colon_tok = tokens[index]
    elif tokens[index].string == "(":
        consumed = _consume_parenthesized_tokens(tokens, index)
        if consumed is None:
            return None
        bases_tokens, index = consumed
        if index >= len(tokens) or tokens[index].string != ":":
            return None
        colon_tok = tokens[index]
    else:
        return None

    col_start = class_tok.start[1]
    col_end = colon_tok.end[1]
    return {
        "statement_text": source_line[col_start:col_end],
        "col_start": col_start,
        "col_end": col_end,
        "class_name": name_tok.string,
        "bases_text": _token_slice_text(source_line, bases_tokens).strip() or None,
    }


# ---------------------------------------------------------------------------
# Source / info builders
# ---------------------------------------------------------------------------

def _read_source_lines(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]
    except Exception:
        return []


def _build_statement_info(raw: dict, parsed: dict = None, **extra_fields):
    source_line = raw.get("line", "")
    info = {
        "filename": raw["filename"],
        "lineno": raw["lineno"],
        "expr_text": source_line,
        "source_line": source_line,
        "col_start": 0,
        "col_end": len(source_line),
        "multiline": False,
    }
    if parsed is not None:
        info.update(
            {
                "expr_text": parsed["statement_text"],
                "col_start": parsed["col_start"],
                "col_end": parsed["col_end"],
            }
        )
    info.update(extra_fields)
    return info


def _exec_statement_info(raw: dict):
    parsed = _parse_exec_statement(raw.get("line", ""))
    extra = {
        "exec_expr_text": None,
        "globals_text": None,
        "locals_text": None,
    }
    if parsed is not None:
        extra.update(
            {
                "exec_expr_text": parsed["expr_text"],
                "globals_text": parsed["globals_text"],
                "locals_text": parsed["locals_text"],
            }
        )
    return _build_statement_info(raw, parsed, **extra)


def _class_statement_info(raw: dict):
    parsed = _parse_class_statement(raw.get("line", ""))
    extra = {"class_name": None, "bases_text": None}
    if parsed is not None:
        extra.update(
            {
                "class_name": parsed["class_name"],
                "bases_text": parsed["bases_text"],
            }
        )
    return _build_statement_info(raw, parsed, **extra)


def _resolved_expression(raw: dict, resolved_callsite: dict):
    source_line = raw.get("line", "")
    expr_text = source_line
    filename = raw.get("filename")
    lineno = raw.get("lineno")
    col_start = 0
    col_end = len(source_line)
    multiline = False

    if resolved_callsite:
        resolved_call = resolved_callsite.get("resolved_call") or {}
        source_line = resolved_callsite.get("line_text") or source_line
        expr_text = resolved_call.get("text") or resolved_callsite.get("callee") or source_line
        filename = resolved_callsite.get("source") or filename
        lineno = resolved_call.get("line_start") or resolved_callsite.get("lineno") or lineno
        col_start = resolved_call.get("col_start")
        col_end = resolved_call.get("col_end")
        multiline = bool(
            resolved_call.get("line_start")
            and resolved_call.get("line_end")
            and resolved_call.get("line_start") != resolved_call.get("line_end")
        )

    if not isinstance(col_start, int) or not isinstance(col_end, int) or col_end < col_start:
        index = source_line.find(expr_text)
        if index >= 0:
            col_start = index
            col_end = index + len(expr_text)
        else:
            col_start = 0
            col_end = len(source_line)

    return {
        "filename": filename,
        "lineno": lineno,
        "expr_text": expr_text,
        "source_line": source_line,
        "col_start": col_start,
        "col_end": col_end,
        "multiline": multiline,
    }


# ---------------------------------------------------------------------------
# Instance construction
# ---------------------------------------------------------------------------

def _build_rule_instance(
    *,
    scope: str,
    filename: str,
    lineno: int,
    display_line: str,
    original_text: str,
    replacement_text,
    rule: WarningRule,
    col_start,
    col_end,
    required_imports=None,
    message=None,
    multiline=False,
):
    required_imports = list(required_imports or [])
    proposal = None
    if replacement_text is not None and (scope != "expression" or not multiline):
        proposal = build_fix_proposal(
            filename=filename,
            rel_filename="",
            lineno=lineno,
            warning_type=rule.warning_type,
            message=message or rule.message_match,
            scope=scope,
            original_text=original_text,
            replacement_text=replacement_text,
            col_start=col_start if scope == "expression" else None,
            col_end=col_end if scope == "expression" else None,
            required_imports=required_imports,
        )

    return {
        "filename": filename,
        "lineno": lineno,
        "warning_type": rule.warning_type,
        "auto_fix_line": replacement_text,
        "display_line": display_line,
        "col_start": col_start,
        "col_end": col_end,
        "highlight": rule.highlight_mode,
        "required_imports": required_imports,
        "fix_proposal": proposal,
    }


def _build_expression_instance(info: dict, rule: WarningRule, replacement_text=None, required_imports=None, message=None):
    return _build_rule_instance(
        scope="expression",
        filename=info["filename"],
        lineno=info["lineno"],
        display_line=info["expr_text"],
        original_text=info["expr_text"],
        replacement_text=replacement_text,
        rule=rule,
        col_start=info["col_start"],
        col_end=info["col_end"],
        required_imports=required_imports,
        message=message,
        multiline=info.get("multiline", False),
    )


def _build_line_instance(*, filename: str, lineno: int, source_line: str, replacement_text, rule: WarningRule, required_imports=None, message=None):
    return _build_rule_instance(
        scope="line",
        filename=filename,
        lineno=lineno,
        display_line=source_line,
        original_text=source_line,
        replacement_text=replacement_text,
        rule=rule,
        col_start=0,
        col_end=len(source_line),
        required_imports=required_imports,
        message=message,
    )


def _single_expression_builder_result(raw: dict, rule: WarningRule, info: dict, replacement_text=None, required_imports=None):
    return [
        _build_expression_instance(
            info,
            rule,
            replacement_text=replacement_text,
            required_imports=required_imports,
            message=raw.get("message"),
        )
    ]


def _warning_only_expression_result(raw: dict, rule: WarningRule, info: dict):
    return _single_expression_builder_result(raw, rule, info)


# ---------------------------------------------------------------------------
# Expression locating / refining
# ---------------------------------------------------------------------------

def _collect_matching_power_calls(node, pattern, out):
    if _node_type(node) == "power":
        text = node.get_code().strip()
        start = getattr(node, "start_pos", None)
        end = getattr(node, "end_pos", None)
        if pattern.match(text) and start is not None and end is not None and start[0] == end[0]:
            out.append(
                {
                    "expr_text": text,
                    "col_start": start[1],
                    "col_end": end[1],
                }
            )
    for child in _children(node):
        _collect_matching_power_calls(child, pattern, out)


def _unique_power_call_match(source_line: str, pattern):
    if _GRAMMAR27 is None or not source_line:
        return None

    module = _GRAMMAR27.parse(source_line + "\n")
    matches = []
    _collect_matching_power_calls(module, pattern, matches)
    unique = {(m["col_start"], m["col_end"]): m for m in matches}
    matches = list(unique.values())
    if len(matches) != 1:
        return None
    return matches[0]


def _refine_info_with_power_pattern(info: dict, pattern):
    match = _unique_power_call_match(info.get("source_line", ""), pattern)
    if match is None:
        return info
    refined = dict(info)
    refined.update(match)
    return refined


def _named_call_pattern(callee_name: str):
    return re.compile(r"^%s\(.*\)$" % re.escape(callee_name))


def _attr_call_pattern(attr_name: str):
    return re.compile(r"^.+\.%s\(\)$" % re.escape(attr_name))


def _qualified_call_pattern(call_target: str):
    return re.compile(r"^%s\(.*\)$" % re.escape(call_target))


def _static_info_resolver(info_builder):
    def resolver(raw: dict, resolved_callsite: dict):
        del resolved_callsite
        return info_builder(raw)

    return resolver


def _power_pattern_refiner(pattern):
    def refiner(raw: dict, info: dict):
        del raw
        return _refine_info_with_power_pattern(info, pattern)

    return refiner


# ---------------------------------------------------------------------------
# Generic builder engine
# ---------------------------------------------------------------------------

def _run_expression_builder(
    raw: dict,
    resolved_callsite: dict,
    rule: WarningRule,
    *,
    info_resolver=None,
    info_refiner=None,
    replacement_builder=None,
    required_imports_builder=None,
    allow_multiline_fix=False,
    fallback_to_warning_only=True,
):
    resolver = info_resolver or _resolved_expression
    info = resolver(raw, resolved_callsite)
    if info_refiner is not None:
        info = info_refiner(raw, info)

    replacement = None
    if replacement_builder is not None:
        replacement = replacement_builder(raw, info)
        if replacement is not None and info.get("multiline") and not allow_multiline_fix:
            replacement = None

    required_imports = None
    if required_imports_builder is not None:
        required_imports = required_imports_builder(raw, info, replacement)

    if replacement is None and not fallback_to_warning_only:
        return []
    return _single_expression_builder_result(
        raw,
        rule,
        info,
        replacement_text=replacement,
        required_imports=required_imports,
    )


def _make_expression_builder(
    *,
    info_resolver=None,
    info_refiner=None,
    replacement_builder=None,
    required_imports_builder=None,
    allow_multiline_fix=False,
    fallback_to_warning_only=True,
):
    def builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
        return _run_expression_builder(
            raw,
            resolved_callsite,
            rule,
            info_resolver=info_resolver,
            info_refiner=info_refiner,
            replacement_builder=replacement_builder,
            required_imports_builder=required_imports_builder,
            allow_multiline_fix=allow_multiline_fix,
            fallback_to_warning_only=fallback_to_warning_only,
        )

    return builder


# ---------------------------------------------------------------------------
# Semantic decision heuristics
# ---------------------------------------------------------------------------

def _wrapped_in_list_call(source_line: str, expr_text: str) -> bool:
    if not source_line or not expr_text:
        return False
    pattern = re.compile(r"\blist\(\s*%s\s*\)" % re.escape(expr_text))
    return bool(pattern.search(source_line))


def _looks_like_text_concat(source_line: str, expr_text: str) -> bool:
    if not source_line or not expr_text:
        return False
    string_lit = r"(?<![A-Za-z0-9_])(?:u|U)?(['\"]).*?\1"
    escaped = re.escape(expr_text)
    return bool(
        re.search(r"%s\s*\+\s*%s" % (string_lit, escaped), source_line)
        or re.search(r"%s\s*\+\s*%s" % (escaped, string_lit), source_line)
    )


def _materialization_required_heuristic(raw: dict, info: dict, metadata: dict):
    del raw
    consumer_op = metadata.get("consumer_op")
    callee_kind = metadata.get("callee_kind") or ""

    if consumer_op == "GET_ITER":
        return False
    if consumer_op in ("BINARY_ADD", "INPLACE_ADD", "STORE_SUBSCR"):
        return True
    if consumer_op == "BINARY_SUBSCR":
        return callee_kind.startswith("dict.")
    if consumer_op and consumer_op.startswith("CALL_FUNCTION"):
        return _wrapped_in_list_call(info["source_line"], info["expr_text"])
    return None


def _text_consumer_required_heuristic(raw: dict, info: dict, metadata: dict):
    del raw
    consumer_op = metadata.get("consumer_op")
    if consumer_op in ("BINARY_ADD", "INPLACE_ADD"):
        return _looks_like_text_concat(info["source_line"], info["expr_text"])
    return None


def _materialization_required(raw: dict, info: dict):
    return _decision_from_metadata_or_heuristic(
        raw,
        info,
        "materialization_required",
        _materialization_required_heuristic,
    )


def _text_consumer_required(raw: dict, info: dict):
    return _decision_from_metadata_or_heuristic(
        raw,
        info,
        "text_consumer",
        _text_consumer_required_heuristic,
    )


# ---------------------------------------------------------------------------
# Replacement builders
# ---------------------------------------------------------------------------

def _next_method_replacement(raw: dict, info: dict):
    del raw
    expr = info["expr_text"].strip()
    match = re.match(r"(?P<receiver>.+)\.next\(\)$", expr)
    if match:
        return "next(%s)" % match.group("receiver").strip()
    return None


def _intern_replacement(raw: dict, info: dict):
    del raw
    expr = info["expr_text"].strip()
    match = re.match(r"^intern\((?P<arg>.*)\)$", expr)
    if match:
        return "sys.intern(%s)" % match.group("arg")
    return None


def _range_materialization_replacement(raw: dict, info: dict):
    expr = info["expr_text"].strip()
    materialize = _materialization_required(raw, info)

    if expr.startswith("xrange("):
        base = "range(" + expr[len("xrange(") :]
        if materialize is True:
            return "list(%s)" % base
        if materialize is False:
            return base
    elif expr.startswith("range(") and materialize:
        return "list(%s)" % expr
    return None


def _dict_listlike_replacement(raw: dict, info: dict):
    expr = info["expr_text"].strip()
    if _materialization_required(raw, info) and re.match(r"^.+\.(keys|values|items)\(\)$", expr):
        return "list(%s)" % expr
    return None


def _base64_text_replacement(raw: dict, info: dict):
    expr = info["expr_text"].strip()
    if _text_consumer_required(raw, info) and not expr.endswith('.decode("ascii")'):
        return '%s.decode("ascii")' % expr
    return None


def _exec_statement_replacement(raw: dict, info: dict):
    del raw
    expr_text = info.get("exec_expr_text")
    globals_text = info.get("globals_text")
    locals_text = info.get("locals_text")
    if globals_text and locals_text:
        return "exec(%s, %s, %s)" % (expr_text, globals_text, locals_text)
    if globals_text:
        return "exec(%s, %s)" % (expr_text, globals_text)
    if expr_text:
        return "exec(%s)" % expr_text
    return None


def _old_style_class_replacement(raw: dict, info: dict):
    del raw
    class_name = info.get("class_name")
    bases_text = (info.get("bases_text") or "").strip()
    if class_name and not bases_text:
        return "class %s(object):" % class_name
    return None


def _constant_required_imports(imports):
    normalized = list(imports or [])

    def builder(raw: dict, info: dict, replacement):
        del raw, info, replacement
        return list(normalized)

    return builder


# ---------------------------------------------------------------------------
# StringIO / cStringIO compat helpers
# ---------------------------------------------------------------------------

def _stringio_target_constructor(raw: dict):
    metadata = _warning_metadata(raw)
    module_name = metadata.get("module_name")
    usage_kind = metadata.get("usage_kind")
    if module_name == "StringIO" and usage_kind == "text":
        return module_name, "StringIO"
    if module_name == "cStringIO" and usage_kind == "bytes":
        return module_name, "BytesIO"
    return module_name, None


def _find_unique_simple_import(filename: str, module_name: str, target_constructor: str, import_kind: str):
    if import_kind == "from":
        pattern = re.compile(r"^(?P<indent>\s*)from\s+%s\s+import\s+StringIO\s*$" % re.escape(module_name))
        replacement_text = lambda indent: "%sfrom io import %s" % (indent, target_constructor)
    elif import_kind == "import":
        pattern = re.compile(r"^(?P<indent>\s*)import\s+%s\s*$" % re.escape(module_name))
        replacement_text = lambda indent: "%simport io" % indent
    else:
        return None

    matches = []
    for lineno, line_text in enumerate(_read_source_lines(filename), start=1):
        match = pattern.match(line_text)
        if not match:
            continue
        indent = match.group("indent") or ""
        matches.append(
            {
                "filename": filename,
                "lineno": lineno,
                "source_line": line_text,
                "replacement_text": replacement_text(indent),
            }
        )

    if len(matches) != 1:
        return None
    return matches[0]


def _maybe_build_simple_import_rewrite(raw: dict, rule: WarningRule, *, filename: str, module_name: str, target_constructor: str, import_kind: str):
    match = _find_unique_simple_import(filename, module_name, target_constructor, import_kind)
    if match is None:
        return None
    return _build_line_instance(
        filename=match["filename"],
        lineno=match["lineno"],
        source_line=match["source_line"],
        replacement_text=match["replacement_text"],
        rule=rule,
        message=raw.get("message"),
    )


def _maybe_build_direct_constructor_rewrite(
    raw: dict,
    rule: WarningRule,
    info: dict,
    *,
    source_constructor: str,
    target_constructor: str,
    import_instance=None,
    required_imports=None,
):
    direct_call = _refine_info_with_power_pattern(info, _named_call_pattern(source_constructor))
    expr = direct_call["expr_text"].strip()
    match = re.match(r"^%s\((?P<args>.*)\)$" % re.escape(source_constructor), expr)
    if match is None:
        return None

    instances = []
    if import_instance is not None:
        instances.append(import_instance)

    if target_constructor != source_constructor or required_imports:
        replacement = "%s(%s)" % (target_constructor, match.group("args"))
        instances.extend(
            _single_expression_builder_result(
                raw,
                rule,
                direct_call,
                replacement_text=replacement,
                required_imports=required_imports,
            )
        )
    return instances or None


def _maybe_build_module_constructor_rewrite(
    raw: dict,
    rule: WarningRule,
    info: dict,
    *,
    module_name: str,
    target_constructor: str,
    import_instance=None,
    required_imports=None,
):
    module_call = _refine_info_with_power_pattern(info, _qualified_call_pattern("%s.StringIO" % module_name))
    expr = module_call["expr_text"].strip()
    match = re.match(r"^%s\.StringIO\((?P<args>.*)\)$" % re.escape(module_name), expr)
    if match is None:
        return None

    instances = []
    if import_instance is not None:
        instances.append(import_instance)

    replacement = "io.%s(%s)" % (target_constructor, match.group("args"))
    instances.extend(
        _single_expression_builder_result(
            raw,
            rule,
            module_call,
            replacement_text=replacement,
            required_imports=required_imports,
        )
    )
    return instances


def stringio_compat_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    module_name, target_constructor = _stringio_target_constructor(raw)
    if target_constructor is None:
        return _warning_only_expression_result(raw, rule, info)

    from_import = _maybe_build_simple_import_rewrite(
        raw,
        rule,
        filename=info["filename"],
        module_name=module_name,
        target_constructor=target_constructor,
        import_kind="from",
    )
    direct_required_imports = [] if from_import is not None else (["from io import BytesIO"] if target_constructor == "BytesIO" else [])
    instances = _maybe_build_direct_constructor_rewrite(
        raw,
        rule,
        info,
        source_constructor="StringIO",
        target_constructor=target_constructor,
        import_instance=from_import,
        required_imports=direct_required_imports,
    )
    if instances is not None:
        return instances

    plain_import = _maybe_build_simple_import_rewrite(
        raw,
        rule,
        filename=info["filename"],
        module_name=module_name,
        target_constructor=target_constructor,
        import_kind="import",
    )
    module_required_imports = [] if plain_import is not None else ["import io"]
    instances = _maybe_build_module_constructor_rewrite(
        raw,
        rule,
        info,
        module_name=module_name,
        target_constructor=target_constructor,
        import_instance=plain_import,
        required_imports=module_required_imports,
    )
    if instances is not None:
        return instances

    return _warning_only_expression_result(raw, rule, info)


# ---------------------------------------------------------------------------
# Concrete builder instances
# ---------------------------------------------------------------------------

next_method_builder = _make_expression_builder(
    info_refiner=_power_pattern_refiner(_attr_call_pattern("next")),
    replacement_builder=_next_method_replacement,
)

intern_builder = _make_expression_builder(
    info_refiner=_power_pattern_refiner(_named_call_pattern("intern")),
    replacement_builder=_intern_replacement,
    required_imports_builder=_constant_required_imports(["import sys"]),
)

range_materialization_builder = _make_expression_builder(
    replacement_builder=_range_materialization_replacement,
)

dict_listlike_builder = _make_expression_builder(
    replacement_builder=_dict_listlike_replacement,
)

base64_text_builder = _make_expression_builder(
    replacement_builder=_base64_text_replacement,
)

exec_statement_builder = _make_expression_builder(
    info_resolver=_static_info_resolver(_exec_statement_info),
    replacement_builder=_exec_statement_replacement,
)

exec_scope_builder = _make_expression_builder(
    info_resolver=_static_info_resolver(_exec_statement_info),
)

old_style_class_builder = _make_expression_builder(
    info_resolver=_static_info_resolver(_class_statement_info),
    replacement_builder=_old_style_class_replacement,
)

mro_risk_builder = _make_expression_builder(
    info_resolver=_static_info_resolver(_class_statement_info),
)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

WARNING_RULES = [
    # Builder-driven compat and semantic rules.
    WarningRule(
        name="cstringio_module",
        warning_type="CSTRINGIO_WARNING",
        message_match="cStringIO module is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="stringio",
        instance_builder=stringio_compat_builder,
        regex_grade="B",
        notes="Auto-fix is limited to direct cStringIO import/call forms.",
    ),
    WarningRule(
        name="stringio_module",
        warning_type="STRINGIO_WARNING",
        message_match="StringIO module is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="stringio",
        instance_builder=stringio_compat_builder,
        regex_grade="B",
        notes="Auto-fix is limited to direct StringIO import/call forms.",
    ),
    WarningRule(
        name="old_style_class",
        warning_type="OLD_STYLE_CLASS_WARNING",
        message_match="old-style classes are not supported in 3.x",
        fix_scope="expression",
        highlight_mode="class",
        instance_builder=old_style_class_builder,
        regex_grade="A",
        notes="Only auto-fixes classic classes that omit explicit bases.",
    ),
    WarningRule(
        name="mro_risk",
        warning_type="MRO_RISK_WARNING",
        message_match="classic-class multiple inheritance may change MRO in 3.x",
        fix_scope="expression",
        highlight_mode="class",
        instance_builder=mro_risk_builder,
        regex_grade="B",
        notes="Warning-only for classic multiple inheritance; manual review required.",
    ),
    WarningRule(
        name="exec_statement",
        warning_type="EXEC_STATEMENT_WARNING",
        message_match="exec statement is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="exec",
        instance_builder=exec_statement_builder,
        regex_grade="B",
        notes="Uses token-aware parsing for the safe exec-statement subset.",
    ),
    WarningRule(
        name="exec_scope",
        warning_type="EXEC_SCOPE_WARNING",
        message_match="exec scope semantics may require manual review in 3.x",
        fix_scope="expression",
        highlight_mode="exec",
        instance_builder=exec_scope_builder,
        regex_grade="B",
        notes="Warning-only for now; metadata is preserved for future semantic fixes.",
    ),
    WarningRule(
        name="next_method",
        warning_type="NEXT_METHOD_WARNING",
        message_match="iterator.next() is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="next",
        instance_builder=next_method_builder,
        regex_grade="A",
        notes="Auto-fix is only offered when the warning carries a resolved iterator callsite.",
    ),
    WarningRule(
        name="intern_builtin",
        warning_type="INTERN_WARNING",
        message_match="intern() is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="intern",
        instance_builder=intern_builder,
        imports=("import sys",),
        regex_grade="A",
    ),
    WarningRule(
        name="range_materialization_xrange",
        warning_type="RANGE_MATERIALIZATION_WARNING",
        message_match="xrange() is not supported in 3.x",
        fix_scope="expression",
        highlight_mode="range",
        instance_builder=range_materialization_builder,
        regex_grade="B",
        notes="Materialization is metadata-driven for now; only a small set of consumer patterns is recognized.",
    ),
    WarningRule(
        name="range_materialization_range",
        warning_type="RANGE_MATERIALIZATION_WARNING",
        message_match="range() may require list materialization in 3.x",
        fix_scope="expression",
        highlight_mode="range",
        instance_builder=range_materialization_builder,
        regex_grade="B",
        notes="First pass only handles explicit consumer metadata coming from pygrate2.",
    ),
    WarningRule(
        name="dict_listlike_keys",
        warning_type="DICT_LISTLIKE_WARNING",
        message_match="dict.keys() may require list materialization in 3.x",
        fix_scope="expression",
        highlight_mode="dict",
        instance_builder=dict_listlike_builder,
        regex_grade="B",
    ),
    WarningRule(
        name="dict_listlike_values",
        warning_type="DICT_LISTLIKE_WARNING",
        message_match="dict.values() may require list materialization in 3.x",
        fix_scope="expression",
        highlight_mode="dict",
        instance_builder=dict_listlike_builder,
        regex_grade="B",
    ),
    WarningRule(
        name="dict_listlike_items",
        warning_type="DICT_LISTLIKE_WARNING",
        message_match="dict.items() may require list materialization in 3.x",
        fix_scope="expression",
        highlight_mode="dict",
        instance_builder=dict_listlike_builder,
        regex_grade="B",
    ),
    WarningRule(
        name="base64_b64encode",
        warning_type="BASE64_B64ENCODE_WARNING",
        message_match="base64.b64encode returns str in Python 2",
        fix_scope="expression",
        highlight_mode="base64",
        instance_builder=base64_text_builder,
        regex_grade="B",
        notes="Auto-fix is gated on metadata that says the encoded value is consumed as text.",
    ),
    WarningRule(
        name="base64_b32encode",
        warning_type="BASE64_B32ENCODE_WARNING",
        message_match="base64.b32encode returns str in Python 2",
        fix_scope="expression",
        highlight_mode="base64",
        instance_builder=base64_text_builder,
        regex_grade="B",
        notes="Auto-fix is gated on metadata that says the encoded value is consumed as text.",
    ),
    WarningRule(
        name="base64_b16encode",
        warning_type="BASE64_B16ENCODE_WARNING",
        message_match="base64.b16encode returns str in Python 2",
        fix_scope="expression",
        highlight_mode="base64",
        instance_builder=base64_text_builder,
        regex_grade="B",
        notes="Auto-fix is gated on metadata that says the encoded value is consumed as text.",
    ),
    # Declarative regex/callable rules.
    WarningRule(
        name="print_statement",
        warning_type="PRINT_WARNING",
        message_match="print must be called as a function",
        fix_kind="regex_sub",
        pattern=re.compile(r"print\s+(.+)"),
        replacement=r"print(\1)",
        fix_scope="line",
        highlight_mode="print",
        regex_grade="B",
        notes="Still regex-based; complex print redirection and trailing comma forms remain fragile.",
    ),
    WarningRule(
        name="dict_has_key",
        warning_type="HAS_KEY_WARNING",
        message_match="dict.has_key() not supported",
        fix_kind="regex_sub",
        pattern=re.compile(r"(?P<obj>[A-Za-z_][\w\.\[\]]*)\.has_key\(\s*(?P<key>.+?)\s*\)"),
        replacement=r"\g<key> in \g<obj>",
        fix_scope="expression",
        highlight_mode="haskey",
        regex_grade="C",
        notes="Useful today, but nested calls and richer receiver expressions should eventually use structured matching.",
    ),
    method_rename_rule(
        name="dict_viewkeys",
        warning_type="DICT_VIEWKEYS_WARNING",
        message_match="dict.viewkeys() is not supported in 3.x",
        method_name="viewkeys",
        replacement_method="keys",
    ),
    method_rename_rule(
        name="dict_viewvalues",
        warning_type="DICT_VIEWVALUES_WARNING",
        message_match="dict.viewvalues() is not supported in 3.x",
        method_name="viewvalues",
        replacement_method="values",
    ),
    method_rename_rule(
        name="dict_viewitems",
        warning_type="DICT_VIEWITEMS_WARNING",
        message_match="dict.viewitems() is not supported in 3.x",
        method_name="viewitems",
        replacement_method="items",
    ),
    method_rename_rule(
        name="dict_iterkeys",
        warning_type="DICT_ITERKEYS_WARNING",
        message_match="dict.iterkeys() is not supported in 3.x",
        method_name="iterkeys",
        replacement_method="keys",
    ),
    method_rename_rule(
        name="dict_itervalues",
        warning_type="DICT_ITERVALUES_WARNING",
        message_match="dict.itervalues() is not supported in 3.x",
        method_name="itervalues",
        replacement_method="values",
    ),
    method_rename_rule(
        name="dict_iteritems",
        warning_type="DICT_ITERITEMS_WARNING",
        message_match="dict.iteritems() is not supported in 3.x",
        method_name="iteritems",
        replacement_method="items",
    ),
    WarningRule(
        name="buffer_builtin",
        warning_type="BUFFER_WARNING",
        message_match="buffer() not supported in 3.x",
        fix_kind="regex_sub",
        pattern=re.compile(r"\bbuffer\(\s*(?P<arg>.+?)\s*\)"),
        replacement=r"memoryview(\g<arg>)",
        fix_scope="expression",
        highlight_mode="buffer",
        regex_grade="A",
    ),
    WarningRule(
        name="file_constructor",
        warning_type="FILE_CONSTRUCTOR_WARNING",
        message_match="The builtin 'file()'/'open()' function is not supported in 3.x",
        fix_scope="line",
        highlight_mode="fileio",
        regex_grade="B",
        notes="Presentation-only today; no backend auto-fix proposal.",
    ),
    WarningRule(
        name="bytesio_truncate",
        warning_type="BYTESIO_TRUNCATE_WARNING",
        message_match="BytesIO.truncate() does not shift the file pointer",
        fix_kind="callable",
        replacement_func=bytesio_truncate_fix,
        fix_scope="line",
        highlight_mode="bytesio",
        regex_grade="A",
    ),
    WarningRule(
        name="tokenize_behavior",
        warning_type="TOKENIZE_WARNING",
        message_match="tokenize() changed in 3.x",
        fix_scope="line",
        highlight_mode="tokenize",
        regex_grade="B",
        notes="No auto-fix yet.",
    ),
    WarningRule(
        name="cmp_argument",
        warning_type="CMP_ARG_WARNING",
        message_match="the cmp argument is not supported in 3.x",
        fix_kind="regex_sub",
        pattern=re.compile(r"\bcmp\s*=\s*(?P<cmp>[^,\)\]]+)"),
        replacement=r"key=cmp_to_key(\g<cmp>)",
        fix_scope="line",
        highlight_mode="cmp",
        imports=("from functools import cmp_to_key",),
        regex_grade="C",
        notes="Still regex-based; nested expressions and multiline kwargs should eventually use structured matching.",
    ),
]


__all__ = ["WARNING_RULES", "bytesio_truncate_fix"]
