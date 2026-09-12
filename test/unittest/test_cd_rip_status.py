import datetime
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from arm.ripper.music_brainz import (  # noqa: E402
    check_musicbrainz_data,
    cover_url_for_release,
    cover_url_for_release_group,
    disc_id_string,
    pick_cd_release,
    resolve_cover_url,
    search_releases_for_ui,
)
from arm.ui.jobs.jobs import _search_title  # noqa: E402
from arm.ui.json_api import calc_process_time, format_job_start, parse_abcde_progress  # noqa: E402


SAMPLE_ABCDE_LOG = """
Grabbing entire CD - tracks:  01 02 03 04 05 06 07 08 09 10
Grabbing track 01: Track 1...
Ripping from sector      37 (track  1 [0:00.00])
Encoding track 01 of 10: Track 1...
Grabbing track 02: Track 2...
Ripping from sector   19272 (track  2 [0:00.00])
Encoding track 02 of 10: Track 2...
Tagging track 02 of 10: Track 2...
"""


class TestParseAbcdeProgress(unittest.TestCase):
    def test_uses_encoding_line_not_cdparanoia_sector_range(self):
        current, total, finished = parse_abcde_progress(SAMPLE_ABCDE_LOG.splitlines())
        self.assertEqual(current, 2)
        self.assertEqual(total, 10)
        self.assertFalse(finished)

    def test_finished_line_completes_last_track(self):
        lines = SAMPLE_ABCDE_LOG.splitlines() + ["Finished."]
        current, total, finished = parse_abcde_progress(lines)
        self.assertEqual(current, 10)
        self.assertEqual(total, 10)
        self.assertTrue(finished)

    def test_does_not_treat_failed_cleanup_as_finished(self):
        lines = ["Finished. Not cleaning /tmp/abcde.work"]
        current, total, finished = parse_abcde_progress(lines, known_track_count=10)
        self.assertIsNone(current)
        self.assertEqual(total, 10)
        self.assertFalse(finished)


class TestCalcProcessTime(unittest.TestCase):
    def test_eta_is_not_negative_when_current_exceeds_total(self):
        start = datetime.datetime.now() - datetime.timedelta(seconds=30)
        eta = calc_process_time(start, 2, 1)
        self.assertNotIn("-1 day", eta)
        self.assertNotIn("@", eta)
        self.assertRegex(eta, r"\([^)]+\)$")

    def test_unknown_when_counts_are_invalid(self):
        self.assertEqual(calc_process_time(datetime.datetime.now(), 0, 10), "Unknown")
        self.assertEqual(calc_process_time(None, 1, 10), "Unknown")

    @patch("arm.ui.json_api.cfg")
    def test_format_job_start_uses_date_format(self, mock_cfg):
        mock_cfg.arm_config = {"DATE_FORMAT": "%m-%d-%Y %H:%M:%S"}
        start = datetime.datetime(2026, 9, 11, 22, 58, 0)
        self.assertEqual(format_job_start(start), "09-11-2026 22:58:00")
        self.assertEqual(format_job_start(None), "")


