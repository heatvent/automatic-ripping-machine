import os
import sys
import time
import unittest
from subprocess import CalledProcessError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from arm.models.job import (  # noqa: E402
    JOB_STATUS_FINISHED,
    Job,
    JobState,
    audio_track_count_from_udev,
    classify_disc_from_udev,
    job_has_terminal_status,
    job_holds_drive,
    serialize_model_value,
    status_label,
)
from arm.models.system_drives import SystemDrives, tray_command_lists  # noqa: E402
from arm.ripper.utils import (  # noqa: E402
    _is_abcde_workdir,
    abcde_rip_command,
    clean_for_filename,
    clear_abcde_work_dirs,
    format_job_errors,
    promote_album_cover,
    should_wait_for_manual,
    stop_stray_abcde,
    track_meets_minlength,
)


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


class TestStatusLabel(unittest.TestCase):
    def test_known_job_statuses(self):
        self.assertEqual(status_label("success"), "Success")
        self.assertEqual(status_label("fail"), "Failed")
        self.assertEqual(status_label("waiting_manual"), "Waiting for Title")
        self.assertEqual(status_label("active"), "Active")
        self.assertEqual(status_label("ripping"), "Ripping")
        self.assertEqual(status_label("waiting"), "Waiting")
        self.assertEqual(status_label("info"), "Reading Disc")
        self.assertEqual(status_label("transcoding"), "Transcoding")
        self.assertEqual(status_label("waiting_transcode"), "Waiting to Transcode")
        self.assertEqual(status_label("waiting_playlist"), "Pick Playlist")

    def test_sysinfo_yes_no(self):
        self.assertEqual(status_label("yes"), "Yes")
        self.assertEqual(status_label("no"), "No")

    def test_unknown_status_title_cases(self):
        self.assertEqual(status_label("custom_step"), "Custom Step")
        self.assertEqual(status_label(None), "")

    def test_music_ripping_is_ripping_not_abcde(self):
        job = SimpleNamespace(status="ripping", disctype="music", video_type="music", config=None)
        self.assertEqual(status_label("ripping", job=job), "Ripping")

    def test_music_info_is_identifying(self):
        job = SimpleNamespace(status="info", disctype="music", video_type="music", config=None)
        self.assertEqual(status_label("info", job=job), "Identifying")


class TestJobEjectRetry(unittest.TestCase):
    def _job(self, ejected=False):
        return SimpleNamespace(
            ejected=ejected,
            devpath="/dev/sr0",
            drive=MagicMock(),
        )

    @patch("arm.models.job.persist_job_session")
    @patch("arm.models.job.cfg")
    @patch("arm.models.job.time.sleep")
    def test_eject_retries_until_success(self, _sleep, mock_cfg, mock_persist):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job()
        job.drive.eject.side_effect = ["Device or resource busy", None]

        Job.eject(job, retries=5, delay=0)

        self.assertTrue(job.ejected)
        self.assertEqual(job.drive.eject.call_count, 2)
        mock_persist.assert_called_once()

    @patch("arm.models.job.persist_job_session")
    @patch("arm.models.job.cfg")
    @patch("arm.models.job.time.sleep")
    def test_eject_leaves_flag_clear_when_all_retries_fail(self, _sleep, mock_cfg, mock_persist):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job()
        job.drive.eject.return_value = "Device or resource busy"

        Job.eject(job, retries=3, delay=0)

        self.assertFalse(job.ejected)
        self.assertEqual(job.drive.eject.call_count, 3)
        mock_persist.assert_called_once()

    @patch("arm.models.job.persist_job_session")
    @patch("arm.models.job.cfg")
    def test_eject_skips_when_already_ejected(self, mock_cfg, mock_persist):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = self._job(ejected=True)

        Job.eject(job)

        job.drive.eject.assert_not_called()
        mock_persist.assert_not_called()

    @patch("arm.models.job.persist_job_session")
    @patch("arm.models.job.cfg")
    def test_auto_eject_disabled_releases_drive(self, mock_cfg, mock_persist):
        mock_cfg.arm_config = {"AUTO_EJECT": False}
        job = self._job()

        Job.eject(job)

        job.drive.eject.assert_not_called()
        job.drive.release_current_job.assert_called_once()
        self.assertTrue(job.ejected)
        mock_persist.assert_called_once()
        self.assertFalse(job_holds_drive(job))


class TestJobHoldsDrive(unittest.TestCase):
    def test_ripping_holds_drive(self):
        job = SimpleNamespace(status=JobState.VIDEO_RIPPING.value, ejected=False)
        self.assertTrue(job_holds_drive(job))

    def test_manual_wait_holds_drive(self):
        job = SimpleNamespace(status=JobState.MANUAL_WAIT_STARTED.value, ejected=False)
        self.assertTrue(job_holds_drive(job))

    def test_playlist_wait_holds_drive(self):
        job = SimpleNamespace(status=JobState.PLAYLIST_WAIT.value, ejected=False)
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

    def test_audio_track_count_from_udev(self):
        self.assertEqual(audio_track_count_from_udev({
            "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO": "10",
        }), 10)
        self.assertIsNone(audio_track_count_from_udev({}))


