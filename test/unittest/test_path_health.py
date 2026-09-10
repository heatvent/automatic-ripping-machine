import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.config.path_health import (  # noqa: E402
    check_path_health,
    ensure_writable_dir,
    media_path_health,
)


class TestPathHealth(unittest.TestCase):
    def test_empty_path(self):
        row = check_path_health("")
        self.assertFalse(row["ok"])
        self.assertEqual(row["error"], "Path is empty")

    def test_missing_folder(self):
        row = check_path_health("/no/such/arm/folder")
        self.assertFalse(row["ok"])
        self.assertFalse(row["is_dir"])

    def test_writable_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = check_path_health(tmp)
            self.assertTrue(row["ok"])
            self.assertTrue(row["writable"])
            self.assertEqual(row["error"], "")

    def test_file_is_not_a_folder(self):
        with tempfile.NamedTemporaryFile() as handle:
            row = check_path_health(handle.name)
            self.assertFalse(row["ok"])
            self.assertIn("not a folder", row["error"])

    def test_media_path_health_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = media_path_health({
                "RAW_PATH": tmp,
                "TRANSCODE_PATH": tmp,
                "COMPLETED_PATH": "/no/such/completed",
            })
            labels = [row["label"] for row in rows]
            self.assertEqual(labels, ["Raw", "Transcode", "Completed"])
            self.assertTrue(rows[0]["ok"])
            self.assertFalse(rows[2]["ok"])

    def test_ensure_writable_dir_creates(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "raw")
            ensure_writable_dir(nested)
            self.assertTrue(os.path.isdir(nested))

    def test_ensure_writable_dir_tolerates_eexist_on_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.makedirs", side_effect=OSError(17, "File exists", tmp)):
                ensure_writable_dir(tmp)


if __name__ == "__main__":
    unittest.main()
