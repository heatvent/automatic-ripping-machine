import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.config.makemkv_select import (  # noqa: E402
    SELECTION_DEFAULTS,
    apply_selection_defaults,
    build_selection_string,
    choose_main_feature_track,
    find_similar_movie_titles,
    format_hms,
    format_playlist_warning,
    write_default_selection,
)

DEFAULT_SELECTION = (
    "-sel:all,+sel:video,-sel:mvcvideo,+sel:audio&(eng),-sel:special,"
    "-sel:audio&(eng&havemulti),-sel:audio&(eng&havelossless),"
    "-sel:audio&(eng&core),-sel:audio&(eng&2),+sel:forced&(eng),"
    "+sel:subtitle&(eng),-sel:subtitle&(eng&2)"
)


class TestBuildSelectionString(unittest.TestCase):
    def test_defaults_match_recommended_english_rule(self):
        self.assertEqual(build_selection_string({}), DEFAULT_SELECTION)
        self.assertEqual(build_selection_string(None), DEFAULT_SELECTION)

    def test_spanish_all_audio_keeps_core_when_asked(self):
        selection = build_selection_string({
            "MKV_LANG": "spa",
            "MKV_VIDEO": "all",
            "MKV_AUDIO": "all",
            "MKV_INCLUDE_CORE": True,
            "MKV_EXCLUDE_COMMENTARY": True,
            "MKV_SUBTITLES": "forced",
        })
        self.assertEqual(
            selection,
            "-sel:all,+sel:video,-sel:mvcvideo,+sel:audio&(spa),-sel:special,"
            "+sel:forced&(spa)",
        )
        self.assertNotIn("core", selection)
        self.assertNotIn("havemulti", selection)

    def test_language_tagged_video_and_no_subs(self):
        selection = build_selection_string({
            "MKV_VIDEO": "lang",
            "MKV_AUDIO": "none",
            "MKV_SUBTITLES": "none",
        })
        self.assertEqual(selection, "-sel:all,+sel:video&(eng),-sel:mvcvideo")

    def test_invalid_language_falls_back_to_english(self):
        selection = build_selection_string({"MKV_LANG": "english"})
        self.assertIn("+sel:audio&(eng)", selection)

    def test_include_core_with_best_audio_omits_core_drop(self):
        selection = build_selection_string({"MKV_INCLUDE_CORE": "true"})
        self.assertNotIn("&core)", selection)
        self.assertIn("-sel:audio&(eng&2)", selection)

    def test_keep_commentary_when_disabled(self):
        selection = build_selection_string({"MKV_EXCLUDE_COMMENTARY": "false"})
        self.assertNotIn("-sel:special", selection)


class TestSettingsConfWriter(unittest.TestCase):
    def test_replaces_selection_and_keeps_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.conf")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('app_Key = "T-KEEPME"\n')
                handle.write('app_DefaultSelectionString = "-sel:all"\n')
                handle.write('app_DefaultSelectionString = "-sel:old"\n')
            write_default_selection(path, DEFAULT_SELECTION)
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn('app_Key = "T-KEEPME"', text)
            self.assertEqual(text.count("app_DefaultSelectionString"), 1)
            self.assertIn(f'app_DefaultSelectionString = "{DEFAULT_SELECTION}"', text)

    def test_creates_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "settings.conf")
            write_default_selection(path, "+sel:video")
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(
                    handle.read(),
                    'app_DefaultSelectionString = "+sel:video"\n',
                )


class TestPlaylistDetection(unittest.TestCase):
    def _track(self, number, length):
        return SimpleNamespace(track_number=number, length=length)

    def test_ignores_one_or_two_long_titles(self):
        tracks = [self._track(0, 8500), self._track(1, 8520), self._track(2, 400)]
        self.assertEqual(find_similar_movie_titles(tracks, minlength=600), [])

    def test_flags_many_copies_of_the_feature(self):
        tracks = [self._track(i, 8500 + i) for i in range(8)]
        tracks.append(self._track(99, 420))
        similar = find_similar_movie_titles(tracks, minlength=600)
        self.assertEqual(len(similar), 8)

    def test_does_not_treat_short_extras_as_the_feature(self):
        tracks = [self._track(i, 1200) for i in range(10)]
        tracks.append(self._track(20, 7200))
        self.assertEqual(find_similar_movie_titles(tracks, minlength=600), [])

    def test_warning_lists_title_numbers_and_mainfeature_note(self):
        similar = [self._track(i, 8460) for i in range(5)]
        message = format_playlist_warning(similar, mainfeature=True)
        self.assertIn("5 titles", message)
        self.assertIn("2:21:00", message)
        self.assertIn("0, 1, 2, 3, 4", message)
        self.assertIn("Main Feature Only is on", message)
        self.assertIn("most chapters, then largest, then longest", message)

    def test_format_hms(self):
        self.assertEqual(format_hms(0), "0:00:00")
        self.assertEqual(format_hms(8460), "2:21:00")


class TestChooseMainFeature(unittest.TestCase):
    def _track(self, number, length=7200, chapters=20, filesize=10_000):
        return SimpleNamespace(
            track_number=number, length=length, chapters=chapters, filesize=filesize
        )

    def test_prefers_more_chapters_over_longer_runtime(self):
        decoy = self._track(1, length=8500, chapters=2, filesize=50_000)
        movie = self._track(4, length=8400, chapters=16, filesize=40_000)
        chosen = choose_main_feature_track([decoy, movie])
        self.assertEqual(chosen.track_number, 4)

    def test_filesize_breaks_chapter_ties(self):
        smaller = self._track(2, chapters=12, filesize=8_000)
        larger = self._track(5, chapters=12, filesize=12_000)
        chosen = choose_main_feature_track([smaller, larger])
        self.assertEqual(chosen.track_number, 5)

    def test_length_then_lowest_number_as_later_tiebreakers(self):
        shorter = self._track(3, length=7000, chapters=10, filesize=9_000)
        longer = self._track(1, length=8000, chapters=10, filesize=9_000)
        chosen = choose_main_feature_track([shorter, longer])
        self.assertEqual(chosen.track_number, 1)
        twins = [
            self._track(7, length=8000, chapters=10, filesize=9_000),
            self._track(2, length=8000, chapters=10, filesize=9_000),
        ]
        self.assertEqual(choose_main_feature_track(twins).track_number, 2)

    def test_empty(self):
        self.assertIsNone(choose_main_feature_track([]))
        self.assertIsNone(choose_main_feature_track(None))


class TestSelectionDefaults(unittest.TestCase):
    def test_fills_missing_keys_only(self):
        config = {"MKV_LANG": "ger", "RIPMETHOD": "mkv"}
        apply_selection_defaults(config)
        self.assertEqual(config["MKV_LANG"], "ger")
        self.assertEqual(config["MKV_AUDIO"], "best")
        self.assertEqual(config["RIPMETHOD"], "mkv")

    def test_places_new_keys_before_mkv_args(self):
        config = {
            "RIPMETHOD": "mkv",
            "MKV_ARGS": "",
            "DELRAWFILES": True,
        }
        apply_selection_defaults(config)
        keys = list(config)
        self.assertEqual(keys[:1], ["RIPMETHOD"])
        self.assertEqual(keys[1:7], list(SELECTION_DEFAULTS))
        self.assertEqual(keys[7], "MKV_ARGS")
        self.assertEqual(keys[-1], "DELRAWFILES")


if __name__ == "__main__":
    unittest.main()
