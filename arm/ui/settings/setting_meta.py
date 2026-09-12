"""Friendly labels, grouping, and validation for ARM settings UI."""

import html as html_module
import re

from arm.config.config_utils import (
    BOOLEAN_SETTING_KEYS,
    ENUM_SETTING_CHOICES,
    HIDDEN_SETTING_KEYS,
)

SETTING_LABELS = {
    "ARM_NAME": "Machine Name",
    "ARM_CHILDREN": "Child ARM Servers",
    "PREVENT_99": "Block DVD Track 99 DRM",
    "ARM_CHECK_UDF": "Identify UDF Data vs Video",
    "GET_VIDEO_TITLE": "Look Up Video Titles",
    "ARM_API_KEY": "ARM Title API Key",
    "DISABLE_LOGIN": "Disable UI Login",
    "SKIP_TRANSCODE": "Skip Transcoding",
    "VIDEOTYPE": "Video Type",
    "MINLENGTH": "Minimum Title Length (s)",
    "MAXLENGTH": "Maximum Title Length (s)",
    "MANUAL_WAIT": "Wait for Manual Title",
    "MANUAL_WAIT_TIME": "Manual Wait Time (s)",
    "DATE_FORMAT": "Date Format",
    "ALLOW_DUPLICATES": "Allow Duplicate Rips",
    "MAX_CONCURRENT_TRANSCODES": "Max Concurrent Transcodes",
    "MAX_CONCURRENT_MAKEMKVINFO": "Max Concurrent Rips",
    "DATA_RIP_PARAMETERS": "Data Disc Extra Arguments",
    "METADATA_PROVIDER": "Metadata Provider",
    "GET_AUDIO_TITLE": "CD Title Source",
    "RIP_POSTER": "Rip DVD Jacket Poster",
    "AUTO_EJECT": "Eject When Finished",
    "ABCDE_CONFIG_FILE": "CD Ripper Config File",
    "RAW_PATH": "Raw Rip Folder",
    "TRANSCODE_PATH": "Transcode Folder",
    "COMPLETED_PATH": "Completed Folder",
    "EXTRAS_SUB": "Extras Subfolder Name",
    "INSTALLPATH": "ARM Install Path",
    "LOGPATH": "Log Folder",
    "LOGLEVEL": "Log Level",
    "LOGLIFE": "Keep Logs (Days)",
    "DBFILE": "Database File",
    "WEBSERVER_IP": "UI Bind Address",
    "WEBSERVER_PORT": "UI Port",
    "UI_BASE_URL": "Public UI URL",
    "SET_MEDIA_PERMISSIONS": "Set File Permissions",
    "CHMOD_VALUE": "Permission Mode",
    "SET_MEDIA_OWNER": "Set File Owner",
    "CHOWN_USER": "Owner Username",
    "CHOWN_GROUP": "Owner Group",
    "MAKEMKV_PERMA_KEY": "License Key",
    "RIPMETHOD": "Rip Method",
    "MKV_LANG": "Language",
    "MKV_VIDEO": "Video",
    "MKV_AUDIO": "Audio",
    "MKV_INCLUDE_CORE": "Include HD Core",
    "MKV_EXCLUDE_COMMENTARY": "Exclude Commentary",
    "MKV_SUBTITLES": "Subtitles",
    "MKV_ARGS": "Extra Arguments",
    "DELRAWFILES": "Delete Temporary Rip Files",
    "HB_PRESET_DVD": "DVD Preset",
    "HB_PRESET_BD": "Blu-ray Preset",
    "DEST_EXT": "Output File Type",
    "HANDBRAKE_CLI": "HandBrake Program",
    "HANDBRAKE_LOCAL": "Local HandBrake Program",
    "FFMPEG_PRE_FILE_ARGS": "Arguments Before Input",
    "FFMPEG_POST_FILE_ARGS": "Arguments After Input",
    "FFMPEG_CLI": "FFmpeg Program",
    "FFMPEG_LOCAL": "Local FFmpeg Program",
    "USE_FFMPEG": "Use FFmpeg Instead of HandBrake",
    "MAINFEATURE": "Main Title Only",
    "HB_ARGS_DVD": "Extra DVD Arguments",
    "HB_ARGS_BD": "Extra Blu-ray Arguments",
    "EMBY_REFRESH": "Refresh Emby Library",
    "EMBY_SERVER": "Emby Server",
    "EMBY_PORT": "Emby Port",
    "EMBY_CLIENT": "Emby Client Name",
    "EMBY_DEVICE": "Emby Device Name",
    "EMBY_DEVICEID": "Emby Device ID",
    "EMBY_USERNAME": "Emby Username",
    "EMBY_USERID": "Emby User ID",
    "EMBY_PASSWORD": "Emby Password Hash",
    "EMBY_API_KEY": "Emby API Key",
    "NOTIFY_RIP": "Notify When Rip Finishes",
    "NOTIFY_TRANSCODE": "Notify When Transcode Finishes",
    "NOTIFY_JOBID": "Include Job ID",
    "PB_KEY": "Pushbullet Key",
    "IFTTT_KEY": "IFTTT Key",
    "IFTTT_EVENT": "IFTTT Event Name",
    "PO_USER_KEY": "Pushover User Key",
    "PO_APP_KEY": "Pushover App Key",
    "BASH_SCRIPT": "Notification Script",
    "OMDB_API_KEY": "OMDb API Key",
    "TMDB_API_KEY": "TMDb API Key",
    "JSON_URL": "JSON Webhook URL",
    "APPRISE": "Apprise Config File",
    "index_refresh": "Home Refresh Interval (ms)",
    "database_limit": "History per Page",
    # Unused leftover; hidden on the Web UI form. Label kept for comments.json.
    "notify_refresh": "Notification Display Time (ms)",
}

