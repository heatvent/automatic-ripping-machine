import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.ui.jobs.jobs import _album_facts, format_track_length  # noqa: E402


class TestFormatTrackLength(unittest.TestCase):
    def test_music_milliseconds(self):
        self.assertEqual(format_track_length(291000, True), "4:51")
        self.assertEqual(format_track_length(206493, True), "3:26")

    def test_movie_seconds(self):
        self.assertEqual(format_track_length(7959, False), "2:12:39")
        self.assertEqual(format_track_length(133, False), "2:13")

    def test_empty(self):
        self.assertEqual(format_track_length(None, False), "0:00")
        self.assertEqual(format_track_length("nope", True), "—")


class TestAlbumFacts(unittest.TestCase):
    def test_includes_barcode_and_catalog(self):
        job = SimpleNamespace(year="1987", no_of_titles=12, label="10,000 Maniacs In My Tribe", crc_id="x")
        facts = _album_facts(job, {
            "artist": "10,000 Maniacs",
            "album": "In My Tribe",
            "year": "1987",
            "label": "Elektra",
            "barcode": "075596073820",
            "catalog": "60738-2, 9 60738-2",
            "country": "US",
            "primary_type": "Album",
            "mbid": "371475ce-191b-46a1-99fe-df538fc56d75",
            "url": "https://musicbrainz.org/release/371475ce-191b-46a1-99fe-df538fc56d75",
        })
        by_label = {item["label"]: item["value"] for item in facts}
        self.assertEqual(by_label["Barcode"], "075596073820")
        self.assertEqual(by_label["Catalog #"], "60738-2, 9 60738-2")
