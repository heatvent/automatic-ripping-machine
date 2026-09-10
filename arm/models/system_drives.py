"""Database Model for Drive Information on the System
"""

import enum
import fcntl
import logging
import os
import re
from subprocess import CalledProcessError

from arm.ripper.ProcessHandler import arm_subprocess
from arm.ui import db


def tray_command_lists(mount, method):
    """Return ``eject`` command variants, most specific first."""
    if not mount:
        return []
    if method == "close":
        return [
            ["eject", "--verbose", "--trayclose", "--cdrom", "--scsi", mount],
            ["eject", "--verbose", "--trayclose", "--cdrom", mount],
            ["eject", "--verbose", "--trayclose", mount],
            ["eject", "--verbose", "--traytoggle", "--cdrom", "--scsi", mount],
        ]
    if method == "toggle":
        return [
            ["eject", "--verbose", "--traytoggle", "--cdrom", "--scsi", mount],
            ["eject", "--verbose", "--traytoggle", mount],
            ["eject", "--verbose", "--cdrom", "--scsi", mount],
        ]
    return [
        ["eject", "--verbose", "--cdrom", "--scsi", mount],
        ["eject", "--verbose", "--cdrom", mount],
        ["eject", "--verbose", mount],
        ["eject", "--verbose", "--traytoggle", "--cdrom", "--scsi", mount],
    ]


class CDS(enum.Enum):
    """CD Status

    ioctl defines may (not very likely) change.
    see https://github.com/torvalds/linux/blob/master/include/uapi/linux/cdrom.h
    """
    NO_INFO = 0
    """CDS_NO_INFO"""
    NO_DISC = 1
    """CDS_NO_INFO"""
    TRAY_OPEN = 2
    """CDS_TRAY_OPEN"""
    DRIVE_NOT_READY = 3
    """CDS_DRIVE_NOT_READY"""
    DISC_OK = 4
    """CDS_DISC_OK"""
    ERROR = None


def _tray_status(devpath, logger=logging):
    """
    Get the Status of the CDROM Drive.

    Note: This should be considered as internal function to the
          SystemDrives class and should not be called directly.

    Parameters
    ----------
    devpath: str
        path to cdrom

    Returns
    -------
    int or None
        Returns `None` if a (known) error occured and `int` on
        success.  The values are defined in the linux kernel and
        referenced here:

        - `CDS_NO_INFO`
        - `CDS_NO_DISC`
        - `CDS_TRAY_OPEN`
        - `CDS_DRIVE_NOT_READY`
        - `CDS_DISC_OK`

        ioctl defines may (not very likely) change. See
        [linux/cdrom.h](https://github.com/torvalds/linux/blob/master/include/uapi/linux/cdrom.h)
        for specifics.
    """
    try:
        disk_check = os.open(devpath, os.O_RDONLY | os.O_NONBLOCK)
    except FileNotFoundError as err:
        logger.critical(f"Possibly Stale Mount Points detected: '{err}'")
        return None  # should be cleared in `ui.settings.DriveUtils.drives_update`
    except TypeError as err:
        logger.critical(f"Possible Database Inconsistency for {devpath}: '{err:s}'")
        return None  # inconsistency in SystemDrives.mount
    except OSError as err:
        # Sometimes ARM will log errors opening hard drives. this check should stop it
        if re.search(r'hd[a-j]|sd[a-j]|loop\d|nvme\d', devpath):
            logger.critical(f"The device '{devpath}' is not an optical drive")
            return None  # inconsistency in SystemDrives.mount
        # We queried a mount path that is not present any more.
        if 'No such device or address' in str(err):
            logger.critical(f"Drive Mount Path does not exist: '{err}'")
            return None  # drive mount path missing. Should get cleared by `ui.settings.DriveUtils.drives_update`
        raise err
    try:
        return fcntl.ioctl(disk_check, 0x5326, 0)
    except OSError as err:
        logger.warning(f"Failed to check status for '{devpath}': {err:s}")
        return None
    finally:
        os.close(disk_check)


