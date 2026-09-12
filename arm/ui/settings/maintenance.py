"""Maintenance tab helpers: job stats, bulk deletes, backup/restore."""
import logging
import os
import sqlite3

from sqlalchemy import or_, text

from arm.models.config import Config
from arm.models.job import JOB_STATUS_FINISHED, Job, JobState
from arm.models.track import Track
from arm.ui import db
from arm.ui.settings import DriveUtils as drive_utils
from arm.ui.settings.backup_zip import (
    BackupError,
    MEMBER_ABCDE,
    MEMBER_APPRISE,
    MEMBER_ARM_YAML,
    MEMBER_DB,
    atomic_replace,
    build_backup_zip,
    extract_backup_zip,
)

FINISHED_STATUSES = tuple(state.value for state in JOB_STATUS_FINISHED)

log = logging.getLogger("armui")


def backup_paths():
    """Live config and database paths included in a backup zip."""
    import arm.config.config as cfg
    return {
        "arm_yaml": cfg.arm_config_path,
        "apprise": cfg.apprise_config_path,
        "abcde": cfg.abcde_config_path,
        "dbfile": cfg.arm_config.get("DBFILE"),
    }


def make_backup_zip():
    """Return (BytesIO, filename) for a downloadable backup."""
    import arm.config.config as cfg
    version = "unknown"
    install = cfg.arm_config.get("INSTALLPATH", "/opt/arm")
    version_file = os.path.join(install, "VERSION")
    try:
        with open(version_file, encoding="utf-8") as handle:
            version = handle.read().strip() or version
    except OSError:
        pass
    return build_backup_zip(backup_paths(), arm_version=version)


def job_stats():
    """Counts shown on the Maintenance tab."""
    total = Job.query.count()
    failed = Job.query.filter(Job.status == JobState.FAILURE.value).count()
    unfinished = Job.query.filter(
        or_(Job.status.is_(None), Job.status.notin_(FINISHED_STATUSES))
    ).count()
    return {
        "total": total,
        "failed": failed,
        "unfinished": unfinished,
        "finished": Job.query.filter(Job.status.in_(FINISHED_STATUSES)).count(),
    }


def _delete_job_row(job):
    """Remove one job row and its tracks/config. Does not delete ripped files."""
    drive_utils.job_cleanup(job.job_id)
    Track.query.filter_by(job_id=job.job_id).delete()
    Config.query.filter_by(job_id=job.job_id).delete()
    db.session.delete(job)


def delete_jobs(scope):
    """Delete failed jobs, or all finished jobs. Returns (deleted, skipped)."""
    if scope == "failed":
        jobs = Job.query.filter(Job.status == JobState.FAILURE.value).all()
        skipped = 0
    elif scope == "all":
        jobs = Job.query.filter(Job.status.in_(FINISHED_STATUSES)).all()
        skipped = Job.query.filter(
            or_(Job.status.is_(None), Job.status.notin_(FINISHED_STATUSES))
        ).count()
    else:
        raise BackupError("Unknown maintenance action.")

    deleted = 0
    for job in jobs:
        _delete_job_row(job)
        deleted += 1
    db.session.commit()
    _vacuum_sqlite()
    return deleted, skipped


def _vacuum_sqlite():
    """Reclaim space after bulk deletes. Safe to ignore if SQLite is busy."""
    try:
        db.session.commit()
        db.session.remove()
        with db.engine.connect() as conn:
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            conn.execute(text("VACUUM"))
    except Exception as err:  # noqa: BLE001
        log.warning("SQLite VACUUM after maintenance failed: %s", err)


def _checkpoint_and_close(dbfile):
    """Flush WAL and drop the SQLAlchemy connection before replacing arm.db."""
    if not dbfile or not os.path.isfile(dbfile):
        db.session.remove()
        db.engine.dispose()
        return
    try:
        conn = sqlite3.connect(dbfile)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as err:
        log.warning("Could not checkpoint SQLite before restore: %s", err)
    db.session.remove()
    db.engine.dispose()


def restore_backup_zip(zip_source, extracted_dir):
    """Replace config files and the database from a backup zip.

    The caller should ask the user to restart the web UI afterwards.
    """
    stats = job_stats()
    if stats["unfinished"]:
        raise BackupError(
            "Restore is blocked while a rip or transcode is running."
        )
    _manifest, extracted = extract_backup_zip(zip_source, extracted_dir)
    paths = backup_paths()
    mapping = (
        (MEMBER_ARM_YAML, paths.get("arm_yaml")),
        (MEMBER_APPRISE, paths.get("apprise")),
        (MEMBER_ABCDE, paths.get("abcde")),
    )
    dbfile = paths.get("dbfile")
    if MEMBER_DB in extracted:
        _checkpoint_and_close(dbfile)
    for member, dest in mapping:
        src = extracted.get(member)
        if src and dest:
            atomic_replace(src, dest)
    if MEMBER_DB in extracted and dbfile:
        for suffix in ("-wal", "-shm"):
            leftover = dbfile + suffix
            if os.path.isfile(leftover):
                os.remove(leftover)
        atomic_replace(extracted[MEMBER_DB], dbfile)
    return True
