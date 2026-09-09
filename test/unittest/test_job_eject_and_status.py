import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.models.job import (  # noqa: E402
    JOB_STATUS_FINISHED,
    Job,
    JobState,
    classify_disc_from_udev,
    job_has_terminal_status,
    job_holds_drive,
    serialize_model_value,
)
from arm.ripper.utils import format_job_errors, should_wait_for_manual  # noqa: E402


class TestJobTerminalStatus(unittest.TestCase):
    def test_failure_is_terminal(self):
        self.assertTrue(job_has_terminal_status(JobState.FAILURE.value))
        self.assertIn(JobState.FAILURE, JOB_STATUS_FINISHED)

    def test_success_is_terminal(self):
        self.assertTrue(job_has_terminal_status(JobState.SUCCESS.value))

    def test_active_is_not_terminal(self):
        self.assertFalse(job_has_terminal_status(JobState.IDLE.value))

    def test_invalid_status_is_not_terminal(self):
        self.assertFalse(job_has_terminal_status(None))


class TestJobEjectRetry(unittest.TestCase):
    def _job(self, ejected=False):
        return SimpleNamespace(
            ejected=ejected,
            devpath="/dev/sr0",
            drive=MagicMock(),
        )

    @patch("arm.models.job.cfg")
    @patch("arm.models.job.time.sleep")
    def test_eject_retries_until_success(self, _sleep, mock_cfg):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job()
        job.drive.eject.side_effect = ["Device or resource busy", None]

        Job.eject(job, retries=5, delay=0)

        self.assertTrue(job.ejected)
        self.assertEqual(job.drive.eject.call_count, 2)

    @patch("arm.models.job.cfg")
    @patch("arm.models.job.time.sleep")
    def test_eject_leaves_flag_clear_when_all_retries_fail(self, _sleep, mock_cfg):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job()
        job.drive.eject.return_value = "Device or resource busy"

        Job.eject(job, retries=3, delay=0)

        self.assertFalse(job.ejected)
        self.assertEqual(job.drive.eject.call_count, 3)

    @patch("arm.models.job.cfg")
    def test_eject_skips_when_already_ejected(self, mock_cfg):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job(ejected=True)

        Job.eject(job)

        job.drive.eject.assert_not_called()

    @patch("arm.models.job.cfg")
    def test_auto_eject_disabled_releases_drive(self, mock_cfg):
        mock_cfg.arm_config = {"AUTO_EJECT": False}
        job = self._job()

        Job.eject(job)

        job.drive.eject.assert_not_called()
        job.drive.release_current_job.assert_called_once()
        self.assertFalse(job.ejected)


class TestJobHoldsDrive(unittest.TestCase):
    def test_ripping_holds_drive(self):
        job = SimpleNamespace(status=JobState.VIDEO_RIPPING.value, ejected=False)
        self.assertTrue(job_holds_drive(job))

    def test_manual_wait_holds_drive(self):
        job = SimpleNamespace(status=JobState.MANUAL_WAIT_STARTED.value, ejected=False)
        self.assertTrue(job_holds_drive(job))

    def test_transcoding_releases_drive(self):
        job = SimpleNamespace(status=JobState.TRANSCODE_ACTIVE.value, ejected=False)
        self.assertFalse(job_holds_drive(job))

    def test_waiting_transcode_releases_drive(self):
        job = SimpleNamespace(status=JobState.TRANSCODE_WAITING.value, ejected=False)
        self.assertFalse(job_holds_drive(job))

    def test_ejected_releases_drive(self):
        job = SimpleNamespace(status=JobState.VIDEO_RIPPING.value, ejected=True)
        self.assertFalse(job_holds_drive(job))

    def test_manual_wait_is_not_makemkv_wait(self):
        self.assertNotEqual(JobState.MANUAL_WAIT_STARTED.value, JobState.VIDEO_WAITING.value)


class TestFormatJobErrors(unittest.TestCase):
    def test_string_is_not_split_into_letters(self):
        self.assertEqual(format_job_errors("MakeMKV failed"), "MakeMKV failed")

    def test_list_is_joined(self):
        self.assertEqual(format_job_errors(["Title 1", "Title 2"]), "Title 1, Title 2")

    def test_empty_is_blank(self):
        self.assertEqual(format_job_errors(None), "")
        self.assertEqual(format_job_errors(""), "")


class TestShouldWaitForManual(unittest.TestCase):
    def test_auto_drive_skips_wait(self):
        job = SimpleNamespace(
            config=SimpleNamespace(MANUAL_WAIT=True, MANUAL_WAIT_TIME=60),
            manual_mode=False,
        )
        self.assertFalse(should_wait_for_manual(job))

    def test_manual_drive_waits(self):
        job = SimpleNamespace(
            config=SimpleNamespace(MANUAL_WAIT=True, MANUAL_WAIT_TIME=60),
            manual_mode=True,
        )
        self.assertTrue(should_wait_for_manual(job))

    def test_wait_disabled_skips(self):
        job = SimpleNamespace(
            config=SimpleNamespace(MANUAL_WAIT=False, MANUAL_WAIT_TIME=60),
            manual_mode=True,
        )
        self.assertFalse(should_wait_for_manual(job))


class TestClassifyDiscFromUdev(unittest.TestCase):
    def test_data_cdr_with_iso_is_data_not_music(self):
        disc_type, label = classify_disc_from_udev({
            "ID_CDROM_MEDIA_CD_R": "1",
            "ID_FS_TYPE": "iso9660",
            "ID_FS_LABEL": "INSTALLER",
        })
        self.assertEqual(disc_type, "data")
        self.assertEqual(label, "INSTALLER")

    def test_audio_cdr_without_fs_is_music(self):
        disc_type, _label = classify_disc_from_udev({
            "ID_CDROM_MEDIA_CD_R": "1",
        })
        self.assertEqual(disc_type, "music")

    def test_audio_tracks_win_over_filesystem(self):
        disc_type, _label = classify_disc_from_udev({
            "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO": "12",
            "ID_FS_TYPE": "iso9660",
        })
        self.assertEqual(disc_type, "music")

    def test_dvd_wins_over_cd_flags(self):
        disc_type, _label = classify_disc_from_udev({
            "ID_CDROM_MEDIA_DVD": "1",
            "ID_CDROM_MEDIA_CD": "1",
        })
        self.assertEqual(disc_type, "dvd")


class TestSerializeModelValue(unittest.TestCase):
    def test_none_stays_none(self):
        self.assertIsNone(serialize_model_value(None))

    def test_other_values_stringify(self):
        self.assertEqual(serialize_model_value(12), "12")


class TestJobEjectWithoutDrive(unittest.TestCase):
    @patch("arm.models.job.subprocess.run")
    @patch("arm.models.job.cfg")
    def test_ejects_devpath_when_drive_row_missing(self, mock_cfg, mock_run):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = SimpleNamespace(ejected=False, devpath="/dev/sr0", drive=None)

        Job.eject(job)

        mock_run.assert_called_once()
        self.assertTrue(job.ejected)


if __name__ == "__main__":
    unittest.main()
