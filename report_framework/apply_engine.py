import ast
import difflib
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


class ApplyError(ValueError):
    pass


@dataclass
class SourceEdit:
    line: int
    scope: str
    original_text: str
    replacement_text: str
    col_start: Optional[int] = None
    col_end: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "SourceEdit":
        if not isinstance(data, dict):
            raise ApplyError("invalid edit payload")
        return cls(
            line=int(data["line"]),
            scope=str(data["scope"]),
            original_text=str(data["original_text"]),
            replacement_text=str(data["replacement_text"]),
            col_start=_coerce_optional_int(data.get("col_start")),
            col_end=_coerce_optional_int(data.get("col_end")),
        )


@dataclass
class FixProposal:
    filename: str
    rel_filename: str
    warning_type: str
    message: str
    edit: SourceEdit
    required_imports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "FixProposal":
        if not isinstance(data, dict):
            raise ApplyError("invalid proposal payload")
        return cls(
            filename=str(data["filename"]),
            rel_filename=str(data["rel_filename"]),
            warning_type=str(data["warning_type"]),
            message=str(data.get("message", "")),
            edit=SourceEdit.from_dict(data["edit"]),
            required_imports=_coerce_string_list(data.get("required_imports")),
        )


@dataclass
class PreviewApplyResult:
    source_text: str
    diff_text: str
    applied_count: int


def _coerce_optional_int(value) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _coerce_string_list(value) -> List[str]:
    if not value:
        return []
    if not isinstance(value, (list, tuple)):
        return [str(value)]
    return [str(item) for item in value if str(item).strip()]


def build_fix_proposal(
    *,
    filename: str,
    rel_filename: str,
    lineno: int,
    warning_type: str,
    message: str,
    scope: str,
    original_text: str,
    replacement_text: Optional[str],
    col_start: Optional[int],
    col_end: Optional[int],
    required_imports: Optional[Sequence[str]] = None,
) -> Optional[FixProposal]:
    if replacement_text is None or replacement_text == original_text:
        return None
    return FixProposal(
        filename=filename,
        rel_filename=rel_filename,
        warning_type=warning_type,
        message=message,
        edit=SourceEdit(
            line=lineno,
            scope=scope,
            original_text=original_text,
            replacement_text=replacement_text,
            col_start=col_start,
            col_end=col_end,
        ),
        required_imports=list(required_imports or []),
    )


def extract_fix_proposals(warning_payloads: Iterable[Dict[str, object]], rel_filename: str) -> List[FixProposal]:
    proposals: List[FixProposal] = []
    for payload in warning_payloads or []:
        if not isinstance(payload, dict):
            continue
        proposal_payload = payload.get("proposal")
        if proposal_payload is None:
            continue
        proposal = FixProposal.from_dict(proposal_payload)
        if proposal.rel_filename != rel_filename:
            continue
        proposals.append(proposal)
    return proposals


def preview_apply_warnings(
    *,
    source_text: str,
    warning_payloads: Iterable[Dict[str, object]],
    rel_filename: str,
) -> PreviewApplyResult:
    proposals = extract_fix_proposals(warning_payloads, rel_filename)
    if not proposals:
        raise ApplyError("no auto-fixable warnings selected")
    return apply_fix_proposals(source_text=source_text, proposals=proposals, rel_filename=rel_filename)


def apply_fix_proposals(
    *,
    source_text: str,
    proposals: Sequence[FixProposal],
    rel_filename: str,
) -> PreviewApplyResult:
    original_text = source_text
    if not proposals:
        return PreviewApplyResult(source_text=source_text, diff_text="", applied_count=0)

    had_trailing_newline = source_text.endswith("\n")
    lines = source_text.splitlines()
    applied: List[FixProposal] = []
    grouped: Dict[int, List[FixProposal]] = {}

    for proposal in proposals:
        idx = proposal.edit.line - 1
        if idx < 0 or idx >= len(lines):
            raise ApplyError(
                "line %s is out of range for %s" % (proposal.edit.line, proposal.rel_filename)
            )
        grouped.setdefault(idx, []).append(proposal)

    for idx in sorted(grouped):
        current_line = lines[idx]
        line_proposals = grouped[idx]
        line_scope = [proposal for proposal in line_proposals if proposal.edit.scope == "line"]
        if line_scope:
            current_line, line_applied = _apply_line_scope_proposals(current_line, line_scope)
            if line_applied:
                lines[idx] = current_line
                applied.extend(line_applied)
            continue

        current_line, line_applied = _apply_expression_proposals(current_line, line_proposals)
        if line_applied:
            lines[idx] = current_line
            applied.extend(line_applied)

    new_text = _join_lines(lines, had_trailing_newline)
    imports_to_add = []
    for proposal in applied:
        imports_to_add.extend(proposal.required_imports)
    new_text = ensure_imports(new_text, imports_to_add)
    diff_text = build_unified_diff(original_text, new_text, rel_filename)
    return PreviewApplyResult(
        source_text=new_text,
        diff_text=diff_text,
        applied_count=len(applied),
    )


def _apply_line_scope_proposals(
    current_line: str,
    proposals: Sequence[FixProposal],
) -> Tuple[str, List[FixProposal]]:
    first = proposals[0]
    replacements = {proposal.edit.replacement_text for proposal in proposals}
    if len(replacements) > 1:
        raise ApplyError(
            "conflicting line replacements on line %s" % first.edit.line
        )
    replacement = first.edit.replacement_text
    if current_line == replacement:
        return current_line, []
    if current_line != first.edit.original_text:
        raise ApplyError(
            "line %s no longer matches the proposed fix context" % first.edit.line
        )
    return replacement, [first]


