"""Check media folders without creating them.

Used by the UI (Home / Settings) and by ripper setup so a broken hgfs or NFS
mount is visible before a disc is inserted.
"""

import os

import psutil

MEDIA_PATH_KEYS = ("RAW_PATH", "TRANSCODE_PATH", "COMPLETED_PATH")
PATH_LABELS = {
    "RAW_PATH": "Raw",
    "TRANSCODE_PATH": "Transcode",
    "COMPLETED_PATH": "Completed",
    "LOGPATH": "Logs",
}


def check_path_health(path):
    """Return a dict describing one folder. Never creates directories."""
    result = {
        "path": path or "",
        "exists": False,
        "is_dir": False,
        "readable": False,
        "writable": False,
        "ok": False,
        "free_gb": None,
        "percent_used": None,
        "error": "",
    }
    if not path:
        result["error"] = "Path is empty"
        return result
    try:
        result["exists"] = os.path.lexists(path)
        result["is_dir"] = os.path.isdir(path)
        if result["is_dir"]:
            result["readable"] = os.access(path, os.R_OK)
            result["writable"] = os.access(path, os.W_OK)
            try:
                usage = psutil.disk_usage(path)
                result["free_gb"] = round(usage.free / 1073741824, 1)
                result["percent_used"] = usage.percent
            except OSError as err:
                result["error"] = str(err)
        elif result["exists"]:
            result["error"] = "Path exists but is not a folder"
        else:
            result["error"] = "Folder not found"
    except OSError as err:
        result["error"] = str(err)
    result["ok"] = bool(
        result["is_dir"] and result["readable"] and result["writable"]
    )
    if result["ok"] and not result["error"]:
        result["error"] = ""
    return result


def media_path_health(config):
    """Health for the rip folders ARM needs before a job starts."""
    config = config or {}
    rows = []
    for key in MEDIA_PATH_KEYS:
        row = check_path_health(str(config.get(key) or ""))
        row["key"] = key
        row["label"] = PATH_LABELS.get(key, key)
        rows.append(row)
    return rows


def ensure_writable_dir(folder, logger=None):
    """Create folder if missing; tolerate EEXIST on writable mounts.

    Some hgfs/NFS mounts raise File exists from makedirs even with exist_ok.
    If the path is already a writable directory, continue. Otherwise raise.
    """
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError as err:
        if os.path.isdir(folder) and os.access(folder, os.W_OK):
            if logger:
                logger.warning(
                    "Could not create %s (%s); folder is already writable",
                    folder,
                    err,
                )
            return
        raise OSError(
            err.errno,
            f"Cannot use folder {folder}: {err}",
            folder,
        ) from err
    if not os.path.isdir(folder):
        raise OSError(0, f"Path is not a folder: {folder}", folder)
