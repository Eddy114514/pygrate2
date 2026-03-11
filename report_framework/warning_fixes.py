import os
import re
import sys

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


WARNING_RULES = [
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
        fix_scope="line",
        highlight_mode="base64",
        regex_grade="B",
        notes="No auto-fix yet.",
    ),
    WarningRule(
        name="base64_b32encode",
        warning_type="BASE64_B32ENCODE_WARNING",
        message_match="base64.b32encode returns str in Python 2",
        fix_scope="line",
        highlight_mode="base64",
        regex_grade="B",
        notes="No auto-fix yet.",
    ),
    WarningRule(
        name="base64_b16encode",
        warning_type="BASE64_B16ENCODE_WARNING",
        message_match="base64.b16encode returns str in Python 2",
        fix_scope="line",
        highlight_mode="base64",
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
