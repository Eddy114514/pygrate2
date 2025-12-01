import re

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
        "highlight": "fileio",
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
]
