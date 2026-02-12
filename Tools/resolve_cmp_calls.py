#!/usr/bin/env python3
"""
Resolve cmp warnings with bytecode offsets to source callees.

Implementation strategy (library-first):
- Use Python2's stdlib `dis` (via subprocess) to get CALL_* offsets on a line.
- Use `parso` (Python 2.7 grammar) to extract callee expressions in eval order.
"""

import argparse
import json
import os
import re
import subprocess
import sys


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_DIR = os.path.join(ROOT_DIR, ".vendor")
if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

try:
    import parso
except Exception as e:
    raise SystemExit(
        "parso is required. Install with: "
        "python3 -m pip install --target .vendor parso==0.7.1\n"
        "import error: %s" % (e,)
    )


HEADER_RE = re.compile(
    r"^(?P<filename>.+?):(?P<lineno>\d+):\s+(?P<category>[^:]+):\s+(?P<message>.*)$"
)
CALLSITE_BASE_RE = re.compile(
    r"called from\s+.+?:(?P<call_lineno>\d+)\s+in\s+(?P<func>[^,\)]+)"
)
BYTECODE_RE = re.compile(
    r"bytecode(?:=(?P<opname>[A-Z_]+))?@(?P<offset>\d+)"
)

PY2_OFFSET_SCRIPT = r"""
import dis, opcode, sys, json, types

path, func_name, line_s = sys.argv[1], sys.argv[2], sys.argv[3]
line = int(line_s)
src = open(path, 'rb').read()
root = compile(src, path, 'exec')

def walk_code(co):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            for ch in walk_code(c):
                yield ch

def span(co):
    starts = list(dis.findlinestarts(co))
    if not starts:
        return co.co_firstlineno, co.co_firstlineno
    lines = [ln for _, ln in starts]
    return min(lines), max(lines)

target = None
if func_name == '<module>':
    target = root
else:
    cands = [co for co in walk_code(root) if co.co_name == func_name]
    best = None
    best_span = None
    for co in cands:
        lo, hi = span(co)
        if lo <= line <= hi:
            s = hi - lo
            if best is None or s < best_span:
                best = co
                best_span = s
    target = best or (cands[0] if cands else None)

if target is None:
    print("[]")
    sys.exit(0)

call_ops = set()
for n in ('CALL_FUNCTION', 'CALL_FUNCTION_VAR', 'CALL_FUNCTION_KW', 'CALL_FUNCTION_VAR_KW'):
    op = opcode.opmap.get(n)
    if op is not None:
        call_ops.add(op)

line_starts = dict(dis.findlinestarts(target))
cur_line = target.co_firstlineno
code = target.co_code
i = 0
offsets = []
while i < len(code):
    off = i
    if off in line_starts:
        cur_line = line_starts[off]
    op = ord(code[i])
    i += 1
    if op >= opcode.HAVE_ARGUMENT:
        i += 2
    if op in call_ops and cur_line == line:
        offsets.append(off)

print(json.dumps(offsets))
"""

GRAMMAR27 = parso.load_grammar(version="2.7")


def _children(node):
    return getattr(node, "children", ())


def _is_leaf(node):
    return not hasattr(node, "children")


def _value(node):
    return getattr(node, "value", None)


def _eval_node(node, calls):
    if node is None:
        return "<expr>"

    ntype = getattr(node, "type", None)
    kids = _children(node)

    if _is_leaf(node):
        if ntype == "name":
            return _value(node)
        return "<expr>"

    if ntype == "power" and kids:
        base = _eval_node(kids[0], calls)
        for trailer in kids[1:]:
            if getattr(trailer, "type", None) != "trailer":
                _eval_node(trailer, calls)
                continue
            t_children = _children(trailer)
            if not t_children:
                continue
            first = _value(t_children[0])
            if first == ".":
                attr = _value(t_children[1]) if len(t_children) > 1 else "<?>"
                base = "%s.%s" % (base, attr)
            elif first == "[":
                if len(t_children) > 2:
                    _eval_node(t_children[1], calls)
                base = "%s[...]" % (base,)
            elif first == "(":
                if len(t_children) > 2:
                    _eval_node(t_children[1], calls)  # arglist
                calls.append(base)
                base = "<ret>"
        return base

    if ntype == "expr_stmt":
        # Assignment bytecode evaluates RHS before STORE_*.
        if any(_value(ch) == "=" for ch in kids):
            _eval_node(kids[-1], calls)
            for ch in kids[:-1]:
                _eval_node(ch, calls)
        else:
            for ch in kids:
                _eval_node(ch, calls)
        return "<expr>"

    for ch in kids:
        _eval_node(ch, calls)
    return "<expr>"


def line_callees_with_parso(line_text):
    module = GRAMMAR27.parse((line_text or "") + "\n")
    calls = []
    for ch in _children(module):
        _eval_node(ch, calls)
    return calls


