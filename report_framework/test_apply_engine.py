import os
import sys
import tempfile
import unittest


HERE = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import web_frontend
from apply_engine import apply_fix_proposals, build_fix_proposal
from file_io import save_with_backup
from framework import analyze_file_with_output
from services.file_service import build_tree_for_ui
from warning_fixes import bytesio_truncate_fix
from web_frontend import app


class ApplyEngineTests(unittest.TestCase):
    def _proposal(
        self,
        *,
        line,
        scope,
        original,
        replacement,
        warning_type,
        required_imports=None,
        col_start=None,
        col_end=None,
    ):
        proposal = build_fix_proposal(
            filename="/tmp/sample.py",
            rel_filename="sample.py",
            lineno=line,
            warning_type=warning_type,
            message=warning_type,
            scope=scope,
            original_text=original,
            replacement_text=replacement,
            col_start=col_start,
            col_end=col_end,
            required_imports=required_imports or [],
        )
        self.assertIsNotNone(proposal)
        return proposal

    def test_cmp_arg_adds_missing_import_and_diff(self):
        source = (
            "#!/usr/bin/env python\n"
            "# -*- coding: utf-8 -*-\n"
            "\"\"\"demo\"\"\"\n"
            "\n"
            "def sort_values(seq):\n"
            "    seq.sort(cmp=mycmp)\n"
            "    return seq\n"
        )
        proposal = self._proposal(
            line=6,
            scope="line",
            original="    seq.sort(cmp=mycmp)",
            replacement="    seq.sort(key=cmp_to_key(mycmp))",
            warning_type="CMP_ARG_WARNING",
            required_imports=["from functools import cmp_to_key"],
        )

        result = apply_fix_proposals(
            source_text=source,
            proposals=[proposal],
            rel_filename="sample.py",
        )

        self.assertIn("from functools import cmp_to_key", result.source_text)
        self.assertIn("    seq.sort(key=cmp_to_key(mycmp))", result.source_text)
        self.assertEqual(result.applied_count, 1)
        self.assertIn("--- a/sample.py", result.diff_text)
        self.assertIn("+++ b/sample.py", result.diff_text)
        self.assertIn("+from functools import cmp_to_key", result.diff_text)
        self.assertIn("-    seq.sort(cmp=mycmp)", result.diff_text)
        self.assertIn("+    seq.sort(key=cmp_to_key(mycmp))", result.diff_text)

    def test_cmp_arg_does_not_duplicate_existing_import(self):
        source = (
            "from functools import cmp_to_key\n"
            "\n"
            "def sort_values(seq):\n"
            "    seq.sort(cmp=mycmp)\n"
            "    return seq\n"
        )
        proposal = self._proposal(
            line=4,
            scope="line",
            original="    seq.sort(cmp=mycmp)",
            replacement="    seq.sort(key=cmp_to_key(mycmp))",
            warning_type="CMP_ARG_WARNING",
            required_imports=["from functools import cmp_to_key"],
        )

        result = apply_fix_proposals(
            source_text=source,
            proposals=[proposal],
            rel_filename="sample.py",
        )

        self.assertEqual(result.source_text.count("from functools import cmp_to_key"), 1)
        self.assertEqual(result.applied_count, 1)

    def test_has_key_replaces_only_target_expression(self):
        source = 'result = [d.has_key("a"), keep_me, d.has_key("b")]\n'
        target = 'd.has_key("a")'
        col_start = source.index(target)
        proposal = self._proposal(
            line=1,
            scope="expression",
            original=target,
            replacement='"a" in d',
            warning_type="HAS_KEY_WARNING",
            col_start=col_start,
            col_end=col_start + len(target),
        )

        result = apply_fix_proposals(
            source_text=source,
            proposals=[proposal],
            rel_filename="sample.py",
        )

        self.assertEqual(
            result.source_text,
            'result = ["a" in d, keep_me, d.has_key("b")]\n',
        )
        self.assertIn("keep_me", result.source_text)
        self.assertIn('d.has_key("b")', result.source_text)

    def test_bytesio_truncate_line_scope_keeps_callable_rewrite(self):
        source = (
            "from io import BytesIO\n"
            "x = BytesIO('AAAA')\n"
            "x.seek(3)\n"
            "n = x.truncate(0)\n"
        )
        original = "n = x.truncate(0)"
        replacement = bytesio_truncate_fix(original, {})
        proposal = self._proposal(
            line=4,
            scope="line",
            original=original,
            replacement=replacement,
            warning_type="BYTESIO_TRUNCATE_WARNING",
        )

        result = apply_fix_proposals(
            source_text=source,
            proposals=[proposal],
            rel_filename="sample.py",
        )

        self.assertIn("x.seek(0); n = x.truncate()", result.source_text)
        self.assertEqual(result.applied_count, 1)

    def test_multiple_warnings_same_line_apply_right_to_left(self):
        source = 'result = [d.has_key("a"), d.has_key("b")]\n'
        first = 'd.has_key("a")'
        second = 'd.has_key("b")'
        first_start = source.index(first)
        second_start = source.index(second)
        proposals = [
            self._proposal(
                line=1,
                scope="expression",
                original=first,
                replacement='"a" in d',
                warning_type="HAS_KEY_WARNING",
                col_start=first_start,
                col_end=first_start + len(first),
            ),
            self._proposal(
                line=1,
                scope="expression",
                original=second,
                replacement='"b" in d',
                warning_type="HAS_KEY_WARNING",
                col_start=second_start,
                col_end=second_start + len(second),
            ),
        ]

        result = apply_fix_proposals(
            source_text=source,
            proposals=proposals,
            rel_filename="sample.py",
        )

        self.assertEqual(result.source_text, 'result = ["a" in d, "b" in d]\n')
        self.assertEqual(result.applied_count, 2)

    def test_preview_apply_endpoint_returns_backend_preview(self):
        source = "def sort_values(seq):\n    seq.sort(cmp=mycmp)\n"
        proposal = self._proposal(
            line=2,
            scope="line",
            original="    seq.sort(cmp=mycmp)",
            replacement="    seq.sort(key=cmp_to_key(mycmp))",
            warning_type="CMP_ARG_WARNING",
            required_imports=["from functools import cmp_to_key"],
        )
        client = app.test_client()

        response = client.post(
            "/preview_apply",
            json={
                "root": "/tmp",
                "file": "sample.py",
                "sourceText": source,
                "warnings": [
                    {
                        "file": "sample.py",
                        "proposal": proposal.to_dict(),
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["appliedCount"], 1)
        self.assertIn("cmp_to_key", data["sourceText"])
        self.assertIn("--- a/sample.py", data["diffText"])

    def test_autosave_endpoint_persists_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sample.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write("print('old')\n")

            client = app.test_client()
            response = client.post(
                "/autosave",
                json={
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": "print('new')\n",
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["ok"])
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "print('new')\n")

    def test_save_and_reanalyze_endpoint_closes_loop_for_current_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sample.py")
            original = 'd = {"a": 1}\nprint(d.has_key("a"))\n'
            fixed = 'd = {"a": 1}\nprint("a" in d)\n'
            with open(path, "w", encoding="utf-8") as f:
                f.write(original)

            client = app.test_client()
            response = client.post(
                "/save_and_reanalyze",
                json={
                    "engine": REPO_ROOT,
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": fixed,
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["warningCount"], 0)
            self.assertEqual(data["warnings"], [])
            self.assertEqual(data["sourceText"], fixed)
            self.assertIn("True", data["runOutput"])
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), fixed)

    def test_save_and_reanalyze_warning_payload_keeps_span_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sample.py")
            source = 'd = {"a": 1}\nprint(d.has_key("a"))\n'
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)

            client = app.test_client()
            response = client.post(
                "/save_and_reanalyze",
                json={
                    "engine": REPO_ROOT,
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": source,
                },
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["warningCount"], 1)
            warning = data["warnings"][0]
            for key in ("warningId", "line", "type", "message", "original", "fix", "proposal", "colStart", "colEnd"):
                self.assertIn(key, warning)
            self.assertEqual(warning["type"], "HAS_KEY_WARNING")
            self.assertEqual(warning["proposal"]["edit"]["scope"], "expression")
            self.assertIsInstance(warning["colStart"], int)
            self.assertIsInstance(warning["colEnd"], int)
            self.assertGreater(warning["colEnd"], warning["colStart"])

            response2 = client.post(
                "/save_and_reanalyze",
                json={
                    "engine": REPO_ROOT,
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": source,
                },
            )
            self.assertEqual(response2.status_code, 200)
            data2 = response2.get_json()
            self.assertEqual(data2["warnings"][0]["warningId"], warning["warningId"])

    def test_preview_apply_then_save_and_reanalyze_smoke_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sample.py")
            source = 'd = {"a": 1}\nprint(d.has_key("a"))\n'
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)

            warnings, _ = analyze_file_with_output(REPO_ROOT, tmpdir, "sample.py")
            current_warnings = [w for w in warnings if w.rel_filename == "sample.py"]
            payload = web_frontend._serialize_warnings_for_client(
                current_warnings,
                {"sample.py": source},
            )

            client = app.test_client()
            preview_response = client.post(
                "/preview_apply",
                json={
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": source,
                    "warnings": payload,
                },
            )
            self.assertEqual(preview_response.status_code, 200)
            preview_data = preview_response.get_json()
            self.assertTrue(preview_data["ok"])
            self.assertGreaterEqual(preview_data["appliedCount"], 1)

            save_response = client.post(
                "/save_and_reanalyze",
                json={
                    "engine": REPO_ROOT,
                    "root": tmpdir,
                    "file": "sample.py",
                    "sourceText": preview_data["sourceText"],
                },
            )
            self.assertEqual(save_response.status_code, 200)
            save_data = save_response.get_json()
            self.assertTrue(save_data["ok"])
            self.assertEqual(save_data["warningCount"], 0)
            self.assertIsInstance(save_data["warnings"], list)
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), preview_data["sourceText"])

    def test_save_with_backup_refreshes_latest_diff_baseline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sample.py")
            prev_path = os.path.join(tmpdir, ".pygrate_history", "sample.py.prev")
            with open(path, "w", encoding="utf-8") as f:
                f.write("print('v1')\n")

            save_with_backup(tmpdir, "sample.py", "print('v2')\n")
            with open(prev_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "print('v1')\n")

            save_with_backup(tmpdir, "sample.py", "print('v3')\n")
            with open(prev_path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), "print('v2')\n")

    def test_build_tree_for_ui_excludes_internal_history_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".pygrate_history"), exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "__pycache__"), exist_ok=True)
            os.makedirs(os.path.join(tmpdir, "pkg"), exist_ok=True)
            with open(os.path.join(tmpdir, ".pygrate_history", "shadow.py"), "w", encoding="utf-8") as f:
                f.write("print('shadow')\n")
            with open(os.path.join(tmpdir, "__pycache__", "cache.py"), "w", encoding="utf-8") as f:
                f.write("print('cache')\n")
            with open(os.path.join(tmpdir, "pkg", "real.py"), "w", encoding="utf-8") as f:
                f.write("print('real')\n")

            tree = build_tree_for_ui(tmpdir)

            self.assertNotIn(".pygrate_history", tree)
            self.assertNotIn("__pycache__", tree)
            self.assertIn("pkg", tree)
            self.assertEqual(tree["pkg"]["__files__"], ["real.py"])

    def test_project_page_renders_frontend_shell_assets(self):
        client = app.test_client()
        response = client.get("/project")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("window.PYGRATE_BOOTSTRAP", html)
        self.assertIn("/static/frontend/", html)
        self.assertIn("Pygrate Project", html)

    def test_api_project_returns_tree_nodes_without_internal_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".pygrate_history"), exist_ok=True)
            with open(os.path.join(tmpdir, "sample.py"), "w", encoding="utf-8") as f:
                f.write("print('ok')\n")
            with open(os.path.join(tmpdir, ".pygrate_history", "shadow.py"), "w", encoding="utf-8") as f:
                f.write("print('shadow')\n")

            client = app.test_client()
            response = client.get(
                "/api/project",
                query_string={"engine": REPO_ROOT, "root": tmpdir},
            )

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["treeNodes"][0]["path"], "sample.py")
            paths = []
            stack = list(data["treeNodes"])
            while stack:
                node = stack.pop()
                paths.append(node["path"])
                stack.extend(node.get("children", []))
            self.assertNotIn(".pygrate_history", paths)


if __name__ == "__main__":
    unittest.main()