class TestMusicBrainzHelpers(unittest.TestCase):
    def test_cover_url_for_release(self):
        self.assertIsNone(cover_url_for_release("not-an-id"))
        self.assertEqual(
            cover_url_for_release("c096904e-baa6-44d3-8a38-26ca251b5ed1"),
            "https://coverartarchive.org/release/c096904e-baa6-44d3-8a38-26ca251b5ed1/front-500",
        )
        self.assertEqual(
            cover_url_for_release_group("7866f536-a9c7-32eb-8eed-bb49132432fa"),
            "https://coverartarchive.org/release-group/7866f536-a9c7-32eb-8eed-bb49132432fa/front-500",
        )

    @patch("arm.ripper.music_brainz.mb.get_release_group_image_list")
    @patch("arm.ripper.music_brainz.mb.get_image_list")
    def test_resolve_cover_falls_back_to_release_group(self, mock_images, mock_group):
        from musicbrainzngs import WebServiceError
        mock_images.side_effect = WebServiceError("404")
        mock_group.side_effect = WebServiceError("404")
        release = {"release-group": {"id": "7866f536-a9c7-32eb-8eed-bb49132432fa"}}
        url = resolve_cover_url("c096904e-baa6-44d3-8a38-26ca251b5ed1", release)
        self.assertEqual(
            url,
            "https://coverartarchive.org/release-group/7866f536-a9c7-32eb-8eed-bb49132432fa/front-500",
        )

    def test_disc_id_string_from_object(self):
        disc = SimpleNamespace(id="7P833R4jqwuk6rAidSCfeNEZktI-")
        self.assertEqual(disc_id_string(disc), "7P833R4jqwuk6rAidSCfeNEZktI-")

    def test_pick_cd_release_prefers_matching_track_count(self):
        releases = [
            {
                "title": "Wrong",
                "medium-list": [{"format": "CD", "track-list": [{}] * 8}],
            },
            {
                "title": "Piano Man",
                "medium-list": [{"format": "CD", "track-list": [{}] * 10}],
            },
        ]
        release, medium = pick_cd_release(releases, 10)
        self.assertEqual(release["title"], "Piano Man")
        self.assertEqual(len(medium["track-list"]), 10)

    @patch("arm.ripper.music_brainz.resolve_cover_url", return_value=None)
    @patch("arm.ripper.music_brainz.get_cd_art", return_value=False)
    @patch("arm.ripper.music_brainz.process_tracks")
    @patch("arm.ripper.music_brainz.u.database_updater")
    def test_fuzzy_release_list_identifies_album(self, mock_update, _tracks, _art, _cover):
        job = SimpleNamespace(job_id=202, no_of_titles=10)
        disc_info = {
            "release-list": [{
                "id": "mbid-piano-man",
                "title": "Piano Man",
                "date": "1973",
                "artist-credit": [{"artist": {"name": "Billy Joel"}}],
                "cover-art-archive": {"artwork": "false"},
                "medium-list": [{"format": "CD", "track-list": [{"recording": {"title": "Piano Man"}}] * 10}],
            }]
        }
        title = check_musicbrainz_data(job, disc_info)
        self.assertEqual(title, "Billy Joel Piano Man")
        mock_update.assert_called()
        args = mock_update.call_args[0][0]
        self.assertTrue(args["hasnicetitle"])
        self.assertEqual(args["year"], "1973")

    def test_placeholder_title_does_not_search(self):
        self.assertEqual(search_releases_for_ui("not identified")["Search"], [])
        self.assertEqual(search_releases_for_ui("")["Search"], [])

    @patch("arm.ripper.music_brainz.mb.search_releases")
    @patch("arm.ripper.music_brainz.mb.set_useragent")
    def test_search_releases_for_ui_maps_mbid(self, _agent, mock_search):
        mock_search.return_value = {
            "release-list": [{
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "title": "Piano Man",
                "date": "1973-11-09",
                "artist-credit": [{"artist": {"name": "Billy Joel"}}],
            }]
        }
        results = search_releases_for_ui("Piano Man", "1973")
        self.assertEqual(len(results["Search"]), 1)
        hit = results["Search"][0]
        self.assertEqual(hit["Title"], "Billy Joel Piano Man")
        self.assertEqual(hit["Year"], "1973")
        self.assertEqual(hit["Type"], "Music")
        self.assertEqual(hit["imdbID"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        mock_search.assert_called_once()
        called_query = mock_search.call_args.kwargs.get("query", "")
        self.assertIn("Piano Man", called_query)
        self.assertIn("1973", called_query)


class TestSearchTitlePrefill(unittest.TestCase):
    def test_blanks_unidentified(self):
        job = SimpleNamespace(title="not identified")
        self.assertEqual(_search_title(job), "")
        job.title = "Billy Joel Piano Man"
        self.assertEqual(_search_title(job), "Billy Joel Piano Man")

    def test_blanks_none_year(self):
        from arm.ui.jobs.jobs import _search_year
        job = SimpleNamespace(year=None)
        self.assertEqual(_search_year(job), "")
        job.year = "1973"
        self.assertEqual(_search_year(job), "1973")


if __name__ == "__main__":
    unittest.main()