def _apply_expression_proposals(
    current_line: str,
    proposals: Sequence[FixProposal],
) -> Tuple[str, List[FixProposal]]:
    applied: List[FixProposal] = []
    occupied_ranges: List[Tuple[int, int]] = []

    def sort_key(proposal: FixProposal):
        start = proposal.edit.col_start if proposal.edit.col_start is not None else -1
        end = proposal.edit.col_end if proposal.edit.col_end is not None else -1
        return (start, end - start, proposal.edit.original_text)

    for proposal in sorted(proposals, key=sort_key, reverse=True):
        span = _resolve_expression_span(current_line, proposal)
        if span is None:
            continue
        start, end = span
        if any(_ranges_overlap((start, end), existing) for existing in occupied_ranges):
            raise ApplyError(
                "overlapping expression fixes on line %s" % proposal.edit.line
            )
        current_line = (
            current_line[:start]
            + proposal.edit.replacement_text
            + current_line[end:]
        )
        occupied_ranges.append((start, end))
        applied.append(proposal)

    return current_line, applied


def _resolve_expression_span(current_line: str, proposal: FixProposal) -> Optional[Tuple[int, int]]:
    original = proposal.edit.original_text
    replacement = proposal.edit.replacement_text
    start = proposal.edit.col_start
    end = proposal.edit.col_end

    if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(current_line):
        segment = current_line[start:end]
        if segment == original:
            return start, end
        if segment == replacement:
            return None

    occurrences = _find_occurrences(current_line, original)
    if len(occurrences) == 1:
        return occurrences[0]
    if len(occurrences) == 0 and replacement and replacement in current_line:
        return None

    raise ApplyError(
        "expression fix on line %s no longer matches the current source" % proposal.edit.line
    )


def _find_occurrences(line: str, needle: str) -> List[Tuple[int, int]]:
    if not needle:
        return []
    out: List[Tuple[int, int]] = []
    start = line.find(needle)
    while start != -1:
        out.append((start, start + len(needle)))
        start = line.find(needle, start + 1)
    return out


def _ranges_overlap(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _join_lines(lines: Sequence[str], had_trailing_newline: bool) -> str:
    text = "\n".join(lines)
    if had_trailing_newline:
        return text + "\n"
    return text


def build_unified_diff(before: str, after: str, rel_filename: str) -> str:
    if before == after:
        return ""
    diff_lines = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        fromfile="a/%s" % rel_filename,
        tofile="b/%s" % rel_filename,
        lineterm="",
    )
    return "\n".join(diff_lines)


def canonicalize_imports_from_source(src: str) -> Set[str]:
    try:
        tree = ast.parse(src)
    except Exception:
        return _canonicalize_imports_from_lines(src.splitlines())
    return _canonicalize_imports_from_tree(tree)


def normalize_required_imports(import_lines: Sequence[str]) -> List[str]:
    canonicals: List[str] = []
    for line in import_lines or []:
        if not line or not isinstance(line, str):
            continue
        try:
            tree = ast.parse(line)
        except Exception:
            continue
        canonicals.extend(sorted(_canonicalize_imports_from_tree(tree)))
    return canonicals


def ensure_imports(source_text: str, import_lines: Sequence[str]) -> str:
    required = normalize_required_imports(import_lines)
    if not required:
        return source_text

    existing = canonicalize_imports_from_source(source_text)
    missing = []
    seen = set()
    for line in required:
        if line in existing or line in seen:
            continue
        missing.append(line)
        seen.add(line)

    if not missing:
        return source_text

    had_trailing_newline = source_text.endswith("\n")
    lines = source_text.splitlines()
    insert_at = find_import_insert_index(lines)
    need_blank = insert_at < len(lines) and lines[insert_at].strip() != ""
    to_insert = missing + ([""] if need_blank else [])
    lines[insert_at:insert_at] = to_insert
    return _join_lines(lines, had_trailing_newline)


def find_import_insert_index(lines: Sequence[str]) -> int:
    idx = 0
    if idx < len(lines) and lines[idx].startswith("#!"):
        idx += 1

    if idx < len(lines) and "coding" in lines[idx]:
        candidate = lines[idx]
        if "coding:" in candidate or "coding=" in candidate:
            idx += 1

    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    if idx < len(lines):
        line = lines[idx].strip()
        if line.startswith('"""') or line.startswith("'''"):
            quote = '"""' if line.startswith('"""') else "'''"
            if line.count(quote) >= 2:
                idx += 1
            else:
                idx += 1
                while idx < len(lines):
                    if quote in lines[idx]:
                        idx += 1
                        break
                    idx += 1

    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    return idx


def _canonicalize_imports_from_tree(tree) -> Set[str]:
    results: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                alias_part = " as %s" % alias.asname if alias.asname else ""
                results.add("import %s%s" % (name, alias_part))
        elif isinstance(node, ast.ImportFrom):
            module = "." * (node.level or 0) + (node.module or "")
            for alias in node.names:
                name = alias.name
                alias_part = " as %s" % alias.asname if alias.asname else ""
                results.add("from %s import %s%s" % (module, name, alias_part))
    return results


def _canonicalize_imports_from_lines(lines: Sequence[str]) -> Set[str]:
    results: Set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        try:
            tree = ast.parse(stripped)
        except Exception:
            continue
        results.update(_canonicalize_imports_from_tree(tree))
    return results
