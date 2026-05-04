import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HERE = os.path.abspath(os.path.dirname(__file__))
REPORT_FRAMEWORK_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPORT_FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, REPORT_FRAMEWORK_ROOT)

import framework
import resolve_warning_calls as resolver
import web_frontend


class CmpMethodWarningTests(unittest.TestCase):
    def _make_tempdir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return tmp.name

    def _write_sample(self, source_text):
        tmpdir = self._make_tempdir()
        path = os.path.join(tmpdir, "sample.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source_text)
        return tmpdir, path

    def _run_runtime(self, path):
        proc = subprocess.run(
            [os.path.join(REPO_ROOT, "python"), "-3", "-B", path],
            capture_output=True,
            text=True,
        )
        return proc.stdout, proc.stderr

    def _analyze(self, tmpdir):
        return framework.analyze_file_with_output(REPO_ROOT, tmpdir, "sample.py")

    def _cmp_warnings(self, warnings):
        return [w for w in warnings if w.warning_type == "CMP_METHOD_WARNING"]

    def _wrapper_source_at_line(self, call_line):
        lines = [
            "class C(object):",
            "    def __cmp__(self, other): return 1-1",
            "def top(a,b): return cmp(a,b)",
            "x=C(); y=C()",
        ]
        while len(lines) < call_line - 1:
            lines.append("# filler %d" % (len(lines) + 1))
        lines.append("print(top(x,y))")
        return "\n".join(lines) + "\n"

    def _multiline_wrapper_source(self, call_line):
        lines = [
            "class C(object):",
            "    def __cmp__(self, other):",
            "        return 1-1",
            "",
            "def top(a,b):",
            "    return cmp(a,b)",
            "",
            "x=C()",
            "y=C()",
        ]
        while len(lines) < call_line - 1:
            lines.append("# filler %d" % (len(lines) + 1))
        lines.append("print(top(x,y))")
        return "\n".join(lines) + "\n"

    def test_cmp_method_resolution_stable_across_call_lines(self):
        for call_line in (5, 14, 25):
            with self.subTest(call_line=call_line):
                tmpdir, _ = self._write_sample(self._wrapper_source_at_line(call_line))
                warnings, _ = self._analyze(tmpdir)
                cmp_warnings = self._cmp_warnings(warnings)

                self.assertEqual(len(cmp_warnings), 1)
                warning = cmp_warnings[0]
                self.assertEqual(warning.lineno, call_line)
                self.assertEqual(warning.line, "top(x,y)")
                self.assertEqual((warning.col_start, warning.col_end), (6, 14))

    def test_cmp_method_prefers_message_call_line_over_header_line(self):
        tmpdir, path = self._write_sample(self._wrapper_source_at_line(14))
        _, stderr = self._run_runtime(path)
        header = next(
            line for line in stderr.splitlines()
            if "cmp method is not supported in 3.x" in line
        )

        parsed = resolver.parse_warning_callsite(header)
        self.assertEqual(parsed["header_lineno"], 3)
        self.assertEqual(parsed["call_lineno"], 14)

        resolved = resolver.resolve_warning_callsite(
            header,
            py2_bin=os.path.join(REPO_ROOT, "python"),
            source_path=path,
        )
        self.assertEqual(resolved["lineno"], 14)
        self.assertEqual(resolved["resolved_call"]["text"], "top(x,y)")

        warnings, _ = self._analyze(tmpdir)
        cmp_warning = self._cmp_warnings(warnings)[0]
        self.assertEqual(cmp_warning.lineno, 14)
        self.assertEqual(cmp_warning.line, "top(x,y)")

    def test_cmp_method_warning_survives_resolver_failure(self):
        tmpdir, _ = self._write_sample(self._multiline_wrapper_source(14))

        with mock.patch.object(framework, "_resolve_warning_callsite", return_value=None):
            warnings, _ = self._analyze(tmpdir)

        cmp_warnings = self._cmp_warnings(warnings)
        self.assertEqual(len(cmp_warnings), 1)
        warning = cmp_warnings[0]
        self.assertEqual(warning.lineno, 6)
        self.assertEqual(warning.line, "    return cmp(a,b)")
        self.assertIsNone(warning.auto_fix_line)

    def test_cmp_method_multiple_calls_same_line_keep_distinct_spans(self):
        source = "\n".join(
            [
                "class C(object):",
                "    def __cmp__(self, other): return 1-1",
                "x=C()",
                "y=C()",
                "result = (cmp(x,y), cmp(x,y))",
            ]
        ) + "\n"
        tmpdir, _ = self._write_sample(source)
        warnings, _ = self._analyze(tmpdir)
        cmp_warnings = self._cmp_warnings(warnings)

        self.assertEqual(len(cmp_warnings), 2)
        spans = sorted((w.col_start, w.col_end) for w in cmp_warnings)
        line_text = "result = (cmp(x,y), cmp(x,y))"
        first = line_text.index("cmp(x,y)")
        second = line_text.index("cmp(x,y)", first + 1)
        self.assertEqual(
            spans,
            [
                (first, first + len("cmp(x,y)")),
                (second, second + len("cmp(x,y)")),
            ],
        )

    def test_cmp_method_cross_line_callsite_resolves_to_call_start(self):
        source = "\n".join(
            [
                "class C(object):",
                "    def __cmp__(self, other): return 1-1",
                "",
                "def top(a,b): return cmp(a,b)",
                "",
                "x=C()",
                "y=C()",
                "result = top(",
                "    x,",
                "    y",
                ")",
            ]
        ) + "\n"
        tmpdir, _ = self._write_sample(source)
        warnings, _ = self._analyze(tmpdir)
        cmp_warnings = self._cmp_warnings(warnings)

        self.assertEqual(len(cmp_warnings), 1)
        warning = cmp_warnings[0]
        self.assertEqual(warning.lineno, 8)
        self.assertEqual(warning.line, "result = top(")
        self.assertGreaterEqual(warning.col_end, warning.col_start)

    def test_cmp_method_payload_builds_warning_id_without_proposal(self):
        tmpdir, _ = self._write_sample(
            "\n".join(
                [
                    "xyz = cmp",
                    "f = cmp",
                    "def g(x,y):",
                    "  return 1",
                    "a = [xyz(1,2), f(3,4), 5, g(1,2)]",
                    "a = [xyz(1,2), f(3,4), 5, g(1,2)]",
                ]
            ) + "\n"
        )

        warnings, _ = self._analyze(tmpdir)
        cmp_warnings = self._cmp_warnings(warnings)
        self.assertGreaterEqual(len(cmp_warnings), 1)

        payload = web_frontend._warning_to_payload(cmp_warnings[0])
        self.assertIn("warningId", payload)
        self.assertTrue(payload["warningId"].startswith("warn-"))
        self.assertIsNone(payload["proposal"])


if __name__ == "__main__":
    unittest.main()
