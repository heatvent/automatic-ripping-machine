import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.config.config_utils import ENUM_SETTING_CHOICES  # noqa: E402
from arm.ui.settings.abcde_utils import (  # noqa: E402
    abcde_groups_for_ui,
    apply_abcde_updates,
    parse_abcde_values,
    validate_abcde_form,
)
from arm.ui.settings.setting_meta import (  # noqa: E402
    format_setting_help,
    grouped_setting_keys,
    page_setting_groups,
    setting_label,
    strip_comment_hashes,
    validate_ripper_form,
    validate_ui_form,
)


class TestCommentsJson(unittest.TestCase):
    def test_setting_comments_keep_hash_prefixes(self):
        import json
        comments_path = os.path.join(
            os.path.dirname(__file__), "../../arm/ui/comments.json"
        )
        with open(os.path.abspath(comments_path), encoding="utf-8") as handle:
            comments = json.load(handle)
        self.assertIn("ARM_CFG_GROUPS", comments)
        for key, value in comments.items():
            if key == "ARM_CFG_GROUPS":
                continue
            self.assertIsInstance(value, str, key)
            for line in value.splitlines():
                if line.strip() == "":
                    continue
                self.assertTrue(
                    line.lstrip().startswith("#"),
                    f"{key} comment line must stay a yaml comment: {line!r}",
                )


