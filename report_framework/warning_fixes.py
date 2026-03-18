import os
import re
import sys

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


def _children(node):
    return getattr(node, "children", ())


def _value(node):
    return getattr(node, "value", None)


def _node_type(node):
    return getattr(node, "type", None)


def _trailer_is_attr_truncate(node):
    if _node_type(node) != "trailer":
        return False
    kids = _children(node)
    return (
        len(kids) >= 2
        and _value(kids[0]) == "."
        and _value(kids[1]) == "truncate"
    )


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

    for i in range(1, len(kids) - 1):
        attr = kids[i]
        call = kids[i + 1]
        if not _trailer_is_attr_truncate(attr):
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
    m = _match_truncate_zero_call_on_power(node, line_text)
    if m is not None:
        out.append(m)
    for ch in _children(node):
        _collect_truncate_zero_calls(ch, line_text, out)


def bytesio_truncate_fix(line: str, raw: dict):
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
    unique = {}
    for m in matches:
        unique[(m["call_start"], m["call_end"])] = m
    matches = list(unique.values())
    if len(matches) != 1:
        return line

    m = matches[0]
    call_start = m["call_start"]
    call_end = m["call_end"]
    obj = m["obj"]
    if call_end <= call_start:
        return line

    replaced = line[:call_start] + ".truncate()" + line[call_end:]
    indent_len = len(replaced) - len(replaced.lstrip())
    indent = replaced[:indent_len]
    body = replaced[indent_len:]
    return f"{indent}{obj}.seek(0); {body}"


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
        expr_text = (
            resolved_call.get("text")
            or resolved_callsite.get("callee")
            or source_line
        )
        filename = resolved_callsite.get("source") or filename
        lineno = (
            resolved_call.get("line_start")
            or resolved_callsite.get("lineno")
            or lineno
        )
        col_start = resolved_call.get("col_start")
        col_end = resolved_call.get("col_end")
        multiline = (
            resolved_call.get("line_start")
            and resolved_call.get("line_end")
            and resolved_call.get("line_start") != resolved_call.get("line_end")
        )

    if not isinstance(col_start, int) or not isinstance(col_end, int) or col_end < col_start:
        idx = source_line.find(expr_text)
        if idx >= 0:
            col_start = idx
            col_end = idx + len(expr_text)
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


def _collect_matching_power_calls(node, pattern, out):
    if _node_type(node) == "power":
        text = node.get_code().strip()
        start = getattr(node, "start_pos", None)
        end = getattr(node, "end_pos", None)
        if (
            pattern.match(text)
            and start is not None
            and end is not None
            and start[0] == end[0]
        ):
            out.append(
                {
                    "expr_text": text,
                    "col_start": start[1],
                    "col_end": end[1],
                }
            )
    for ch in _children(node):
        _collect_matching_power_calls(ch, pattern, out)


def _unique_power_call_match(source_line: str, pattern):
    if _GRAMMAR27 is None or not source_line:
        return None

    module = _GRAMMAR27.parse(source_line + "\n")
    matches = []
    _collect_matching_power_calls(module, pattern, matches)
    unique = {}
    for match in matches:
        unique[(match["col_start"], match["col_end"])] = match
    matches = list(unique.values())
    if len(matches) != 1:
        return None
    return matches[0]


def _refine_info_to_named_call(info: dict, callee_name: str):
    pattern = re.compile(r"^%s\(.*\)$" % re.escape(callee_name))
    match = _unique_power_call_match(info.get("source_line", ""), pattern)
    if match is None:
        return info
    refined = dict(info)
    refined.update(match)
    return refined


def _refine_info_to_attr_call(info: dict, attr_name: str):
    pattern = re.compile(r"^.+\.%s\(\)$" % re.escape(attr_name))
    match = _unique_power_call_match(info.get("source_line", ""), pattern)
    if match is None:
        return info
    refined = dict(info)
    refined.update(match)
    return refined


