import os
import re
import sys

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
    {
        "warning_type": "PRINT_WARNING",
        "message_contains": "print must be called as a function",
        "fix_kind": "regex_sub",
        "pattern": re.compile(r"print\s+(.+)"),
        "replacement": r"print(\1)",
        "fix_scope": "line",
        "highlight": "print",
    },
    {
        "warning_type": "HAS_KEY_WARNING",
        "message_contains": "dict.has_key() not supported",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]]*)\.has_key\(\s*(?P<key>.+?)\s*\)"
        ),
        "replacement": r"\g<key> in \g<obj>",
        "fix_scope": "expression",
        "highlight": "haskey",
    },
    {
        "warning_type": "DICT_VIEWKEYS_WARNING",
        "message_contains": "dict.viewkeys() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewkeys\(\)"
        ),
        "replacement": r"\g<obj>.keys()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_VIEWVALUES_WARNING",
        "message_contains": "dict.viewvalues() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewvalues\(\)"
        ),
        "replacement": r"\g<obj>.values()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_VIEWITEMS_WARNING",
        "message_contains": "dict.viewitems() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewitems\(\)"
        ),
        "replacement": r"\g<obj>.items()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_ITERKEYS_WARNING",
        "message_contains": "dict.iterkeys() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.iterkeys\(\)"
        ),
        "replacement": r"\g<obj>.keys()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_ITERVALUES_WARNING",
        "message_contains": "dict.itervalues() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.itervalues\(\)"
        ),
        "replacement": r"\g<obj>.values()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_ITERITEMS_WARNING",
        "message_contains": "dict.iteritems() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.iteritems\(\)"
        ),
        "replacement": r"\g<obj>.items()",
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "BUFFER_WARNING",
        "message_contains": "buffer() not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r"\bbuffer\(\s*(?P<arg>.+?)\s*\)"
        ),
        "replacement": r"memoryview(\g<arg>)",
        "fix_scope": "expression",
        "highlight": "buffer",
    },
    {
        "warning_type": "FILE_CONSTRUCTOR_WARNING",
        "message_contains": "The builtin 'file()'/'open()' function is not supported in 3.x",
        "fix_scope": "line",
        "highlight": "fileio",
    },
    {
        "warning_type": "BYTESIO_TRUNCATE_WARNING",
        "message_contains": "BytesIO.truncate() does not shift the file pointer",
        "fix_kind": "callable",
        "replacement_func": bytesio_truncate_fix,
        "fix_scope": "line",
        "highlight": "bytesio",
    },
    {
        "warning_type": "TOKENIZE_WARNING",
        "message_contains": "tokenize() changed in 3.x",
        "fix_scope": "line",
        "highlight": "tokenize",
    },
    {
        "warning_type": "BASE64_B64ENCODE_WARNING",
        "message_contains": "base64.b64encode returns str in Python 2",
        "fix_scope": "line",
        "highlight": "base64",
    },
    {
        "warning_type": "BASE64_B32ENCODE_WARNING",
        "message_contains": "base64.b32encode returns str in Python 2",
        "fix_scope": "line",
        "highlight": "base64",
    },
    {
        "warning_type": "BASE64_B16ENCODE_WARNING",
        "message_contains": "base64.b16encode returns str in Python 2",
        "fix_scope": "line",
        "highlight": "base64",
    },
    {
        "warning_type": "CMP_ARG_WARNING",
        "message_contains": "the cmp argument is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(r"\bcmp\s*=\s*(?P<cmp>[^,\)\]]+)"),
        "replacement": r"key=cmp_to_key(\g<cmp>)",
        "fix_scope": "line",
        "highlight": "cmp",
        "imports": ["from functools import cmp_to_key"],
    },
]
