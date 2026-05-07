import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.crud_executor import move_file_secure
from modules.multimodal_parser import extract_document_content
from modules.periodic_scanner import scan_directory_once
from modules.rules_engine import classify_file
from core.settings_manager import validate_poll_interval, validate_watch_directory
from db.database_manager import DatabaseManager
from main import _run_interval_loop, get_briner_data_dir


class RulesEngineTests(unittest.TestCase):
    def test_classifies_extension_from_config(self):
        config = {
            "taxonomy": {
                "categories": [
                    {"category": "Media/Videos", "extensions": [".mp4"]},
                ]
            }
        }

        decision = classify_file("clip.MP4", ".MP4", config)

        self.assertEqual(decision.category, "Media/Videos")
        self.assertEqual(decision.action, "move")

    def test_generic_pdf_is_ambiguous_by_default(self):
        self.assertIsNone(classify_file("unknown.pdf", ".pdf", {"rules": {}}))


class MoveFileTests(unittest.TestCase):
    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "file.txt"
            source.write_text("hello", encoding="utf-8")

            result = move_file_secure(str(source), "../escape", workspace, dry_run=True)

            self.assertFalse(result["ok"])

    def test_dry_run_does_not_move_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "file.txt"
            source.write_text("hello", encoding="utf-8")

            result = move_file_secure(str(source), "Docs", workspace, dry_run=True)

            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertTrue(source.exists())

    def test_workspace_mismatch_reports_resolved_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            outside = root / "outside"
            workspace.mkdir()
            outside.mkdir()
            source = outside / "file.txt"
            source.write_text("hello", encoding="utf-8")

            result = move_file_secure(str(source), "Docs", workspace, dry_run=True)

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "workspace_mismatch")
            self.assertIn("source_resuelto=", result["message"])
            self.assertIn("workspace_resuelto=", result["message"])

    def test_destination_aliases_use_existing_numbered_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "actividad.pdf"
            source.write_text("hello", encoding="utf-8")

            result = move_file_secure(
                str(source),
                "Universidad y Estudio/Actividades y Tareas",
                workspace,
                dry_run=True,
                destination_aliases={"Universidad y Estudio": "1. Universidad y Estudio"},
            )

            self.assertTrue(result["ok"])
            self.assertIn("1. Universidad y Estudio", result["new_path"])


class SettingsTests(unittest.TestCase):
    def test_rejects_poll_interval_under_minimum(self):
        with self.assertRaises(ValueError):
            validate_poll_interval(9)

    def test_accepts_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(validate_watch_directory(temp_dir), str(Path(temp_dir).resolve()))

    def test_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            with self.assertRaises(ValueError):
                validate_watch_directory(missing)



    def test_get_briner_data_dir_uses_xdg_when_frozen_without_appdata(self):
        with patch.dict("main.os.environ", {"XDG_DATA_HOME": "/tmp/xdg"}, clear=True):
            data_dir = get_briner_data_dir(is_frozen=True, home=Path("/home/tester"))

        self.assertEqual(data_dir, Path("/tmp/xdg/Briner").resolve())

    def test_get_briner_data_dir_honors_override(self):
        with patch.dict("main.os.environ", {"BRINER_HOME": "~/custom_briner"}, clear=True):
            data_dir = get_briner_data_dir(is_frozen=True, home=Path("/home/tester"))

        self.assertEqual(data_dir, Path("~/custom_briner").expanduser().resolve())

class FakeDb:
    def __init__(self):
        self.registered = []

    def register_file(self, *info):
        self.registered.append(info)
        return True


class PeriodicScannerTests(unittest.TestCase):
    def test_scan_directory_once_registers_new_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "document.txt").write_text("hello", encoding="utf-8")
            (root / "desktop.ini").write_text("ignored", encoding="utf-8")
            (root / "~$lock.docx").write_text("ignored", encoding="utf-8")
            db = FakeDb()

            count = scan_directory_once(root, db, {})

            self.assertEqual(count, 1)
            self.assertEqual(db.registered[0][0], "document.txt")

    def test_scan_ignores_destination_alias_roots_when_recursive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "new.pdf").write_text("new", encoding="utf-8")
            organized = root / "1. Universidad y Estudio"
            organized.mkdir()
            (organized / "old.pdf").write_text("old", encoding="utf-8")
            db = FakeDb()

            count = scan_directory_once(
                root,
                db,
                {
                    "monitoring": {
                        "recursive": True,
                        "destination_aliases": {"Universidad y Estudio": "1. Universidad y Estudio"},
                    }
                },
            )

            self.assertEqual(count, 1)
            self.assertEqual(db.registered[0][0], "new.pdf")


class IntervalLoopTests(unittest.TestCase):
    def test_interval_loop_scans_immediately_before_sleep(self):
        calls = []

        class FakeOrchestrator:
            def process_pending_files(self):
                calls.append("process")
                return {"processed": 0, "errors": 0}

        class FakeDb:
            pass

        def fake_scan(workspace_dir, db_manager, config):
            calls.append("scan")
            return 0

        def fake_sleep(seconds):
            calls.append(("sleep", seconds))
            raise RuntimeError("stop loop")

        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            with patch("main.scan_directory_once", side_effect=fake_scan), patch("main.time.sleep", side_effect=fake_sleep):
                with self.assertRaises(RuntimeError):
                    _run_interval_loop(FakeOrchestrator(), FakeDb(), workspace, {}, 3600, once=False)

        self.assertEqual(calls, ["scan", "process", ("sleep", 1)])


class ParserTests(unittest.TestCase):
    def test_extracts_docx_text_with_stdlib_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            docx = Path(temp_dir) / "sample.docx"
            xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Hello from docx</w:t></w:r></w:p></w:body></w:document>"
            )
            with zipfile.ZipFile(docx, "w") as archive:
                archive.writestr("word/document.xml", xml)

            content = extract_document_content(str(docx))

            self.assertIn("Hello from docx", content)


class SchemaTests(unittest.TestCase):
    def test_schema_creates_classification_events(self):
        schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
        conn = sqlite3.connect(":memory:")
        conn.executescript(schema)

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        self.assertIn("files", tables)
        self.assertIn("classification_events", tables)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        self.assertIn("retry_count", columns)


class DatabaseRetryTests(unittest.TestCase):
    def test_register_file_stops_requeueing_after_three_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "briner.db"
            db = DatabaseManager(str(db_path))
            filepath = str((Path(temp_dir) / "file.txt").resolve())

            self.assertTrue(db.register_file("file.txt", filepath, ".txt", 5, 1.0))
            db.update_file_status(filepath, "error")
            self.assertTrue(db.register_file("file.txt", filepath, ".txt", 5, 2.0))
            db.update_file_status(filepath, "error")
            self.assertTrue(db.register_file("file.txt", filepath, ".txt", 5, 3.0))
            db.update_file_status(filepath, "error")

            self.assertFalse(db.register_file("file.txt", filepath, ".txt", 5, 4.0))

            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT status, retry_count FROM files WHERE filepath = ?", (filepath,)).fetchone()
            finally:
                conn.close()

            self.assertEqual(row["status"], "error")
            self.assertEqual(row["retry_count"], 3)


if __name__ == "__main__":
    unittest.main()
