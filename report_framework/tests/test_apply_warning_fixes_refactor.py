import os
import sys
import tempfile
import unittest


HERE = os.path.abspath(os.path.dirname(__file__))
REPORT_FRAMEWORK_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if REPORT_FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, REPORT_FRAMEWORK_ROOT)

import warning_fixes as wf
from models.rule_models import WarningRule


class WarningFixRefactorTests(unittest.TestCase):
    def _rule(self, name):
        return next(rule for rule in wf.WARNING_RULES if rule.name == name)

    def _raw(self, line, metadata=None, lineno=1, filename="sample.py", message="warning"):
        return {
            "filename": filename,
            "lineno": lineno,
            "line": line,
            "message": message,
            "metadata": metadata or {},
        }

    def _resolved_callsite(self, source_line, expr_text, col_start, col_end, lineno=1, filename="sample.py"):
        return {
            "source": filename,
            "lineno": lineno,
            "line_text": source_line,
            "callee": expr_text,
            "resolved_call": {
                "text": expr_text,
                "line_start": lineno,
                "line_end": lineno,
                "col_start": col_start,
                "col_end": col_end,
            },
        }

    def test_instance_payload_shape_stays_stable_for_line_and_expression(self):
        rule = WarningRule(
            name="dummy",
            warning_type="DUMMY_WARNING",
            message_match="dummy warning",
            fix_scope="expression",
            highlight_mode="dummy",
        )

        line_instance = wf._build_line_instance(
            filename="sample.py",
            lineno=3,
            source_line="import StringIO",
            replacement_text="import io",
            rule=rule,
            required_imports=["import sys"],
            message="dummy",
        )
        self.assertEqual(
            set(line_instance.keys()),
            {
                "filename",
                "lineno",
                "warning_type",
                "auto_fix_line",
                "display_line",
                "col_start",
                "col_end",
                "highlight",
                "required_imports",
                "fix_proposal",
            },
        )
        self.assertEqual(line_instance["fix_proposal"].edit.scope, "line")
        self.assertEqual(line_instance["fix_proposal"].edit.original_text, "import StringIO")
        self.assertEqual(line_instance["fix_proposal"].edit.replacement_text, "import io")
        self.assertEqual(line_instance["fix_proposal"].required_imports, ["import sys"])

        info = {
            "filename": "sample.py",
            "lineno": 5,
            "expr_text": "intern('abc')",
            "source_line": "value = intern('abc')",
            "col_start": 8,
            "col_end": 21,
            "multiline": False,
        }
        expr_instance = wf._build_expression_instance(
            info,
            rule,
            "sys.intern('abc')",
            required_imports=["import sys"],
            message="dummy",
        )
        self.assertEqual(set(expr_instance.keys()), set(line_instance.keys()))
        self.assertEqual(expr_instance["fix_proposal"].edit.scope, "expression")
        self.assertEqual(expr_instance["fix_proposal"].edit.original_text, "intern('abc')")
        self.assertEqual(expr_instance["fix_proposal"].edit.replacement_text, "sys.intern('abc')")
        self.assertEqual(expr_instance["fix_proposal"].edit.col_start, 8)
        self.assertEqual(expr_instance["fix_proposal"].edit.col_end, 21)
        self.assertEqual(expr_instance["fix_proposal"].required_imports, ["import sys"])

    def test_statement_parsers_keep_current_shapes(self):
        self.assertEqual(
            wf._parse_exec_statement("exec code"),
            {
                "statement_text": "exec code",
                "col_start": 0,
                "col_end": 9,
                "expr_text": "code",
                "globals_text": None,
                "locals_text": None,
            },
        )
        self.assertEqual(
            wf._parse_exec_statement("exec code in g"),
            {
                "statement_text": "exec code in g",
                "col_start": 0,
                "col_end": 14,
                "expr_text": "code",
                "globals_text": "g",
                "locals_text": None,
            },
        )
        self.assertEqual(
            wf._parse_exec_statement("exec code in g, l"),
            {
                "statement_text": "exec code in g, l",
                "col_start": 0,
                "col_end": 17,
                "expr_text": "code",
                "globals_text": "g",
                "locals_text": "l",
            },
        )
        self.assertEqual(
            wf._parse_class_statement("class Foo:"),
            {
                "statement_text": "class Foo:",
                "col_start": 0,
                "col_end": 10,
                "class_name": "Foo",
                "bases_text": None,
            },
        )
        self.assertEqual(
            wf._parse_class_statement("class Foo(Base):"),
            {
                "statement_text": "class Foo(Base):",
                "col_start": 0,
                "col_end": 16,
                "class_name": "Foo",
                "bases_text": "Base",
            },
        )

    def test_builder_regressions_keep_replacements_and_required_imports(self):
        next_rule = self._rule("next_method")
        next_raw = self._raw("value = it.next()")
        next_result = wf.next_method_builder(next_raw, None, next_rule)[0]
        self.assertEqual(next_result["warning_type"], "NEXT_METHOD_WARNING")
        self.assertEqual(next_result["auto_fix_line"], "next(it)")
        self.assertEqual(next_result["required_imports"], [])
        self.assertIsNotNone(next_result["fix_proposal"])

        intern_rule = self._rule("intern_builtin")
        intern_raw = self._raw("value = intern('abc')")
        intern_result = wf.intern_builder(intern_raw, None, intern_rule)[0]
        self.assertEqual(intern_result["warning_type"], "INTERN_WARNING")
        self.assertEqual(intern_result["auto_fix_line"], "sys.intern('abc')")
        self.assertEqual(intern_result["required_imports"], ["import sys"])
        self.assertIsNotNone(intern_result["fix_proposal"])

        range_rule = self._rule("range_materialization_range")
        range_line = "nums = range(3) + [4]"
        range_raw = self._raw(
            range_line,
            metadata={"consumer_op": "BINARY_ADD", "materialization_required": True},
        )
        range_result = wf.range_materialization_builder(
            range_raw,
            self._resolved_callsite(range_line, "range(3)", 7, 15),
            range_rule,
        )[0]
        self.assertEqual(range_result["warning_type"], "RANGE_MATERIALIZATION_WARNING")
        self.assertEqual(range_result["auto_fix_line"], "list(range(3))")

        dict_rule = self._rule("dict_listlike_keys")
        dict_line = "second = d.keys()[1]"
        dict_raw = self._raw(
            dict_line,
            metadata={"consumer_op": "BINARY_SUBSCR", "materialization_required": True},
        )
        dict_result = wf.dict_listlike_builder(
            dict_raw,
            self._resolved_callsite(dict_line, "d.keys()", 9, 17),
            dict_rule,
        )[0]
        self.assertEqual(dict_result["warning_type"], "DICT_LISTLIKE_WARNING")
        self.assertEqual(dict_result["auto_fix_line"], "list(d.keys())")

        base64_rule = self._rule("base64_b64encode")
        base64_line = "value = 'prefix:' + base64.b64encode('x')"
        base64_raw = self._raw(
            base64_line,
            metadata={"consumer_op": "BINARY_ADD", "text_consumer": True},
        )
        base64_result = wf.base64_text_builder(
            base64_raw,
            self._resolved_callsite(base64_line, "base64.b64encode('x')", 20, 41),
            base64_rule,
        )[0]
        self.assertEqual(base64_result["warning_type"], "BASE64_B64ENCODE_WARNING")
        self.assertEqual(base64_result["auto_fix_line"], 'base64.b64encode(\'x\').decode("ascii")')

        exec_rule = self._rule("exec_statement")
        exec_result = wf.exec_statement_builder(
            self._raw("exec code in g, l"),
            None,
            exec_rule,
        )[0]
        self.assertEqual(exec_result["warning_type"], "EXEC_STATEMENT_WARNING")
        self.assertEqual(exec_result["auto_fix_line"], "exec(code, g, l)")

        class_rule = self._rule("old_style_class")
        class_result = wf.old_style_class_builder(
            self._raw("class Foo:"),
            None,
            class_rule,
        )[0]
        self.assertEqual(class_result["warning_type"], "OLD_STYLE_CLASS_WARNING")
        self.assertEqual(class_result["auto_fix_line"], "class Foo(object):")

        mro_rule = self._rule("mro_risk")
        mro_result = wf.mro_risk_builder(
            self._raw("class C(A, B):"),
            None,
            mro_rule,
        )[0]
        self.assertEqual(mro_result["warning_type"], "MRO_RISK_WARNING")
        self.assertIsNone(mro_result["fix_proposal"])

    def test_stringio_compat_builder_covers_text_bytes_and_unknown_paths(self):
        rule = self._rule("stringio_module")
        cstring_rule = self._rule("cstringio_module")

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        from_text = "from StringIO import StringIO\nbuf = StringIO()\n"
        from_text_path = os.path.join(tmp.name, "from_text.py")
        with open(from_text_path, "w", encoding="utf-8") as f:
            f.write(from_text)
        text_instances = wf.stringio_compat_builder(
            self._raw(
                "buf = StringIO()",
                metadata={"module_name": "StringIO", "usage_kind": "text"},
                lineno=2,
                filename=from_text_path,
            ),
            None,
            rule,
        )
        self.assertEqual(len(text_instances), 1)
        self.assertEqual(text_instances[0]["fix_proposal"].edit.scope, "line")
        self.assertEqual(text_instances[0]["auto_fix_line"], "from io import StringIO")

        import_text = "import StringIO\nbuf = StringIO.StringIO()\n"
        import_text_path = os.path.join(tmp.name, "import_text.py")
        with open(import_text_path, "w", encoding="utf-8") as f:
            f.write(import_text)
        import_text_instances = wf.stringio_compat_builder(
            self._raw(
                "buf = StringIO.StringIO()",
                metadata={"module_name": "StringIO", "usage_kind": "text"},
                lineno=2,
                filename=import_text_path,
            ),
            None,
            rule,
        )
        self.assertEqual(len(import_text_instances), 2)
        self.assertEqual(import_text_instances[0]["fix_proposal"].edit.scope, "line")
        self.assertEqual(import_text_instances[1]["fix_proposal"].edit.scope, "expression")
        self.assertEqual(import_text_instances[1]["auto_fix_line"], "io.StringIO()")

        from_bytes = "from cStringIO import StringIO\nbuf = StringIO('abc')\n"
        from_bytes_path = os.path.join(tmp.name, "from_bytes.py")
        with open(from_bytes_path, "w", encoding="utf-8") as f:
            f.write(from_bytes)
        from_bytes_instances = wf.stringio_compat_builder(
            self._raw(
                "buf = StringIO('abc')",
                metadata={"module_name": "cStringIO", "usage_kind": "bytes"},
                lineno=2,
                filename=from_bytes_path,
            ),
            None,
            cstring_rule,
        )
        self.assertEqual(len(from_bytes_instances), 2)
        self.assertEqual(from_bytes_instances[0]["auto_fix_line"], "from io import BytesIO")
        self.assertEqual(from_bytes_instances[1]["auto_fix_line"], "BytesIO('abc')")

        import_bytes = "import cStringIO\nbuf = cStringIO.StringIO('abc')\n"
        import_bytes_path = os.path.join(tmp.name, "import_bytes.py")
        with open(import_bytes_path, "w", encoding="utf-8") as f:
            f.write(import_bytes)
        import_bytes_instances = wf.stringio_compat_builder(
            self._raw(
                "buf = cStringIO.StringIO('abc')",
                metadata={"module_name": "cStringIO", "usage_kind": "bytes"},
                lineno=2,
                filename=import_bytes_path,
            ),
            None,
            cstring_rule,
        )
        self.assertEqual(len(import_bytes_instances), 2)
        self.assertEqual(import_bytes_instances[0]["auto_fix_line"], "import io")
        self.assertEqual(import_bytes_instances[1]["auto_fix_line"], "io.BytesIO('abc')")

        unknown_instances = wf.stringio_compat_builder(
            self._raw(
                "buf = StringIO()",
                metadata={"module_name": "StringIO", "usage_kind": "unknown"},
                lineno=2,
                filename=from_text_path,
            ),
            None,
            rule,
        )
        self.assertEqual(len(unknown_instances), 1)
        self.assertIsNone(unknown_instances[0]["fix_proposal"])


if __name__ == "__main__":
    unittest.main()
