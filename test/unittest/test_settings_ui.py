import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.config.config_utils import ENUM_SETTING_CHOICES  # noqa: E402
from arm.ui.settings.abcde_utils import (  # noqa: E402
    apply_abcde_updates,
    parse_abcde_values,
    validate_abcde_form,
)
from arm.ui.settings.setting_meta import (  # noqa: E402
    grouped_setting_keys,
    page_setting_groups,
    setting_label,
    validate_ripper_form,
    validate_ui_form,
)


class TestSettingMeta(unittest.TestCase):
    def test_friendly_label_then_key(self):
        self.assertEqual(setting_label("ARM_NAME"), "Machine name")
        self.assertEqual(setting_label("UNKNOWN_FLAG"), "Unknown Flag")

    def test_enum_choices_are_value_label_pairs(self):
        for key, choices in ENUM_SETTING_CHOICES.items():
            self.assertTrue(choices, key)
            for item in choices:
                self.assertEqual(len(item), 2, key)
                self.assertIsInstance(item[0], str)
                self.assertIsInstance(item[1], str)

    def test_groups_cover_known_keys_and_leftovers(self):
        settings = {
            "ARM_NAME": "lab",
            "RIPMETHOD": "mkv",
            "HB_PRESET_DVD": "HQ",
            "UNIDENTIFIED_EJECT": "true",
            "CUSTOM_EXTRA": "1",
        }
        groups = grouped_setting_keys(settings)
        titles = [title for _, title, _ in groups]
        self.assertIn("General", titles)
        self.assertIn("MakeMKV", titles)
        self.assertIn("HandBrake", titles)
        other = [keys for group_id, _, keys in groups if group_id == "other"]
        self.assertEqual(other, [["CUSTOM_EXTRA"]])
        all_keys = [key for _, _, keys in groups for key in keys]
        self.assertNotIn("UNIDENTIFIED_EJECT", all_keys)

    def test_page_groups_split_system_ripper_and_notify(self):
        settings = {
            "ARM_NAME": "lab",
            "DISABLE_LOGIN": "false",
            "RIPMETHOD": "mkv",
            "EMBY_SERVER": "emby",
            "NOTIFY_RIP": "true",
            "CUSTOM_EXTRA": "1",
            "UNIDENTIFIED_EJECT": "true",
        }
        pages = page_setting_groups(settings)
        general_keys = [key for _, _, keys in pages["general"] for key in keys]
        ripper_keys = [key for _, _, keys in pages["ripper"] for key in keys]
        notify_keys = [key for _, _, keys in pages["notify"] for key in keys]
        self.assertIn("ARM_NAME", general_keys)
        self.assertIn("DISABLE_LOGIN", general_keys)
        self.assertNotIn("ARM_NAME", ripper_keys)
        self.assertIn("RIPMETHOD", ripper_keys)
        self.assertIn("CUSTOM_EXTRA", ripper_keys)
        self.assertIn("EMBY_SERVER", notify_keys)
        self.assertIn("NOTIFY_RIP", notify_keys)
        self.assertNotIn("UNIDENTIFIED_EJECT", general_keys + ripper_keys + notify_keys)

    def test_ripper_validation(self):
        errors = validate_ripper_form({
            "WEBSERVER_PORT": "99999",
            "CHMOD_VALUE": "99",
            "MINLENGTH": "800",
            "MAXLENGTH": "100",
            "RIPMETHOD": "nope",
            "SKIP_TRANSCODE": "maybe",
            "LOGLIFE": "3",
        })
        self.assertIn("WEBSERVER_PORT", errors)
        self.assertIn("CHMOD_VALUE", errors)
        self.assertIn("MAXLENGTH", errors)
        self.assertIn("RIPMETHOD", errors)
        self.assertIn("SKIP_TRANSCODE", errors)
        self.assertNotIn("LOGLIFE", errors)

    def test_ripper_validation_accepts_good_values(self):
        errors = validate_ripper_form({
            "WEBSERVER_PORT": "8080",
            "CHMOD_VALUE": "775",
            "MINLENGTH": "600",
            "MAXLENGTH": "99999",
            "RIPMETHOD": "mkv",
            "SKIP_TRANSCODE": "true",
            "csrf_token": "x",
        })
        self.assertEqual(errors, {})

    def test_ui_validation(self):
        self.assertIn("index_refresh", validate_ui_form(100, 25))
        self.assertIn("database_limit", validate_ui_form(2000, 0))
        self.assertEqual(validate_ui_form(2000, 25), {})


class TestAbcdeUtils(unittest.TestCase):
    SAMPLE = """\
# CDDBMETHOD=cddb
CDDBMETHOD=musicbrainz
OUTPUTTYPE=flac
# keep this comment
mungealbumname() {
  echo hi
}
PADTRACKS=n
MAXPROCS=2
"""

    def test_parse_prefers_active_assignment(self):
        values, active = parse_abcde_values(self.SAMPLE)
        self.assertEqual(values["CDDBMETHOD"], "musicbrainz")
        self.assertIn("CDDBMETHOD", active)
        self.assertEqual(values["PADTRACKS"], "n")

    def test_apply_preserves_functions_and_comments(self):
        updated = apply_abcde_updates(self.SAMPLE, {
            "CDDBMETHOD": "cddb",
            "PADTRACKS": "yes",
            "MAXPROCS": "4",
            "OUTPUTTYPE": "flac,mp3",
        })
        self.assertIn("# keep this comment", updated)
        self.assertIn("mungealbumname() {", updated)
        self.assertIn("CDDBMETHOD=cddb", updated)
        self.assertNotIn("CDDBMETHOD=musicbrainz", updated)
        self.assertIn("PADTRACKS=y", updated)
        self.assertIn("MAXPROCS=4", updated)
        self.assertIn("OUTPUTTYPE=flac,mp3", updated)

    def test_validate_abcde_form(self):
        errors = validate_abcde_form({
            "PADTRACKS": "maybe",
            "MAXPROCS": "99",
            "CDDBMETHOD": "ldap",
        })
        self.assertIn("PADTRACKS", errors)
        self.assertIn("MAXPROCS", errors)
        self.assertIn("CDDBMETHOD", errors)
        self.assertEqual(validate_abcde_form({
            "PADTRACKS": "y",
            "MAXPROCS": "4",
            "CDDBMETHOD": "musicbrainz",
            "OUTPUTTYPE": "flac,mp3",
        }), {})


if __name__ == "__main__":
    unittest.main()
