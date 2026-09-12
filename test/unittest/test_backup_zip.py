import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone

_BACKUP_ZIP_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "../../arm/ui/settings/backup_zip.py",
))
_spec = importlib.util.spec_from_file_location("arm_backup_zip", _BACKUP_ZIP_PATH)
backup_zip = importlib.util.module_from_spec(_spec)
sys.modules["arm_backup_zip"] = backup_zip
_spec.loader.exec_module(backup_zip)

BackupError = backup_zip.BackupError
MEMBER_ARM_YAML = backup_zip.MEMBER_ARM_YAML
MEMBER_DB = backup_zip.MEMBER_DB
backup_filename = backup_zip.backup_filename
build_backup_zip = backup_zip.build_backup_zip
extract_backup_zip = backup_zip.extract_backup_zip
normalize_zip_name = backup_zip.normalize_zip_name
snapshot_sqlite = backup_zip.snapshot_sqlite


class TestBackupZip(unittest.TestCase):
    def test_backup_filename(self):
        when = datetime(2026, 9, 11, 3, 4, 5, tzinfo=timezone.utc)
        self.assertEqual(backup_filename(when), "arm-backup-20260911-030405.zip")

    def test_normalize_rejects_parent_segments(self):
        with self.assertRaises(BackupError):
            normalize_zip_name("../etc/passwd")
        with self.assertRaises(BackupError):
            normalize_zip_name("db/../../etc/passwd")
        with self.assertRaises(BackupError):
            normalize_zip_name("")

    def test_normalize_allows_known_members(self):
        self.assertEqual(normalize_zip_name("config/arm.yaml"), "config/arm.yaml")
        self.assertEqual(normalize_zip_name("db/arm.db"), "db/arm.db")

    def test_roundtrip_yaml_and_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            yaml_path = os.path.join(tmp, "arm.yaml")
            db_path = os.path.join(tmp, "arm.db")
            with open(yaml_path, "w", encoding="utf-8") as handle:
                handle.write("ARM_NAME: lab\n")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE job (job_id INTEGER PRIMARY KEY, title TEXT)")
            conn.execute("INSERT INTO job (title) VALUES ('Demo')")
            conn.commit()
            conn.close()

            buf, name = build_backup_zip(
                {"arm_yaml": yaml_path, "dbfile": db_path},
                arm_version="2.24.4",
                created=datetime(2026, 9, 11, tzinfo=timezone.utc),
            )
            self.assertTrue(name.endswith(".zip"))

            extracted_dir = os.path.join(tmp, "out")
            os.makedirs(extracted_dir)
            manifest, extracted = extract_backup_zip(buf, extracted_dir)
            self.assertEqual(manifest["format"], "arm-backup")
            self.assertEqual(manifest["arm_version"], "2.24.4")
            self.assertIn(MEMBER_ARM_YAML, extracted)
            self.assertIn(MEMBER_DB, extracted)
            with open(extracted[MEMBER_ARM_YAML], encoding="utf-8") as handle:
                self.assertIn("ARM_NAME: lab", handle.read())
            check = sqlite3.connect(extracted[MEMBER_DB])
            row = check.execute("SELECT title FROM job").fetchone()
            check.close()
            self.assertEqual(row[0], "Demo")

    def test_snapshot_includes_wal_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "arm.db")
            dest = os.path.join(tmp, "copy.db")
            conn = sqlite3.connect(src)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE job (title TEXT)")
            conn.execute("INSERT INTO job VALUES ('one')")
            conn.commit()
            conn.close()
            snapshot_sqlite(src, dest)
            check = sqlite3.connect(dest)
            self.assertEqual(check.execute("SELECT title FROM job").fetchone()[0], "one")
            check.close()

    def test_rejects_unknown_member(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "format": "arm-backup",
                "version": 1,
            }))
            archive.writestr("notes.txt", "nope")
        buf.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BackupError):
                extract_backup_zip(buf, tmp)

    def test_rejects_wrong_format(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "format": "other",
                "version": 1,
            }))
            archive.writestr("config/arm.yaml", "ARM_NAME: x\n")
        buf.seek(0)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BackupError):
                extract_backup_zip(buf, tmp)


if __name__ == "__main__":
    unittest.main()
