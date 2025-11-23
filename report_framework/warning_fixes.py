#report_framework/warning_fixes.py

import re

WARNING_RULES = [
    {
        "warning_type": "PRINT_WARNING",
        "message_contains": "print must be called as a function",
        "fix_kind": "regex_sub",
        "pattern": re.compile(r'^(?P<indent>\s*)print\s+(?P<body>.*)$'),
        "replacement": r'\g<indent>print(\g<body>)',
        "fix_scope": "line",
    },

    {
        "warning_type": "HAS_KEY_WARNING",
        "message_contains": "dict.has_key() not supported",
        "fix_kind": "regex_sub",
        "pattern": re.compile(
            r'(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.has_key\(\s*(?P<key>.+?)\s*\)'
        ),
        "replacement": r'\g<key> in \g<obj>',
        "fix_scope": "expression",
    },

]