def parse_warning_header(line):
    m = HEADER_RE.match(line.strip())
    if not m:
        return None
    message = m.group("message")
    callsite = CALLSITE_BASE_RE.search(message)
    if not callsite:
        return None
    bc = BYTECODE_RE.search(message)
    if not bc:
        return None
    return {
        "filename": m.group("filename"),
        "lineno": int(m.group("lineno")),
        "func": callsite.group("func"),
        "offset": int(bc.group("offset")),
        "opname": bc.group("opname"),
        "raw": line.rstrip("\n"),
    }


def _read_source(path):
    with open(path, "rb") as f:
        b = f.read()
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("latin-1")


def _pick_py2(py2_bin):
    if py2_bin:
        return py2_bin
    env_bin = os.environ.get("PYGRATE_PY2")
    if env_bin:
        return env_bin
    local_bin = os.path.join(ROOT_DIR, "python")
    if os.path.exists(local_bin):
        return local_bin
    return "python2"


def call_offsets_with_py2(source_path, func_name, lineno, py2_bin):
    interp = _pick_py2(py2_bin)
    cmd = [interp, "-c", PY2_OFFSET_SCRIPT, source_path, func_name, str(lineno)]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    if isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    out = out.strip() or "[]"
    return json.loads(out)


def resolve_one(source_path, func_name, call_lineno, offset, py2_bin=None):
    src = _read_source(source_path)
    lines = src.splitlines()
    line_text = lines[call_lineno - 1] if 1 <= call_lineno <= len(lines) else ""
    line_callees = line_callees_with_parso(line_text)

    offsets = call_offsets_with_py2(source_path, func_name, call_lineno, py2_bin)
    if offset not in offsets:
        return {
            "source": source_path,
            "func": func_name,
            "lineno": call_lineno,
            "offset": offset,
            "callee": None,
            "known_offsets": offsets,
            "known_callees": line_callees,
        }

    idx = offsets.index(offset)
    callee = line_callees[idx] if idx < len(line_callees) else None
    return {
        "source": source_path,
        "func": func_name,
        "lineno": call_lineno,
        "offset": offset,
        "callee": callee,
        "known_offsets": offsets,
        "known_callees": line_callees,
        "call_index": idx,
    }


def _warnings_from_args(args):
    rows = [w.rstrip("\n") for w in args.warning]
    if args.warnings_file:
        with open(args.warnings_file, "r") as f:
            rows.extend([ln.rstrip("\n") for ln in f if ln.strip()])
    if args.stdin:
        rows.extend([ln.rstrip("\n") for ln in sys.stdin if ln.strip()])
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Resolve cmp warning bytecode offsets to concrete call targets."
    )
    p.add_argument("--warning", action="append", default=[],
                   help="One full warning header line.")
    p.add_argument("--warnings-file", help="File containing warning headers.")
    p.add_argument("--stdin", action="store_true", help="Read warning lines from stdin.")
    p.add_argument("--source", help="Source file (manual mode).")
    p.add_argument("--func", help="Function name, e.g. <module> (manual mode).")
    p.add_argument("--line", type=int, help="Line number in that function (manual mode).")
    p.add_argument("--offset", type=int, help="Bytecode offset (manual mode).")
    p.add_argument("--py2-bin", help="Python2 interpreter path used for bytecode offsets.")
    args = p.parse_args(argv)

    manual = args.source and args.func and args.line is not None and args.offset is not None
    warning_lines = _warnings_from_args(args)
    if not warning_lines and not manual:
        p.error("provide --warning/--warnings-file/--stdin, or manual mode args.")

    code = 0

    if manual:
        try:
            out = resolve_one(args.source, args.func, args.line, args.offset, args.py2_bin)
            if out["callee"] is None:
                print("%s:%d in %s bytecode@%d -> <unresolved>; offsets=%s callees=%s" % (
                    out["source"], out["lineno"], out["func"], out["offset"],
                    out["known_offsets"], out["known_callees"]
                ))
                code = 2
            else:
                print("%s:%d in %s CALL@%d -> %s" % (
                    out["source"], out["lineno"], out["func"], out["offset"], out["callee"]
                ))
        except Exception as e:
            print("error: %s" % (e,), file=sys.stderr)
            code = 2

    for line in warning_lines:
        parsed = parse_warning_header(line)
        if parsed is None:
            print("skip (unrecognized warning format): %s" % line)
            continue
        src = parsed["filename"]
        if src.startswith("./"):
            src = src[2:]
        if not os.path.exists(src):
            print("skip (source not found): %s" % parsed["filename"])
            continue
        try:
            out = resolve_one(src, parsed["func"], parsed["lineno"], parsed["offset"], args.py2_bin)
            if out["callee"] is None:
                print("%s -> unresolved at @%d; offsets=%s callees=%s" % (
                    parsed["raw"], parsed["offset"], out["known_offsets"], out["known_callees"]
                ))
                code = max(code, 2)
            else:
                print("%s -> callee=%s" % (parsed["raw"], out["callee"]))
        except Exception as e:
            print("%s -> error: %s" % (parsed["raw"], e))
            code = max(code, 2)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