class TestSerializeModelValue(unittest.TestCase):
    def test_none_stays_none(self):
        self.assertIsNone(serialize_model_value(None))

    def test_other_values_stringify(self):
        self.assertEqual(serialize_model_value(12), "12")


class TestJobEjectWithoutDrive(unittest.TestCase):
    @patch("arm.models.job.persist_job_session")
    @patch("arm.models.job.subprocess.run")
    @patch("arm.models.job.cfg")
    def test_ejects_devpath_when_drive_row_missing(self, mock_cfg, mock_run, mock_persist):
        mock_cfg.arm_config = {"AUTO_EJECT": True}
        job = SimpleNamespace(ejected=False, devpath="/dev/sr0", drive=None)

        Job.eject(job)

        mock_run.assert_called_once()
        self.assertTrue(job.ejected)
        mock_persist.assert_called_once()


class TestTrayCommandLists(unittest.TestCase):
    def test_open_tries_scsi_then_plain(self):
        cmds = tray_command_lists("/dev/sr0", "eject")
        self.assertIn("--scsi", cmds[0])
        self.assertNotIn("--scsi", cmds[1])
        self.assertEqual(cmds[2], ["eject", "--verbose", "/dev/sr0"])

    def test_close_uses_trayclose(self):
        cmds = tray_command_lists("/dev/sr0", "close")
        self.assertIn("--trayclose", cmds[0])
        self.assertNotIn("--traytoggle", cmds[0])


class TestDriveEjectFallback(unittest.TestCase):
    def _drive(self):
        return SimpleNamespace(
            mount="/dev/sr0",
            release_current_job=MagicMock(),
        )

    @patch("arm.models.system_drives.arm_subprocess")
    def test_open_falls_back_when_scsi_fails(self, mock_run):
        fail = CalledProcessError(1, ["eject"])
        fail.output = "Device or resource busy"

        def side_effect(cmd, check=False):
            if cmd[0] == "umount":
                return None
            if "--scsi" in cmd:
                raise fail
            return "ok"

        mock_run.side_effect = side_effect
        drive = self._drive()
        self.assertIsNone(SystemDrives.eject(drive, method="eject"))
        drive.release_current_job.assert_called_once()

    @patch("arm.models.system_drives.arm_subprocess")
    def test_close_does_not_release_job(self, mock_run):
        mock_run.return_value = "ok"
        drive = self._drive()
        self.assertIsNone(SystemDrives.eject(drive, method="close"))
        drive.release_current_job.assert_not_called()


class TestTrackMeetsMinlength(unittest.TestCase):
    def test_abcde_tracks_always_rip(self):
        job = SimpleNamespace(config=None)
        self.assertTrue(track_meets_minlength(job, 30, "ABCDE"))

    def test_uses_job_config_when_present(self):
        job = SimpleNamespace(config=SimpleNamespace(MINLENGTH="600"))
        self.assertFalse(track_meets_minlength(job, 291, "MakeMKV"))
        self.assertTrue(track_meets_minlength(job, 601, "MakeMKV"))

    def test_missing_config_does_not_raise(self):
        job = SimpleNamespace(config=None)
        self.assertIsInstance(track_meets_minlength(job, 120, "HandBrake"), bool)


class TestCleanForFilename(unittest.TestCase):
    def test_strips_question_mark_without_trailing_hyphen(self):
        self.assertEqual(
            clean_for_filename("What's the Matter Here?"),
            "What's the Matter Here",
        )

    def test_keeps_comma_in_artist(self):
        self.assertEqual(clean_for_filename("10,000 Maniacs"), "10,000 Maniacs")


class TestAbcdeRipCommand(unittest.TestCase):
    def test_forces_noninteractive(self):
        cmd = abcde_rip_command("/dev/sr0", "album.log", "/home/arm/logs")
        self.assertIn("abcde -N -d \"/dev/sr0\"", cmd)
        self.assertIn("/home/arm/logs/album.log", cmd)