GENERAL_SETTING_GROUPS = (
    ("identity", "Identity", (
        "ARM_NAME", "DISABLE_LOGIN", "DATE_FORMAT", "ARM_CHILDREN",
    )),
    ("logging", "Logging", (
        "LOGLEVEL", "LOGLIFE",
    )),
    ("web", "Web Server", (
        "WEBSERVER_IP", "WEBSERVER_PORT", "UI_BASE_URL",
    )),
    ("permissions", "File Permissions", (
        "SET_MEDIA_PERMISSIONS", "CHMOD_VALUE", "SET_MEDIA_OWNER",
        "CHOWN_USER", "CHOWN_GROUP",
    )),
    ("paths", "Install Paths", (
        "LOGPATH", "DBFILE", "INSTALLPATH",
    )),
)

SETTING_GROUP_INTROS = {
    "identify": (
        "Look up the disc title before MakeMKV starts."
    ),
    "tracks": (
        "Which titles MakeMKV rips from a movie disc."
    ),
    "rip": (
        "MakeMKV writes decrypted MKV files to Raw. The tray ejects when this finishes."
    ),
    "transcode": (
        "Skip Transcoding copies Raw to Completed and does not run HandBrake or FFmpeg. "
        "Max Concurrent Transcodes limits whichever encoder is used."
    ),
    "handbrake": (
        "Used when Skip Transcoding is No and Use FFmpeg Instead of HandBrake is No."
    ),
    "ffmpeg": (
        "Used only when Use FFmpeg Instead of HandBrake is Yes. Experimental. "
        "Max Concurrent Transcodes still limits how many FFmpeg jobs run at once."
    ),
    "copy": (
        "Final library folder. Keep Raw and Transcode on local disk; Completed can be a share."
    ),
}

RIPPER_SETTING_GROUPS = (
    ("identify", "Identify", (
        "GET_VIDEO_TITLE", "VIDEOTYPE", "METADATA_PROVIDER", "OMDB_API_KEY",
        "TMDB_API_KEY", "ARM_API_KEY",
    )),
    ("tracks", "Tracks to Rip", (
        "MINLENGTH", "MAXLENGTH", "MAINFEATURE", "PREVENT_99",
        "ARM_CHECK_UDF", "RIP_POSTER", "DATA_RIP_PARAMETERS",
    )),
    ("rip", "Rip with MakeMKV", (
        "RIPMETHOD", "MKV_LANG", "MKV_VIDEO", "MKV_AUDIO",
        "MKV_INCLUDE_CORE", "MKV_EXCLUDE_COMMENTARY", "MKV_SUBTITLES",
        "MAKEMKV_PERMA_KEY", "MKV_ARGS", "MAX_CONCURRENT_MAKEMKVINFO", "DELRAWFILES",
    )),
    ("transcode", "Transcode", (
        "SKIP_TRANSCODE", "MAX_CONCURRENT_TRANSCODES",
    )),
    ("handbrake", "HandBrake", (
        "HB_PRESET_DVD", "HB_PRESET_BD", "DEST_EXT",
        "HB_ARGS_DVD", "HB_ARGS_BD", "HANDBRAKE_CLI", "HANDBRAKE_LOCAL",
    )),
    ("ffmpeg", "FFmpeg", (
        "USE_FFMPEG", "FFMPEG_CLI", "FFMPEG_LOCAL",
        "FFMPEG_PRE_FILE_ARGS", "FFMPEG_POST_FILE_ARGS",
    )),
    ("copy", "Copy to Library", (
        "RAW_PATH", "TRANSCODE_PATH", "COMPLETED_PATH", "EXTRAS_SUB",
    )),
    ("flow", "Job Flow", (
        "MANUAL_WAIT", "MANUAL_WAIT_TIME", "ALLOW_DUPLICATES", "AUTO_EJECT",
    )),
)