def _build_expression_instance(info: dict, rule: WarningRule, replacement_text=None, required_imports=None, message=None):
    proposal = None
    if replacement_text is not None and not info.get("multiline"):
        proposal = build_fix_proposal(
            filename=info["filename"],
            rel_filename="",
            lineno=info["lineno"],
            warning_type=rule.warning_type,
            message=message or rule.message_match,
            scope="expression",
            original_text=info["expr_text"],
            replacement_text=replacement_text,
            col_start=info["col_start"],
            col_end=info["col_end"],
            required_imports=list(required_imports or []),
        )

    return {
        "filename": info["filename"],
        "lineno": info["lineno"],
        "warning_type": rule.warning_type,
        "auto_fix_line": replacement_text,
        "display_line": info["expr_text"],
        "col_start": info["col_start"],
        "col_end": info["col_end"],
        "highlight": rule.highlight_mode,
        "required_imports": list(required_imports or []),
        "fix_proposal": proposal,
    }


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


def _materialization_required(raw: dict, info: dict):
    explicit = _metadata_bool(raw, "materialization_required")
    if explicit is not None:
        return explicit

    metadata = _warning_metadata(raw)
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


def _text_consumer_required(raw: dict, info: dict):
    explicit = _metadata_bool(raw, "text_consumer")
    if explicit is not None:
        return explicit

    metadata = _warning_metadata(raw)
    consumer_op = metadata.get("consumer_op")
    if consumer_op in ("BINARY_ADD", "INPLACE_ADD"):
        return _looks_like_text_concat(info["source_line"], info["expr_text"])
    return None


def next_method_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    info = _refine_info_to_attr_call(info, "next")
    replacement = None
    expr = info["expr_text"].strip()
    match = re.match(r"(?P<receiver>.+)\.next\(\)$", expr)
    if match and not info["multiline"]:
        replacement = "next(%s)" % match.group("receiver").strip()
    return [_build_expression_instance(info, rule, replacement, message=raw.get("message"))]


def intern_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    info = _refine_info_to_named_call(info, "intern")
    replacement = None
    expr = info["expr_text"].strip()
    match = re.match(r"^intern\((?P<arg>.*)\)$", expr)
    if match and not info["multiline"]:
        replacement = "sys.intern(%s)" % match.group("arg")
    return [_build_expression_instance(
        info,
        rule,
        replacement,
        required_imports=["import sys"],
        message=raw.get("message"),
    )]


def range_materialization_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    expr = info["expr_text"].strip()
    replacement = None
    materialize = _materialization_required(raw, info)

    if expr.startswith("xrange("):
        base = "range(" + expr[len("xrange("):]
        if materialize is True:
            replacement = "list(%s)" % base
        elif materialize is False:
            replacement = base
    elif expr.startswith("range(") and materialize:
        replacement = "list(%s)" % expr

    return [_build_expression_instance(info, rule, replacement, message=raw.get("message"))]


def dict_listlike_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    expr = info["expr_text"].strip()
    replacement = None
    materialize = _materialization_required(raw, info)

    if materialize and re.match(r"^.+\.(keys|values|items)\(\)$", expr):
        replacement = "list(%s)" % expr

    return [_build_expression_instance(info, rule, replacement, message=raw.get("message"))]


def base64_text_builder(raw: dict, resolved_callsite: dict, rule: WarningRule):
    info = _resolved_expression(raw, resolved_callsite)
    expr = info["expr_text"].strip()
    replacement = None
    text_consumer = _text_consumer_required(raw, info)

    if text_consumer and not expr.endswith('.decode("ascii")'):
        replacement = '%s.decode("ascii")' % expr

    return [_build_expression_instance(info, rule, replacement, message=raw.get("message"))]


WARNING_RULES = [
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
        pattern=re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]]*)\.has_key\(\s*(?P<key>.+?)\s*\)"
        ),
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
