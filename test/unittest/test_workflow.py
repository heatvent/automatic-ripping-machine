import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.ui.workflow import (  # noqa: E402
    job_workflow_status,
    movie_pipeline,
    music_pipeline,
)


class TestMoviePipeline(unittest.TestCase):
    def test_skip_transcode_names_makemkv_and_completed(self):
        result = movie_pipeline({
            "SKIP_TRANSCODE": "true",
            "MAINFEATURE": "true",
            "RIPMETHOD": "mkv",
            "MKV_LANG": "eng",
        })
        self.assertTrue(result["skip_transcode"])
        self.assertIn("MakeMKV", result["sentence"])
        self.assertIn("Completed", result["sentence"])
        self.assertIn("is off", result["sentence"])
        self.assertEqual(result["steps"][-1], "Copy Raw to Completed. HandBrake is off.")

    def test_handbrake_path_when_transcode_on(self):
        result = movie_pipeline({
            "SKIP_TRANSCODE": "false",
            "MAINFEATURE": "true",
            "RIPMETHOD": "mkv",
            "USE_FFMPEG": "false",
        })
        self.assertFalse(result["skip_transcode"])
        self.assertEqual(result["encoder"], "HandBrake")
        self.assertIn("HandBrake", result["sentence"])
        self.assertIn("HandBrake reads Raw and writes Transcode.", result["steps"])

    def test_full_disc_backup_step(self):
        result = movie_pipeline({
            "SKIP_TRANSCODE": "true",
            "RIPMETHOD": "backup",
            "MAINFEATURE": "false",
        })
        self.assertIn("full decrypted disc", result["steps"][2])


class TestMusicPipeline(unittest.TestCase):
    def test_musicbrainz_then_abcde(self):
        result = music_pipeline()
        self.assertIn("MusicBrainz", result["sentence"])
        self.assertIn("abcde", result["sentence"])
        self.assertEqual(len(result["steps"]), 2)


class TestJobWorkflowStatus(unittest.TestCase):
    def test_movie_tools(self):
        job = SimpleNamespace(status="ripping", disctype="bluray", video_type="movie", config=None)
        self.assertEqual(job_workflow_status(job), "MakeMKV")
        job.status = "info"
        self.assertEqual(job_workflow_status(job), "Identify")
        job.status = "transcoding"
        self.assertEqual(job_workflow_status(job), "HandBrake")

    def test_music_tools(self):
        job = SimpleNamespace(status="info", disctype="music", video_type="music", config=None)
        self.assertEqual(job_workflow_status(job), "Identifying")
        job.status = "active"
        self.assertEqual(job_workflow_status(job), "Identifying")
        job.status = "ripping"
        self.assertEqual(job_workflow_status(job), "Ripping")

    def test_finished_labels_unchanged(self):
        job = SimpleNamespace(status="success", disctype="dvd", video_type="movie", config=None)
        self.assertEqual(job_workflow_status(job), "Success")


if __name__ == "__main__":
    unittest.main()
