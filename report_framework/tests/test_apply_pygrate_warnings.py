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

    def test_exec_statement_rewrites_simple_exec(self):
        source = 'exec "x = 1"\n'
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["EXEC_STATEMENT_WARNING"])
        self.assertEqual(payload[0]["metadata"]["warning_type"], "EXEC_STATEMENT_WARNING")
        self.assertEqual(payload[0]["fix"], 'exec("x = 1")')

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn('exec("x = 1")', preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_exec_statement_rewrites_exec_with_globals(self):
        source = "code = 'x = 1'\ng = {}\nexec code in g\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["EXEC_STATEMENT_WARNING"])
        self.assertEqual(payload[0]["fix"], "exec(code, g)")

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("exec(code, g)", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_exec_statement_rewrites_exec_with_globals_and_locals(self):
        source = "code = 'x = 1'\ng = {}\nl = {}\nexec code in g, l\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["EXEC_STATEMENT_WARNING"])
        self.assertEqual(payload[0]["fix"], "exec(code, g, l)")

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("exec(code, g, l)", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_exec_scope_warning_exposes_function_scope_metadata(self):
        source = (
            "def run(code, g, l):\n"
            "    exec code in g, l\n"
            "    return l\n"
        )
        _, _, warnings, payload, _ = self._write_and_analyze(source)

        warning_types = [warning.warning_type for warning in warnings]
        self.assertIn("EXEC_STATEMENT_WARNING", warning_types)
        self.assertIn("EXEC_SCOPE_WARNING", warning_types)

        scope_payload = next(item for item in payload if item["type"] == "EXEC_SCOPE_WARNING")
        self.assertIsNone(scope_payload["proposal"])
        self.assertEqual(scope_payload["metadata"]["scope_kind"], "function")
        self.assertTrue(scope_payload["metadata"]["has_explicit_globals"])
        self.assertTrue(scope_payload["metadata"]["has_explicit_locals"])

    def test_exec_preview_apply_and_save_reanalyze_close_loop(self):
        source = "code = 'x = 1'\nexec code\n"
        tmpdir, path, _, payload, _ = self._write_and_analyze(source)

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("exec(code)", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)
        self.assertEqual(saved["warnings"], [])
        with open(path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), preview["sourceText"])

    def test_old_style_class_rewrites_simple_class_header(self):
        source = "class Foo:\n    pass\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["OLD_STYLE_CLASS_WARNING"])
        self.assertEqual(payload[0]["metadata"]["class_name"], "Foo")
        self.assertEqual(payload[0]["metadata"]["bases"], [])
        self.assertTrue(payload[0]["metadata"]["is_classic_class"])
        self.assertEqual(payload[0]["fix"], "class Foo(object):")

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("class Foo(object):", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_new_style_class_object_is_not_reported(self):
        source = "class Foo(object):\n    pass\n"
        _, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(warnings, [])
        self.assertEqual(payload, [])

    def test_old_style_class_payload_carries_metadata(self):
        source = "class Foo:\n    pass\n"
        _, _, _, payload, _ = self._write_and_analyze(source)

        self.assertEqual(payload[0]["type"], "OLD_STYLE_CLASS_WARNING")
        self.assertEqual(payload[0]["metadata"]["class_name"], "Foo")
        self.assertEqual(payload[0]["metadata"]["bases"], [])
        self.assertTrue(payload[0]["metadata"]["is_classic_class"])

    def test_classic_multiple_inheritance_emits_mro_risk_warning(self):
        source = (
            "class A:\n"
            "    pass\n"
            "class B:\n"
            "    pass\n"
            "class C(A, B):\n"
            "    pass\n"
        )
        _, _, warnings, payload, _ = self._write_and_analyze(source)

        warning_types = [warning.warning_type for warning in warnings]
        self.assertIn("OLD_STYLE_CLASS_WARNING", warning_types)
        self.assertIn("MRO_RISK_WARNING", warning_types)

        risk_payload = next(item for item in payload if item["type"] == "MRO_RISK_WARNING")
        self.assertIsNone(risk_payload["proposal"])
        self.assertEqual(risk_payload["metadata"]["class_name"], "C")
        self.assertEqual(risk_payload["metadata"]["bases"], ["A", "B"])
        self.assertEqual(risk_payload["metadata"]["risk_kind"], "classic_multi_inheritance")

    def test_stringio_from_import_rewrites_to_io_stringio(self):
        source = "from StringIO import StringIO\nbuf = StringIO()\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["STRINGIO_WARNING"])
        self.assertEqual(payload[0]["metadata"]["module_name"], "StringIO")
        self.assertEqual(payload[0]["metadata"]["usage_kind"], "text")
        self.assertEqual(payload[0]["fix"], "from io import StringIO")

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("from io import StringIO", preview["sourceText"])
        self.assertIn("buf = StringIO()", preview["sourceText"])

        saved = self._save_and_reanalyze(tmpdir, "sample.py", preview["sourceText"])
        self.assertEqual(saved["warningCount"], 0)

    def test_stringio_module_call_rewrites_import_and_constructor(self):
        source = "import StringIO\nbuf = StringIO.StringIO()\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["STRINGIO_WARNING", "STRINGIO_WARNING"])

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("import io", preview["sourceText"])
        self.assertIn("buf = io.StringIO()", preview["sourceText"])

    def test_cstringio_from_import_rewrites_to_bytesio(self):
        source = "from cStringIO import StringIO\nbuf = StringIO('abc')\n"
        tmpdir, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual(
            [warning.warning_type for warning in warnings],
            ["CSTRINGIO_WARNING", "CSTRINGIO_WARNING"],
        )
        self.assertTrue(all(item["metadata"]["usage_kind"] == "bytes" for item in payload))

        preview = self._preview_apply(tmpdir, "sample.py", source, payload)
        self.assertIn("from io import BytesIO", preview["sourceText"])
        self.assertIn("buf = BytesIO('abc')", preview["sourceText"])

    def test_stringio_alias_usage_keeps_warning_without_fix(self):
        source = "import StringIO as sio\nbuf = sio.StringIO()\n"
        _, _, warnings, payload, _ = self._write_and_analyze(source)

        self.assertEqual([warning.warning_type for warning in warnings], ["STRINGIO_WARNING"])
        self.assertEqual(payload[0]["metadata"]["module_name"], "StringIO")
        self.assertIsNone(payload[0]["proposal"])

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