NOTIFY_SETTING_GROUPS = (
    ("when", "When to Notify", (
        "NOTIFY_RIP", "NOTIFY_TRANSCODE", "NOTIFY_JOBID",
    )),
    ("ifttt", "IFTTT", (
        "IFTTT_KEY", "IFTTT_EVENT",
    )),
    ("pushover", "Pushover", (
        "PO_USER_KEY", "PO_APP_KEY",
    )),
    ("pushbullet", "Pushbullet", (
        "PB_KEY",
    )),
    ("webhooks", "Script and Webhook", (
        "BASH_SCRIPT", "JSON_URL",
    )),
    ("emby", "Emby", (
        "EMBY_REFRESH", "EMBY_SERVER", "EMBY_PORT", "EMBY_API_KEY",
        "EMBY_USERNAME", "EMBY_PASSWORD", "EMBY_USERID",
        "EMBY_CLIENT", "EMBY_DEVICE", "EMBY_DEVICEID",
    )),
    ("apprise", "Apprise File", (
        "APPRISE",
    )),
)

SETTING_GROUPS = GENERAL_SETTING_GROUPS + RIPPER_SETTING_GROUPS + NOTIFY_SETTING_GROUPS
CD_RIPPER_YAML_KEYS = frozenset({"ABCDE_CONFIG_FILE", "GET_AUDIO_TITLE"})

NONEMPTY_SETTING_KEYS = frozenset({
    "DATE_FORMAT", "HB_PRESET_DVD", "HB_PRESET_BD", "HANDBRAKE_CLI",
    "DBFILE", "LOGPATH", "INSTALLPATH", "RAW_PATH", "TRANSCODE_PATH",
    "COMPLETED_PATH",
})

INTEGER_SETTING_KEYS = frozenset({
    "MINLENGTH", "MAXLENGTH", "MANUAL_WAIT_TIME",
    "MAX_CONCURRENT_TRANSCODES", "MAX_CONCURRENT_MAKEMKVINFO",
    "WEBSERVER_PORT", "LOGLIFE", "EMBY_PORT",
})

PORT_SETTING_KEYS = frozenset({"WEBSERVER_PORT", "EMBY_PORT"})


def setting_label(key):
    return SETTING_LABELS.get(key, key.replace("_", " ").title())


def strip_comment_hashes(comment):
    """Remove leading yaml ``#`` prefixes from each comment line."""
    if not comment or not isinstance(comment, str):
        return ""
    lines = []
    for raw in comment.splitlines():
        line = raw.lstrip()
        if line.startswith("#"):
            line = line[1:]
            if line.startswith(" "):
                line = line[1:]
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def format_setting_help(key, comment):
    """Popover body: user-facing comment text, then YAML key for traceability."""
    body = strip_comment_hashes(comment)
    if not body:
        body = "No description is available for this setting."
    safe_key = html_module.escape(str(key or ""))
    safe_body = html_module.escape(body)
    return f"{safe_body}\n\nYAML key: <code>{safe_key}</code>"


def grouped_setting_keys(settings, groups=None, leftovers=True, exclude_keys=None):
    """Return (group_id, title, keys_present) covering visible yaml keys."""
    hidden = HIDDEN_SETTING_KEYS
    exclude_keys = exclude_keys or set()
    group_list = groups if groups is not None else SETTING_GROUPS
    remaining = [
        key for key in settings
        if key not in hidden and key not in exclude_keys
    ]
    grouped = []
    used = set()
    for group_id, title, keys in group_list:
        present = [key for key in keys if key in settings and key not in hidden]
        if present:
            grouped.append((group_id, title, present))
            used.update(present)
    leftover = [key for key in remaining if key not in used]
    if leftovers and leftover:
        grouped.append(("other", "Other", leftover))
    return grouped