class TestSettingMeta(unittest.TestCase):
    def test_friendly_label_then_key(self):
        self.assertEqual(setting_label("ARM_NAME"), "Machine Name")
        self.assertEqual(setting_label("UNKNOWN_FLAG"), "Unknown Flag")

    def test_format_setting_help_strips_hashes_and_adds_key(self):
        help_text = format_setting_help(
            "MINLENGTH",
            "# Ignore titles shorter than this length.\n# Unit: seconds. Default: 600.",
        )
        self.assertTrue(help_text.startswith("Ignore titles shorter"))
        self.assertTrue(help_text.endswith("YAML key: <code>MINLENGTH</code>"))
        self.assertIn("Unit: seconds", help_text)
        self.assertNotIn("# Ignore", help_text)
        self.assertNotIn("# Unit", help_text)

    def test_format_setting_help_keeps_hash_in_body(self):
        help_text = format_setting_help("PREVENT_99", "# Workaround for DVD Track #99 DRM.")
        self.assertIn("Track #99", help_text)
        self.assertNotIn("# Workaround", help_text)

    def test_format_setting_help_empty_comment(self):
        help_text = format_setting_help("FOO", "")
        self.assertTrue(help_text.startswith("No description is available"))
        self.assertTrue(help_text.endswith("YAML key: <code>FOO</code>"))

    def test_strip_comment_hashes(self):
        self.assertEqual(
            strip_comment_hashes("# First line.\n# Second line."),
            "First line.\nSecond line.",
        )

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
        self.assertIn("Identity", titles)
        self.assertIn("Rip with MakeMKV", titles)
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

    def test_general_groups_split_identity_and_logging(self):
        settings = {
            "ARM_NAME": "lab",
            "DISABLE_LOGIN": "false",
            "DATE_FORMAT": "%Y",
            "ARM_CHILDREN": "",
            "LOGLEVEL": "INFO",
            "LOGLIFE": "1",
            "WEBSERVER_PORT": "8080",
        }
        pages = page_setting_groups(settings)
        titles = [title for _, title, _ in pages["general"]]
        self.assertEqual(titles[:3], ["Identity", "Logging", "Web Server"])
        by_id = {group_id: keys for group_id, _, keys in pages["general"]}
        self.assertEqual(by_id["identity"], [
            "ARM_NAME", "DISABLE_LOGIN", "DATE_FORMAT", "ARM_CHILDREN",
        ])
        self.assertEqual(by_id["logging"], ["LOGLEVEL", "LOGLIFE"])

    def test_notify_groups_split_services(self):
        settings = {
            "NOTIFY_RIP": "true",
            "NOTIFY_TRANSCODE": "true",
            "NOTIFY_JOBID": "false",
            "IFTTT_KEY": "x",
            "IFTTT_EVENT": "arm_event",
            "PO_USER_KEY": "u",
            "PO_APP_KEY": "a",
            "PB_KEY": "p",
            "BASH_SCRIPT": "",
            "JSON_URL": "",
            "APPRISE": "/etc/arm/config/apprise.yaml",
            "EMBY_SERVER": "emby",
        }
        pages = page_setting_groups(settings)
        titles = [title for _, title, _ in pages["notify"]]
        self.assertEqual(
            titles,
            [
                "When to Notify",
                "IFTTT",
                "Pushover",
                "Pushbullet",
                "Script and Webhook",
                "Emby",
                "Apprise File",
            ],
        )
        by_id = {group_id: keys for group_id, _, keys in pages["notify"]}
        self.assertEqual(by_id["ifttt"], ["IFTTT_KEY", "IFTTT_EVENT"])
        self.assertEqual(by_id["pushover"], ["PO_USER_KEY", "PO_APP_KEY"])
        self.assertEqual(by_id["apprise"], ["APPRISE"])
        self.assertNotIn("APPRISE", by_id["when"])

    def test_ripper_groups_and_cd_title_source(self):
        settings = {
            "GET_VIDEO_TITLE": "true",
            "MINLENGTH": "600",
            "MANUAL_WAIT": "true",
            "RIPMETHOD": "mkv",
            "SKIP_TRANSCODE": "true",
            "USE_FFMPEG": "false",
            "MAX_CONCURRENT_TRANSCODES": "1",
            "HB_PRESET_DVD": "HQ",
            "GET_AUDIO_TITLE": "musicbrainz",
            "CUSTOM_EXTRA": "1",
        }
        pages = page_setting_groups(settings)
        titles = [title for _, title, _ in pages["ripper"]]
        self.assertIn("Identify", titles)
        self.assertIn("Tracks to Rip", titles)
        self.assertIn("Transcode", titles)
        self.assertIn("HandBrake", titles)
        self.assertIn("FFmpeg", titles)
        self.assertIn("Job Flow", titles)
        by_id = {group_id: keys for group_id, _, keys in pages["ripper"]}
        self.assertEqual(by_id["transcode"], ["SKIP_TRANSCODE", "MAX_CONCURRENT_TRANSCODES"])
        self.assertIn("HB_PRESET_DVD", by_id["handbrake"])
        self.assertNotIn("USE_FFMPEG", by_id["transcode"])
        self.assertEqual(by_id["ffmpeg"][0], "USE_FFMPEG")
        ripper_keys = [key for _, _, keys in pages["ripper"] for key in keys]
        self.assertNotIn("GET_AUDIO_TITLE", ripper_keys)
        self.assertIn("CUSTOM_EXTRA", ripper_keys)

    def test_abcde_config_file_is_not_on_general_or_ripper(self):
        settings = {
            "ARM_NAME": "lab",
            "LOGPATH": "/logs",
            "DBFILE": "/db",
            "INSTALLPATH": "/opt/arm",
            "ABCDE_CONFIG_FILE": "/etc/arm/config/abcde.conf",
            "RIPMETHOD": "mkv",
        }
        pages = page_setting_groups(settings)
        general_keys = [key for _, _, keys in pages["general"] for key in keys]
        ripper_keys = [key for _, _, keys in pages["ripper"] for key in keys]
        self.assertNotIn("ABCDE_CONFIG_FILE", general_keys)
        self.assertNotIn("ABCDE_CONFIG_FILE", ripper_keys)
        self.assertIn("INSTALLPATH", general_keys)

    def test_makemkv_selection_keys_group_and_validate(self):
        settings = {
            "RIPMETHOD": "mkv",
            "MKV_LANG": "eng",
            "MKV_VIDEO": "all",
            "MKV_AUDIO": "best",
            "MKV_INCLUDE_CORE": "false",
            "MKV_EXCLUDE_COMMENTARY": "true",
            "MKV_SUBTITLES": "one_plus_forced",
            "MKV_ARGS": "",
        }
        pages = page_setting_groups(settings)
        ripper_keys = [key for _, _, keys in pages["ripper"] for key in keys]
        for key in settings:
            self.assertIn(key, ripper_keys)
        self.assertEqual(setting_label("MKV_LANG"), "Language")
        self.assertEqual(setting_label("MKV_INCLUDE_CORE"), "Include HD Core")
        self.assertEqual(setting_label("MAINFEATURE"), "Main Title Only")
        pages_main = page_setting_groups({"MAINFEATURE": "true", "HB_PRESET_DVD": "HQ"})
        ripper_keys_main = [key for _, _, keys in pages_main["ripper"] for key in keys]
        self.assertIn("MAINFEATURE", ripper_keys_main)
        errors = validate_ripper_form({"MKV_LANG": "xx", "MKV_AUDIO": "best"})
        self.assertIn("MKV_LANG", errors)

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
            "MKV_LANG": "eng",
            "MKV_VIDEO": "all",
            "MKV_AUDIO": "best",
            "MKV_SUBTITLES": "one_plus_forced",
            "MKV_INCLUDE_CORE": "false",
            "MKV_EXCLUDE_COMMENTARY": "true",
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

    def test_abcde_groups_for_ui(self):
        groups = abcde_groups_for_ui(self.SAMPLE)
        titles = [group["title"] for group in groups]
        self.assertEqual(titles, ["CD Jobs", "Output", "Ripping"])
        lookup_keys = [field["key"] for field in groups[0]["fields"]]
        self.assertEqual(lookup_keys, ["CDDBMETHOD"])
        output = next(field for field in groups[1]["fields"] if field["key"] == "OUTPUTTYPE")
        choice_values = [opt for opt, _label in output["choices"]]
        self.assertIn("flac", choice_values)
        self.assertIn("mp3", choice_values)
        self.assertIn("flac,mp3", choice_values)


class TestServerUtilDiskSpace(unittest.TestCase):
    def test_disconnected_share_does_not_raise(self):
        from unittest.mock import patch
        from arm.ui.settings.ServerUtil import ServerUtil

        util = ServerUtil.__new__(ServerUtil)
        error = OSError(107, "Transport endpoint is not connected")
        error.filename = "/mnt/hgfs/completed"
        with patch("arm.ui.settings.ServerUtil.psutil.disk_usage", side_effect=error), \
             patch("arm.ui.settings.ServerUtil.flash") as mock_flash:
            free, percent = util.get_disk_space("/mnt/hgfs/completed")
        self.assertEqual(free, 0)
        self.assertEqual(percent, 0)
        mock_flash.assert_called_once()
        self.assertIn("/mnt/hgfs/completed", mock_flash.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