class SystemDrives(db.Model):  # pylint: disable=too-many-instance-attributes
    """
    Class to hold the system cd/dvd/Blu-ray drive information
    """
    drive_id = db.Column(db.Integer, index=True, primary_key=True)

    # static information:
    serial_id = db.Column(db.String(100))  # maker+serial (static identification)
    maker = db.Column(db.String(25))
    model = db.Column(db.String(50))
    serial = db.Column(db.String(25))
    connection = db.Column(db.String(5))
    read_cd = db.Column(db.Boolean)
    read_dvd = db.Column(db.Boolean)
    read_bd = db.Column(db.Boolean)

    # dynamic information (subject to change):
    mount = db.Column(db.String(100))  # mount point (may change on startup)
    firmware = db.Column(db.String(10))
    location = db.Column(db.String(255))
    stale = db.Column(db.Boolean)  # indicate that this drive was not found.
    mdisc = db.Column(db.SmallInteger)
    _tray = None  # Numeric Tray Status

    # cross references:
    job_id_current = db.Column(db.Integer, db.ForeignKey("job.job_id"))
    job_id_previous = db.Column(db.Integer, db.ForeignKey("job.job_id"))
    drive_mode = db.Column(db.String(100))
    # relationship - join current and previous jobs to the jobs table
    job_current = db.relationship("Job", foreign_keys=[job_id_current],
                                  backref=db.backref("drive", uselist=False))
    job_previous = db.relationship("Job", foreign_keys=[job_id_previous])  # No backref, one-way only

    # user input:
    name = db.Column(db.String(100))
    description = db.Column(db.Unicode(200))

    def __init__(self):
        # mark drive info as outdated
        self.stale = True
        self.mdisc = None

        # cross references
        self.job_id_current = None
        self.job_id_previous = None

        # user input
        self.description = ""
        self.name = ""
        self.drive_mode = "auto"

    def update(self, drive):
        """
        Update database object with drive information

        Parameters
        ----------
        drive: arm.ui.settings.DriveUtils.Drive
        """
        # static information
        self.serial_id = drive.serial_id
        self.maker = drive.maker
        self.model = drive.model
        self.serial = drive.serial
        self.connection = drive.connection
        self.read_cd = drive.read_cd
        self.read_dvd = drive.read_dvd
        self.read_bd = drive.read_bd
        # dynamic information
        self.mount = drive.mount
        self.firmware = drive.firmware
        self.location = drive.location
        # mark drive info as updated
        self.stale = False

    @property
    def type(self):
        """find the Drive type (CD, DVD, Blu-ray) from the udev values"""
        temp = ""
        if self.read_cd:
            temp += "CD"
        if self.read_dvd:
            temp += "/DVD"
        if self.read_bd:
            temp += "/BluRay"
        return temp

    def tray_status(self):
        """Query and update tray status.
        """
        if self.stale:
            self.tray = None
        else:
            self.tray = _tray_status(self.mount)
        logging.debug(f"Drive '{self.mount}': tray status '{self.tray}'")
        return self.tray

    @property
    def tray(self):
        """Tray Status EnumItem
        """
        return CDS(self._tray)

    @tray.setter
    def tray(self, value):
        self._tray = CDS(value).value

    @property
    def open(self):
        """Drive tray open"""
        return self.tray == CDS.TRAY_OPEN

    @property
    def ready(self):
        """Drive has medium loaded and is ready for reading."""
        return self.tray == CDS.DISC_OK

    def eject(self, method="eject", release_job=None):
        """Open or close the drive.

        Tries several ``eject`` flag combinations. Tray status from the kernel
        is often wrong on VMware passthrough, so callers should use explicit
        ``eject`` or ``close`` rather than ``toggle``.

        Parameters
        ----------
        method: str
            ``eject`` (open), ``close``, or ``toggle``
        release_job: bool or None
            Release the associated job after the command. Defaults to True
            except for ``close``.

        Returns
        -------
        str or None
            ``None`` on success, otherwise the last error message.
        """
        if release_job is None:
            release_job = method != "close"
        if not self.mount:
            return "Drive has no mount path."
        last_error = f"Unable to {method} {self.mount}"
        if method == "eject":
            try:
                arm_subprocess(["umount", self.mount], check=False)
            except OSError:
                pass
        for cmd in tray_command_lists(self.mount, method):
            try:
                arm_subprocess(cmd, check=True)
                if release_job:
                    self.release_current_job()
                return None
            except CalledProcessError as err:
                last_error = err.output or err.stderr or str(err) or last_error
                logging.warning(f"Tray command failed ({' '.join(cmd)}): {last_error}")
            except OSError as err:
                last_error = str(err)
                logging.warning(f"Tray command failed ({' '.join(cmd)}): {last_error}")
        if release_job:
            self.release_current_job()
        return last_error

    def debug(self, logger=logging):
        """
        Report the current drive status (debug)
        """
        logger.debug("*********")
        logger.debug(f"Name: '{self.name}'")
        logger.debug(f"Drive: '{self.maker} {self.model} ({self.firmware})'")
        logger.debug(f"Type: {self.type}")
        logger.debug(f"Description: '{self.description}'")
        logger.debug(f"Mount: '{self.mount}'")
        jobs = (
            ("Current", self.job_id_current, self.job_current),
            ("Previous", self.job_id_previous, self.job_previous),
        )
        for job_name, job_id, job in jobs:
            logger.debug(f"Job {job_name}: {job_id})")
            if job_id and job is not None:
                logger.debug(f"Job - Status: {job.status}")
                logger.debug(f"Job - Type: {job.video_type}")
                logger.debug(f"Job - Title: {job.title}")
                logger.debug(f"Job - Year: {job.year}")
        logger.debug("*********")

    @property
    def processing(self):
        """Drive has an associated job."""
        return self.job_current is not None

    def release_current_job(self):
        if self.job_id_current is None:
            return
        logging.info("Releasing current job from drive")
        # Preserve as previous job
        self.job_id_previous = self.job_id_current
        # Resetting current job to None in order to release it
        self.job_id_current = None

    def new_job(self, job_id):
        """new job assigned to the drive, update with new job id, and previous job_id"""
        logging.info("Creating new job for drive.")
        self.release_current_job()
        self.job_id_current = job_id
