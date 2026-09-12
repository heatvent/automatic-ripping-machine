"""Zip backup format for ARM config files and the SQLite database."""
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO

BACKUP_FORMAT = "arm-backup"
BACKUP_VERSION = 1
MANIFEST_NAME = "manifest.json"
MEMBER_ARM_YAML = "config/arm.yaml"
MEMBER_APPRISE = "config/apprise.yaml"
MEMBER_ABCDE = "config/abcde.conf"
MEMBER_DB = "db/arm.db"
ALLOWED_MEMBERS = frozenset({
    MANIFEST_NAME,
    MEMBER_ARM_YAML,
    MEMBER_APPRISE,
    MEMBER_ABCDE,
    MEMBER_DB,
})
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 768 * 1024 * 1024


class BackupError(ValueError):
    """Raised when a backup zip cannot be created or restored."""


def backup_filename(when=None):
    """Return arm-backup-YYYYMMDD-HHMMSS.zip for when (UTC)."""
    stamp = (when or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"arm-backup-{stamp}.zip"


def normalize_zip_name(name):
    """Reject absolute paths and parent-directory segments."""
    if not name or not isinstance(name, str):
        raise BackupError("Backup zip has an invalid file name.")
    cleaned = name.replace("\\", "/").lstrip("/")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise BackupError("Backup zip contains an unsafe path.")
    return "/".join(parts)


def snapshot_sqlite(src_path, dest_path):
    """Copy a consistent SQLite database, including WAL contents."""
    if not os.path.isfile(src_path):
        raise BackupError("Database file is missing.")
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        dest = sqlite3.connect(dest_path)
        try:
            src.backup(dest)
            dest.commit()
        finally:
            dest.close()
    finally:
        src.close()


def _add_file(archive, arcname, path):
    """Add path if it exists. Missing config files are skipped, not fatal."""
    if path and os.path.isfile(path):
        archive.write(path, arcname)
        return True
    return False


def build_backup_zip(paths, arm_version="unknown", created=None):
    """Build an in-memory backup zip.

    paths keys: arm_yaml, apprise, abcde, dbfile
    """
    created = created or datetime.now(timezone.utc)
    contents = []
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if _add_file(archive, MEMBER_ARM_YAML, paths.get("arm_yaml")):
            contents.append(MEMBER_ARM_YAML)
        if _add_file(archive, MEMBER_APPRISE, paths.get("apprise")):
            contents.append(MEMBER_APPRISE)
        if _add_file(archive, MEMBER_ABCDE, paths.get("abcde")):
            contents.append(MEMBER_ABCDE)

        dbfile = paths.get("dbfile")
        if dbfile and os.path.isfile(dbfile):
            handle, tmp_path = tempfile.mkstemp(prefix="arm-db-backup-")
            os.close(handle)
            try:
                snapshot_sqlite(dbfile, tmp_path)
                archive.write(tmp_path, MEMBER_DB)
                contents.append(MEMBER_DB)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
        if not contents:
            raise BackupError("Nothing was available to back up.")

        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created": created.isoformat(),
            "arm_version": arm_version,
            "contents": contents,
        }
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest, indent=2) + "\n",
        )
    buf.seek(0)
    return buf, backup_filename(created)


def _extract_member(archive, info, dest_dir, total):
    name = normalize_zip_name(info.filename)
    if name not in ALLOWED_MEMBERS:
        raise BackupError(f"Unexpected file in backup zip: {name}")
    if info.file_size > MAX_MEMBER_BYTES:
        raise BackupError("A file in the backup zip is too large.")
    total += info.file_size
    if total > MAX_TOTAL_BYTES:
        raise BackupError("Backup zip is too large.")
    target = os.path.join(dest_dir, *name.split("/"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    copied = 0
    with archive.open(info, "r") as src, open(target, "wb") as dest:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_MEMBER_BYTES:
                raise BackupError("A file in the backup zip is too large.")
            dest.write(chunk)
    return name, target, total


def _load_manifest(extracted):
    manifest_path = extracted.get(MANIFEST_NAME)
    if not manifest_path:
        raise BackupError("Backup zip is missing manifest.json.")
    with open(manifest_path, encoding="utf-8") as handle:
        try:
            manifest = json.load(handle)
        except json.JSONDecodeError as err:
            raise BackupError("Backup zip has an invalid manifest.") from err
    if manifest.get("format") != BACKUP_FORMAT:
        raise BackupError("This zip is not an ARM backup.")
    try:
        version = int(manifest.get("version", 0))
    except (TypeError, ValueError) as err:
        raise BackupError("Backup zip has an unsupported version.") from err
    if version < 1 or version > BACKUP_VERSION:
        raise BackupError("Backup zip has an unsupported version.")
    if MEMBER_ARM_YAML not in extracted and MEMBER_DB not in extracted:
        raise BackupError("Backup zip has no configuration or database.")
    return manifest


def extract_backup_zip(zip_source, dest_dir):
    """Extract a trusted ARM backup into dest_dir.

    Returns (manifest dict, {member: abs path}).
    """
    extracted = {}
    total = 0
    try:
        with zipfile.ZipFile(zip_source, "r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name, target, total = _extract_member(
                    archive, info, dest_dir, total
                )
                extracted[name] = target
    except zipfile.BadZipFile as err:
        raise BackupError("That file is not a valid zip.") from err
    return _load_manifest(extracted), extracted


def atomic_replace(src_path, dest_path):
    """Replace dest_path from src_path using a same-directory rename."""
    directory = os.path.dirname(os.path.abspath(dest_path)) or "."
    os.makedirs(directory, exist_ok=True)
    handle, tmp_path = tempfile.mkstemp(dir=directory, prefix=".arm-restore-")
    os.close(handle)
    try:
        shutil.copy2(src_path, tmp_path)
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
