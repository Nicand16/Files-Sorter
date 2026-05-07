import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.crud_executor import move_file_secure
from modules.multimodal_parser import extract_document_content
from modules.periodic_scanner import scan_directory_once
from modules.rules_engine import classify_file
from core.settings_manager import validate_poll_interval, validate_watch_directory


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


if __name__ == "__main__":
    unittest.main()