class TestAbcdeWorkDirs(unittest.TestCase):
    def test_recognizes_cddb_session_folder(self):
        self.assertTrue(_is_abcde_workdir("/home/arm/abcde.a00a3c0a"))
        self.assertFalse(_is_abcde_workdir("/home/arm/abcde.conf"))
        self.assertFalse(_is_abcde_workdir("/home/arm/music"))

    def test_clear_skips_in_use_and_removes_stale(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            stale = os.path.join(tmp, "abcde.a00a3c0a")
            busy = os.path.join(tmp, "abcde.deadbeef")
            os.makedirs(stale)
            os.makedirs(busy)

            def _busy(path):
                return os.path.basename(str(path)) == "abcde.deadbeef"

            with patch("arm.ripper.utils.abcde_workdir_in_use", side_effect=_busy):
                removed = clear_abcde_work_dirs(tmp)
            self.assertEqual(removed, [stale])
            self.assertFalse(os.path.isdir(stale))
            self.assertTrue(os.path.isdir(busy))

    @patch("arm.ripper.utils.psutil.process_iter")
    def test_stop_stray_kills_orphaned_abcde_on_same_drive(self, mock_iter):
        stray = MagicMock()
        stray.info = {
            "pid": 71666,
            "name": "abcde",
            "cmdline": ["/bin/bash", "/usr/bin/abcde", "-N", "-d", "/dev/sr0"],
        }
        other = MagicMock()
        other.info = {
            "pid": 99,
            "name": "abcde",
            "cmdline": ["/bin/bash", "/usr/bin/abcde", "-N", "-d", "/dev/sr1"],
        }
        mock_iter.return_value = [stray, other]
        killed = stop_stray_abcde("/dev/sr0")
        self.assertEqual(killed, 1)
        stray.kill.assert_called_once()
        other.kill.assert_not_called()


class TestPromoteAlbumCover(unittest.TestCase):
    def test_copies_cover_next_to_tracks(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            backup = os.path.join(tmp, "Artist", "Album", "albumart_backup")
            os.makedirs(backup)
            src = os.path.join(backup, "cover.jpg")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("art")
            copied = promote_album_cover(tmp, max_age_seconds=3600)
            dest = os.path.join(tmp, "Artist", "Album", "cover.jpg")
            self.assertEqual(copied, 1)
            self.assertTrue(os.path.isfile(dest))


class TestLogCleanup(unittest.TestCase):
    def test_keeps_attached_job_logs_and_arm_log(self):
        import tempfile
        from arm.ripper.logger import clean_up_logs, safe_log_basename

        self.assertEqual(
            safe_log_basename("10,000 Maniacs In My Tribe"),
            "10,000 Maniacs In My Tribe",
        )
        with tempfile.TemporaryDirectory() as tmp:
            keep = os.path.join(tmp, "keep-me.log")
            drop = os.path.join(tmp, "orphan.log")
            arm = os.path.join(tmp, "arm.log")
            old = time.time() - 10 * 86400
            for path in (keep, drop, arm):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("x")
                os.utime(path, (old, old))
            clean_up_logs(tmp, 1, keep_names=["keep-me.log"])
            self.assertTrue(os.path.isfile(keep))
            self.assertTrue(os.path.isfile(arm))
            self.assertFalse(os.path.isfile(drop))


class TestUmountIdle(unittest.TestCase):
    def test_not_mounted_is_expected(self):
        from arm.ripper.ProcessHandler import _is_expected_umount_idle
        self.assertTrue(
            _is_expected_umount_idle(
                ["umount", "/dev/sr0"],
                "umount: /dev/sr0: not mounted.",
            )
        )
        self.assertFalse(_is_expected_umount_idle(["mount", "/dev/sr0"], "not mounted"))


class TestIdentifySkipsMusicMount(unittest.TestCase):
    @patch("arm.ripper.identify.check_mount")
    def test_music_does_not_mount(self, mock_mount):
        from arm.ripper import identify
        identify.identify(SimpleNamespace(disctype="music"))
        mock_mount.assert_not_called()


class TestMakeMkvPaths(unittest.TestCase):
    def test_progress_log_is_not_shell_quoted(self):
        from arm.ripper.makemkv import progress_log
        job = SimpleNamespace(job_id=12, config=SimpleNamespace(LOGPATH="/home/arm/logs"))
        path = progress_log(job)
        self.assertEqual(path, "/home/arm/logs/progress/12.log")
        self.assertFalse(path.startswith("'"))
        self.assertFalse(path.endswith("'"))

    def test_setup_rawpath_creates_missing_folder(self):
        import tempfile
        from arm.ripper.makemkv import setup_rawpath
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "Movie")
            job = SimpleNamespace(config=SimpleNamespace(RAW_PATH=tmp), title="Movie", stage="1")
            self.assertEqual(setup_rawpath(job, dest), dest)
            self.assertTrue(os.path.isdir(dest))

    def test_setup_rawpath_raises_when_create_fails(self):
        from arm.ripper.makemkv import setup_rawpath
        job = SimpleNamespace(config=SimpleNamespace(RAW_PATH="/nope"), title="Movie", stage="1")
        with patch("os.path.exists", return_value=False):
            with patch("arm.config.path_health.ensure_writable_dir", side_effect=OSError("denied")):
                with self.assertRaises(OSError):
                    setup_rawpath(job, "/nope/Movie")


if __name__ == "__main__":
    unittest.main()
