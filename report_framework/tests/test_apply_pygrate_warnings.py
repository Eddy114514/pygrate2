import os
import sys
import tempfile
import unittest
from unittest import mock


HERE = os.path.abspath(os.path.dirname(__file__))
REPORT_FRAMEWORK_ROOT = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if REPORT_FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, REPORT_FRAMEWORK_ROOT)

import web_frontend
import framework
from framework import analyze_file_with_output
from web_frontend import app


class PygrateWarningFlowTests(unittest.TestCase):
    def _write_and_analyze(self, source_text, filename="sample.py"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source_text)

        warnings, run_output = analyze_file_with_output(REPO_ROOT, tmp.name, filename)
        current = [warning for warning in warnings if warning.rel_filename == filename]
        payload = web_frontend._serialize_warnings_for_client(current, {filename: source_text})
        return tmp.name, path, current, payload, run_output

    def _preview_apply(self, project_root, filename, source_text, warnings):
        client = app.test_client()
        response = client.post(
            "/preview_apply",
            json={
                "root": project_root,
                "file": filename,
                "sourceText": source_text,
                "warnings": warnings,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        return data

    def _save_and_reanalyze(self, project_root, filename, source_text):
        client = app.test_client()
        response = client.post(
            "/save_and_reanalyze",
            json={
                "engine": REPO_ROOT,
                "root": project_root,
                "file": filename,
                "sourceText": source_text,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        return data

    def test_next_method_warning_closes_loop(self):
        source = "it = iter([1, 2])\nfirst = it.next()\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "NEXT_METHOD_WARNING")
        self.assertEqual(payload[0]["metadata"]["callee_kind"], "iterator.next")
        self.assertIsNotNone(payload[0]["proposal"])

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("first = next(it)", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_next_method_skips_plain_non_iterator_next_method(self):
        source = (
            "class Custom(object):\n"
            "    def next(self):\n"
            "        return 1\n"
            "c = Custom()\n"
            "value = c.next()\n"
        )
        _, _, warnings, _, _ = self._write_and_analyze(source)

        self.assertEqual(warnings, [])

    def test_next_method_warning_still_extracts_call_when_resolver_fails(self):
        source = "it = iter([1, 2])\nfirst = it.next()\n"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "sample.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)

        with mock.patch.object(framework, "_resolve_warning_callsite", return_value=None):
            warnings, _ = framework.analyze_file_with_output(REPO_ROOT, tmp.name, "sample.py")

        current = [warning for warning in warnings if warning.rel_filename == "sample.py"]
        payload = web_frontend._serialize_warnings_for_client(current, {"sample.py": source})

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["original"], "it.next()")
        self.assertEqual(payload[0]["fix"], "next(it)")

        preview = self._preview_apply(tmp.name, "sample.py", source, payload)
        self.assertIn("first = next(it)", preview["sourceText"])
        self.assertNotIn("next(first = it)", preview["sourceText"])

    def test_intern_warning_auto_fix_reuses_existing_import(self):
        source = "import sys\nvalue = intern('abc')\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "INTERN_WARNING")
        self.assertEqual(payload[0]["metadata"]["callee_kind"], "builtin.intern")
        self.assertEqual(payload[0]["importsNeeded"], [])

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertEqual(preview["sourceText"].count("import sys"), 1)
        self.assertIn("value = sys.intern('abc')", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)
        self.assertNotIn("AttributeError", saved["runOutput"])

    def test_intern_warning_still_extracts_call_when_resolver_fails(self):
        source = "value = intern('abc')\n"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "sample.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)

        with mock.patch.object(framework, "_resolve_warning_callsite", return_value=None):
            warnings, _ = framework.analyze_file_with_output(REPO_ROOT, tmp.name, "sample.py")

        current = [warning for warning in warnings if warning.rel_filename == "sample.py"]
        payload = web_frontend._serialize_warnings_for_client(current, {"sample.py": source})

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["original"], "intern('abc')")
        self.assertEqual(payload[0]["fix"], "sys.intern('abc')")

    def test_xrange_iteration_rewrites_to_range(self):
        source = "seen = []\nfor x in xrange(3):\n    seen.append(x)\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "RANGE_MATERIALIZATION_WARNING")
        self.assertEqual(payload[0]["metadata"]["materialization_required"], False)

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("for x in range(3):", preview["sourceText"])
        self.assertNotIn("list(range(3))", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_range_materialization_wraps_list_for_binary_add(self):
        source = "nums = range(3) + [4]\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "RANGE_MATERIALIZATION_WARNING")
        self.assertEqual(payload[0]["metadata"]["consumer_op"], "BINARY_ADD")
        self.assertEqual(payload[0]["metadata"]["materialization_required"], True)

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("nums = list(range(3)) + [4]", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_dict_listlike_warning_only_fixes_list_consumers(self):
        source = "d = {'a': 1, 'b': 2}\nsecond = d.keys()[1]\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "DICT_LISTLIKE_WARNING")
        self.assertEqual(payload[0]["metadata"]["materialization_required"], True)
        self.assertIsNotNone(payload[0]["proposal"])

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("second = list(d.keys())[1]", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_dict_keys_iteration_has_no_listlike_warning(self):
        source = "d = {'a': 1}\nfor key in d.keys():\n    pass\n"
        _, _, warnings, _, _ = self._write_and_analyze(source)

        self.assertEqual(warnings, [])

    def test_base64_text_result_decodes_ascii_for_text_concat(self):
        source = "import base64\nvalue = 'prefix:' + base64.b64encode('x')\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "BASE64_B64ENCODE_WARNING")
        self.assertEqual(payload[0]["metadata"]["text_consumer"], True)
        self.assertIsNotNone(payload[0]["proposal"])

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn('.decode("ascii")', preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertNotIn(
            "BASE64_B64ENCODE_WARNING",
            [warning["type"] for warning in saved["warnings"]],
        )

    def test_base64_without_text_consumer_keeps_warning_without_fix(self):
        source = "import base64\nvalue = base64.b64encode('x')\n"
        _, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].warning_type, "BASE64_B64ENCODE_WARNING")
        self.assertIsNone(payload[0]["metadata"]["text_consumer"])
        self.assertIsNone(payload[0]["proposal"])


if __name__ == "__main__":
    unittest.main()