def page_setting_groups(settings):
    """Split visible yaml keys across General, Ripper, and Notifications tabs."""
    general_keys = {
        key for _, _, keys in GENERAL_SETTING_GROUPS for key in keys
    }
    notify_keys = {
        key for _, _, keys in NOTIFY_SETTING_GROUPS for key in keys
    }
    return {
        "general": grouped_setting_keys(
            settings, GENERAL_SETTING_GROUPS, leftovers=False
        ),
        "ripper": grouped_setting_keys(
            settings, RIPPER_SETTING_GROUPS,
            exclude_keys=general_keys | notify_keys | CD_RIPPER_YAML_KEYS,
        ),
        "notify": grouped_setting_keys(
            settings, NOTIFY_SETTING_GROUPS, leftovers=False
        ),
    }


def _require_int(errors, values, key, minimum=None, maximum=None):
    """Validate one integer setting and record errors in place."""
    if key not in values:
        return
    text = values[key]
    if text == "":
        if key in ("EMBY_PORT",):
            return
        errors[key] = "Enter a number."
        return
    try:
        number = int(text)
    except ValueError:
        errors[key] = "Must be a whole number."
        return
    if minimum is not None and number < minimum:
        errors[key] = f"Must be at least {minimum}."
    if maximum is not None and number > maximum:
        errors[key] = f"Must be at most {maximum}."


def _validate_ripper_numbers(errors, values):
    for key in INTEGER_SETTING_KEYS:
        if key in PORT_SETTING_KEYS:
            _require_int(errors, values, key, 1, 65535)
        else:
            _require_int(errors, values, key, 0)


def _validate_ripper_required(errors, values):
    for key in NONEMPTY_SETTING_KEYS:
        if key in values and values[key] == "":
            errors[key] = "This field is required."


def _validate_ripper_chmod(errors, values):
    chmod = values.get("CHMOD_VALUE")
    if chmod is not None and chmod != "" and not re.fullmatch(r"[0-7]{3,4}", chmod):
        errors["CHMOD_VALUE"] = "Use 3 or 4 octal digits, for example 775."


def _validate_ripper_lengths(errors, values):
    min_len = values.get("MINLENGTH")
    max_len = values.get("MAXLENGTH")
    try:
        if min_len not in (None, "") and max_len not in (None, ""):
            if int(min_len) > int(max_len):
                errors["MAXLENGTH"] = "Must be greater than or equal to minimum title length."
    except ValueError:
        pass


def _validate_ripper_enums(errors, values):
    for key, choices in ENUM_SETTING_CHOICES.items():
        if key not in values:
            continue
        allowed = {item[0] for item in choices}
        if values[key] not in allowed:
            errors[key] = "Choose one of the listed options."


def _validate_ripper_bools(errors, values):
    for key in BOOLEAN_SETTING_KEYS:
        if key in values and values[key].lower() not in ("true", "false"):
            errors[key] = "Choose Yes or No."


def validate_ripper_form(form_data, current_settings=None):
    """Return {key: message} for invalid submitted ripper settings."""
    errors = {}
    current_settings = current_settings or {}
    values = {}
    for key, raw in form_data.items():
        if key == "csrf_token":
            continue
        values[key] = "" if raw is None else str(raw).strip()

    _validate_ripper_numbers(errors, values)
    _validate_ripper_required(errors, values)
    _validate_ripper_chmod(errors, values)
    _validate_ripper_lengths(errors, values)
    _validate_ripper_enums(errors, values)
    _validate_ripper_bools(errors, values)
    return errors


def validate_ui_form(index_refresh, database_limit):
    """Return {key: message} for invalid UI settings."""
    errors = {}
    if index_refresh is None:
        errors["index_refresh"] = "Enter a number."
    elif index_refresh < 500:
        errors["index_refresh"] = "Must be at least 500 milliseconds."
    if database_limit is None:
        errors["database_limit"] = "Enter a number."
    elif database_limit < 1 or database_limit > 200:
        errors["database_limit"] = "Must be between 1 and 200."
    return errors
