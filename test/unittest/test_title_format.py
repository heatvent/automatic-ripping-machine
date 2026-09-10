import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.title_format import clean_for_filename, normalize_title_text  # noqa: E402


class TestNormalizeTitleText(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertEqual(normalize_title_text(None), "")
        self.assertEqual(normalize_title_text(""), "")

    def test_curly_apostrophe_and_quotes(self):
        self.assertEqual(normalize_title_text("What’s the Matter Here"), "What's the Matter Here")
        self.assertIn("Crocodile", normalize_title_text("“Crocodile” Dundee"))

    def test_dashes_and_ellipsis(self):
        self.assertEqual(normalize_title_text("Track 1–2"), "Track 1-2")
        self.assertEqual(normalize_title_text("Wait…"), "Wait...")

    def test_nbsp_and_trademark(self):
        self.assertEqual(normalize_title_text("Star Wars\u00a0I™"), "Star Wars I")


class TestCleanForFilename(unittest.TestCase):
    def test_keeps_apostrophe_drops_question_mark(self):
        self.assertEqual(
            clean_for_filename("What's the Matter Here?"),
            "What's the Matter Here",
        )

    def test_keeps_comma_and_spaces(self):
        self.assertEqual(clean_for_filename("10,000 Maniacs"), "10,000 Maniacs")

    def test_colon_becomes_dash(self):
        self.assertEqual(
            clean_for_filename("The Lord of the Rings: The Fellowship of the Ring"),
            "The Lord of the Rings - The Fellowship of the Ring",
        )

    def test_slash_in_band_name(self):
        self.assertEqual(clean_for_filename("AC/DC"), "AC-DC")

    def test_keeps_ampersand(self):
        self.assertEqual(clean_for_filename("Simon & Garfunkel"), "Simon & Garfunkel")

    def test_keeps_accents(self):
        self.assertEqual(clean_for_filename("Amélie"), "Amélie")

    def test_keeps_cjk(self):
        self.assertEqual(clean_for_filename("千と千尋の神隠し"), "千と千尋の神隠し")

    def test_star_in_mash(self):
        self.assertEqual(clean_for_filename("M*A*S*H"), "MASH")

    def test_path_traversal(self):
        self.assertEqual(clean_for_filename("../etc/passwd"), "etc-passwd")

    def test_null_and_control(self):
        self.assertEqual(clean_for_filename("Movie\x00Name\nTwo"), "MovieName Two")

    def test_underscores_become_spaces(self):
        self.assertEqual(clean_for_filename("THE_MATRIX"), "THE MATRIX")

    def test_only_illegal_falls_back(self):
        self.assertEqual(clean_for_filename("???***"), "untitled")

    def test_windows_reserved(self):
        self.assertEqual(clean_for_filename("CON"), "CON disc")
        self.assertEqual(clean_for_filename("nul"), "nul disc")

    def test_trailing_dot_and_space(self):
        self.assertEqual(clean_for_filename("Se7en..."), "Se7en")

    def test_year_suffix_in_fix_style(self):
        self.assertEqual(
            clean_for_filename("Ocean's Eleven (2001)"),
            "Ocean's Eleven (2001)",
        )

    def test_long_title_truncates_on_word(self):
        long = " ".join(["Alpha"] * 80)
        result = clean_for_filename(long, max_length=40)
        self.assertLessEqual(len(result), 40)
        self.assertFalse(result.endswith("Alp"))

    def test_none_uses_fallback(self):
        self.assertEqual(clean_for_filename(None), "untitled")
        self.assertEqual(clean_for_filename("   ", fallback="music_cd"), "music_cd")


if __name__ == "__main__":
    unittest.main()
