from dataclasses import dataclass, field
from typing import Callable, Optional, Pattern, Sequence


ReplacementFunc = Callable[[str, dict], str]


@dataclass(frozen=True)
class WarningRule:
    name: str
    warning_type: str
    message_match: str
    fix_scope: str
    highlight_mode: str
    fix_kind: Optional[str] = None
    pattern: Optional[Pattern[str]] = None
    replacement: Optional[str] = None
    replacement_func: Optional[ReplacementFunc] = None
    imports: Sequence[str] = field(default_factory=tuple)
    regex_grade: str = "A"
    notes: str = ""


def method_rename_rule(
    *,
    name: str,
    warning_type: str,
    message_match: str,
    method_name: str,
    replacement_method: str,
    regex_grade: str = "A",
    notes: str = "",
) -> WarningRule:
    import re

    return WarningRule(
        name=name,
        warning_type=warning_type,
        message_match=message_match,
        fix_kind="regex_sub",
        pattern=re.compile(
            r"(?P<obj>[A-Za-z_][\w\.\[\]\(\)]*)\.%s\(\)" % re.escape(method_name)
        ),
        replacement=r"\g<obj>.%s()" % replacement_method,
        fix_scope="expression",
        highlight_mode="dict",
        regex_grade=regex_grade,
        notes=notes,
    )
