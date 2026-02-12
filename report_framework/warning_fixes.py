import re

def _should_collect_text_evidence(message: str) -> bool:
    if not message:
        return False
    for rule in WARNING_RULES:
        if rule.get("needs_text_evidence") and rule.get("message_contains") in message:
            return True
    return False

def file_warning_fix(line: str, raw: dict):
    if not isinstance(raw, dict):
        return line

    text_evidence = bool(raw.get("text_evidence"))
    want_binary = not text_evidence
    observed = raw.get("observed") or {}
    observed_mode = observed.get("mode") if isinstance(observed, dict) else None

    def ensure_b(mode_val: str) -> str:
        if "b" in mode_val:
            return mode_val
        if not mode_val:
            return "rb"
        if mode_val[0] in ("r", "w", "a"):
            return mode_val[0] + "b" + mode_val[1:]
        return mode_val + "b"

    def mode_literal_from_observed() -> str:
        if not observed_mode:
            return ""
        mode_val = str(observed_mode)
        if want_binary:
            mode_val = ensure_b(mode_val)
        return f"'{mode_val}'"

    def replace_or_insert_mode(src: str) -> str:
        mode_kw = re.compile(r"(mode\s*=\s*)([rubfRUBF]*['\"][^'\"]*['\"])")
        mode_pos = re.compile(r"(\b(?:file|open)\s*\([^,\)]*\s*,\s*)([rubfRUBF]*['\"][^'\"]*['\"])")
        if observed_mode:
            mode_literal = mode_literal_from_observed()
        else:
            mode_literal = None

        def add_b_to_literal(lit: str) -> str:
            m = re.match(r"^(?P<prefix>[rubfRUBF]*)(?P<quote>['\"])(?P<val>.*)(?P=quote)$", lit.strip())
            if not m:
                return lit
            val = m.group("val")
            if want_binary:
                val = ensure_b(val)
            return f"{m.group('prefix')}{m.group('quote')}{val}{m.group('quote')}"

        if mode_literal:
            if mode_kw.search(src):
                return mode_kw.sub(r"\1" + mode_literal, src, count=1)
            if mode_pos.search(src):
                return mode_pos.sub(r"\1" + mode_literal, src, count=1)
        else:
            if want_binary:
                if mode_kw.search(src):
                    return mode_kw.sub(lambda m: m.group(1) + add_b_to_literal(m.group(2)), src, count=1)
                if mode_pos.search(src):
                    return mode_pos.sub(lambda m: m.group(1) + add_b_to_literal(m.group(2)), src, count=1)
                insert_pos = re.compile(r"(\b(?:file|open)\s*\([^,\)]*\s*)(\))")
                return insert_pos.sub(r"\1, 'rb'\2", src, count=1)
        return src

    updated = replace_or_insert_mode(line)
    updated = re.sub(r"\bfile\s*\(", "io.open(", updated)
    updated = re.sub(r"\bopen\s*\(", "io.open(", updated)
    return updated


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
            r'(?P<obj>[A-Za-z_][\w\.\[\]]*)\.has_key\(\s*(?P<key>.+?)\s*\)'
        ),
        "replacement": r'\g<key> in \g<obj>',
        "fix_scope": "expression",
        "highlight": "haskey",
    },

    {
        "warning_type": "DICT_VIEWKEYS_WARNING",
        "message_contains": "dict.viewkeys() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewkeys\(\)'
        ),
        "replacement": r'\g<obj>.keys()',
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_VIEWVALUES_WARNING",
        "message_contains": "dict.viewvalues() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewvalues\(\)'
        ),
        "replacement": r'\g<obj>.values()',
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_VIEWITEMS_WARNING",
        "message_contains": "dict.viewitems() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.viewitems\(\)'
        ),
        "replacement": r'\g<obj>.items()',
        "fix_scope": "expression",
        "highlight": "dict",
    },

    {
        "warning_type": "DICT_ITERKEYS_WARNING",
        "message_contains": "dict.iterkeys() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.iterkeys\(\)'
        ),
        "replacement": r'\g<obj>.keys()',
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_ITERVALUES_WARNING",
        "message_contains": "dict.itervalues() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.itervalues\(\)'
        ),
        "replacement": r'\g<obj>.values()',
        "fix_scope": "expression",
        "highlight": "dict",
    },
    {
        "warning_type": "DICT_ITERITEMS_WARNING",
        "message_contains": "dict.iteritems() is not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.iteritems\(\)'
        ),
        "replacement": r'\g<obj>.items()',
        "fix_scope": "expression",
        "highlight": "dict",
    },

    {
        "warning_type": "BUFFER_WARNING",
        "message_contains": "buffer() not supported in 3.x",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'\bbuffer\(\s*(?P<arg>.+?)\s*\)'
        ),
        "replacement": r'memoryview(\g<arg>)',
        "fix_scope": "expression",
        "highlight": "buffer",
    },


    {
        "warning_type": "FILE_CONSTRUCTOR_WARNING",
        "message_contains": "The builtin 'file()'/'open()' function is not supported in 3.x",
        "fix_scope": "line",
        "fix_kind": "callable",
        "replacement_func": file_warning_fix,
        "highlight": "fileio",
        "imports": ["import io"],
        "needs_text_evidence": True,
    },

    {
        "warning_type": "BYTESIO_TRUNCATE_WARNING",
        "message_contains": "BytesIO.truncate() does not shift the file pointer",
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
        "pattern": re.compile(r'\bcmp\s*=\s*(?P<cmp>[^,\)\]]+)'),
        "replacement": r'key=cmp_to_key(\g<cmp>)',
        "fix_scope": "line",
        "highlight": "cmp",
        "imports": ["from functools import cmp_to_key"],
    },
]


def file_warning_fix(line: str, raw: dict):
    """
    Attempt to auto-fix file/open warnings using observed mode info from Py3k warning.
    - Replace file(...)/open(...) with io.open(...)
    - If observed mode is text (no 'b') and line lacks encoding kwarg, add encoding='utf-8'
    """
    observed = raw.get("observed") if isinstance(raw, dict) else None
    mode = None
    if isinstance(observed, dict):
        mode = observed.get("mode")

    pattern_file = re.compile(r"\bfile\s*\(\s*(?P<args>[^)]*)\)")
    pattern_open = re.compile(r"\bopen\s*\(\s*(?P<args>[^)]*)\)")

    def build_new(match):
        args = match.group("args")
        needs_encoding = (
            mode is not None
            and "b" not in str(mode)
            and "encoding=" not in args
        )
        if needs_encoding:
            return f"io.open({args}, encoding='utf-8')"
        return f"io.open({args})"

    m = pattern_file.search(line)
    if m:
        return build_new(m)

    m = pattern_open.search(line)
    if m:
        return build_new(m)

    return line
