import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import bcrypt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.config.config_utils import (  # noqa: E402
    BOOLEAN_SETTING_KEYS,
    HIDDEN_SETTING_KEYS,
    cors_origins_from_children,
    is_secret_setting_key,
    load_or_create_secret_key,
    mask_last,
    restore_masked_value,
    setting_value_as_text,
    yaml_is_true,
)
from arm.ui.utils import user_has_default_password  # noqa: E402


class TestSecretMasking(unittest.TestCase):
    def test_mask_last_hides_tail(self):
        self.assertEqual(mask_last("74386ccb"), "7438****")

    def test_mask_short_value(self):
        self.assertEqual(mask_last("ab"), "**")

    def test_restore_keeps_original_when_masked(self):
        current = "74386ccb"
        self.assertEqual(restore_masked_value(mask_last(current), current), current)

    def test_restore_accepts_new_value(self):
        self.assertEqual(restore_masked_value("new-key", "74386ccb"), "new-key")

    def test_restore_allows_clearing(self):
        self.assertEqual(restore_masked_value("", "74386ccb"), "")

    def test_omdb_key_is_secret(self):
        self.assertTrue(is_secret_setting_key("OMDB_API_KEY"))
        self.assertTrue(is_secret_setting_key("MAKEMKV_PERMA_KEY"))
        self.assertFalse(is_secret_setting_key("RIPMETHOD"))


class TestFlaskSecretKey(unittest.TestCase):
    def test_env_overrides_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".flask_secret_key")
            key = load_or_create_secret_key(path, environ={"ARM_SECRET_KEY": "from-env"})
            self.assertEqual(key, "from-env")
            self.assertFalse(os.path.isfile(path))

    def test_creates_and_reuses_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".flask_secret_key")
            first = load_or_create_secret_key(path, environ={})
            second = load_or_create_secret_key(path, environ={})
            self.assertEqual(first, second)
            self.assertEqual(len(first), 64)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class TestCorsOrigins(unittest.TestCase):
    def test_empty_children(self):
        self.assertEqual(cors_origins_from_children(""), [])
        self.assertEqual(cors_origins_from_children(None), [])

    def test_splits_and_strips(self):
        self.assertEqual(
            cors_origins_from_children("http://192.168.0.100:8080/, http://arm2:8080"),
            ["http://192.168.0.100:8080", "http://arm2:8080"],
        )


class TestDefaultPassword(unittest.TestCase):
    def test_detects_admin_password(self):
        salt = bcrypt.gensalt(4)
        user = SimpleNamespace(
            email="admin",
            password=bcrypt.hashpw(b"password", salt),
            hash=salt,
        )
        self.assertTrue(user_has_default_password(user))

    def test_rejects_other_password(self):
        salt = bcrypt.gensalt(4)
        user = SimpleNamespace(
            email="admin",
            password=bcrypt.hashpw(b"other", salt),
            hash=salt,
        )
        self.assertFalse(user_has_default_password(user))


class TestRestartUi(unittest.TestCase):
    @patch("arm.ui.json_api.threading.Thread")
    @patch("arm.ui.json_api.subprocess.check_output")
    def test_restart_does_not_pkill(self, mock_check_output, mock_thread):
        mock_thread.return_value = MagicMock()
        from arm.ui.json_api import restart_ui

        result = restart_ui()

        self.assertTrue(result["success"])
        mock_check_output.assert_not_called()
        mock_thread.assert_called_once()


class TestSettingTypes(unittest.TestCase):
    def test_yaml_is_true(self):
        self.assertTrue(yaml_is_true(True))
        self.assertTrue(yaml_is_true("true"))
        self.assertTrue(yaml_is_true(1))
        self.assertFalse(yaml_is_true("false"))
        self.assertFalse(yaml_is_true(0))

    def test_setting_value_as_text(self):
        self.assertEqual(setting_value_as_text(True), "true")
        self.assertEqual(setting_value_as_text(False), "false")
        self.assertEqual(setting_value_as_text(None), "")

    def test_hidden_and_boolean_keys(self):
        self.assertIn("UNIDENTIFIED_EJECT", HIDDEN_SETTING_KEYS)
        self.assertIn("SKIP_TRANSCODE", BOOLEAN_SETTING_KEYS)
        self.assertIn("GET_VIDEO_TITLE", BOOLEAN_SETTING_KEYS)
        self.assertNotIn("RIPMETHOD", BOOLEAN_SETTING_KEYS)


class TestForkVersionCheck(unittest.TestCase):
    def test_git_check_updates_skips_upstream(self):
        from arm.ui.utils import git_check_updates
        self.assertTrue(git_check_updates("abc123"))

    def test_git_check_version_matches_local(self):
        from arm.ui.utils import git_check_version
        local, remote = git_check_version()
        self.assertEqual(local, remote)


class TestFfprobeNoShell(unittest.TestCase):
    @patch("arm.ripper.ffmpeg.subprocess.check_output")
    def test_probe_source_does_not_use_shell(self, mock_check_output):
        mock_check_output.return_value = b"{}"
        from arm.ripper.ffmpeg import probe_source

        probe_source("/tmp/Disc Title.mkv")

        args, kwargs = mock_check_output.call_args
        self.assertIsInstance(args[0], list)
        self.assertEqual(args[0][0], "ffprobe")
        self.assertIn("/tmp/Disc Title.mkv", args[0])
        self.assertFalse(kwargs.get("shell", False))


if __name__ == "__main__":
    unittest.main()
