"""Friendly labels, grouping, and validation for ARM settings UI."""

from arm.config.config_utils import (
    BOOLEAN_SETTING_KEYS,
    ENUM_SETTING_CHOICES,
    HIDDEN_SETTING_KEYS,
)

SETTING_LABELS = {
    "ARM_NAME": "Machine name",
    "ARM_CHILDREN": "Child ARM servers",
    "PREVENT_99": "Block DVD Track 99 DRM",
    "ARM_CHECK_UDF": "Identify UDF data vs video",
    "GET_VIDEO_TITLE": "Look up video titles",
    "ARM_API_KEY": "ARM title API key",
    "DISABLE_LOGIN": "Disable UI login",
    "SKIP_TRANSCODE": "Skip transcoding",
    "VIDEOTYPE": "Video type",
    "MINLENGTH": "Minimum title length (seconds)",
    "MAXLENGTH": "Maximum title length (seconds)",
    "MANUAL_WAIT": "Wait for manual title",
    "MANUAL_WAIT_TIME": "Manual wait time (seconds)",
    "DATE_FORMAT": "Date format",
    "ALLOW_DUPLICATES": "Allow duplicate rips",
    "MAX_CONCURRENT_TRANSCODES": "Max concurrent transcodes",
    "MAX_CONCURRENT_MAKEMKVINFO": "Max concurrent MakeMKV info",
    "DATA_RIP_PARAMETERS": "Data disc extra arguments",
    "METADATA_PROVIDER": "Metadata provider",
    "GET_AUDIO_TITLE": "CD title source",
    "RIP_POSTER": "Rip DVD jacket poster",
    "AUTO_EJECT": "Eject when finished",
    "ABCDE_CONFIG_FILE": "CD ripper config file",
    "RAW_PATH": "Raw rip folder",
    "TRANSCODE_PATH": "Transcode folder",
    "COMPLETED_PATH": "Completed folder",
    "EXTRAS_SUB": "Extras subfolder name",
    "INSTALLPATH": "ARM install path",
    "LOGPATH": "Log folder",
    "LOGLEVEL": "Log level",
    "LOGLIFE": "Keep logs (days)",
    "DBFILE": "Database file",
    "WEBSERVER_IP": "UI bind address",
    "WEBSERVER_PORT": "UI port",
    "UI_BASE_URL": "Public UI URL",
    "SET_MEDIA_PERMISSIONS": "Set file permissions",
    "CHMOD_VALUE": "Permission mode",
    "SET_MEDIA_OWNER": "Set file owner",
    "CHOWN_USER": "Owner username",
    "CHOWN_GROUP": "Owner group",
    "MAKEMKV_PERMA_KEY": "MakeMKV license key",
    "RIPMETHOD": "Rip method",
    "MKV_ARGS": "Extra MakeMKV arguments",
    "DELRAWFILES": "Delete temporary rip files",
    "HB_PRESET_DVD": "DVD preset",
    "HB_PRESET_BD": "Blu-ray preset",
    "DEST_EXT": "Output file type",
    "HANDBRAKE_CLI": "HandBrake program",
    "HANDBRAKE_LOCAL": "Local HandBrake program",
    "FFMPEG_PRE_FILE_ARGS": "FFmpeg arguments before input",
    "FFMPEG_POST_FILE_ARGS": "FFmpeg arguments after input",
    "FFMPEG_CLI": "FFmpeg program",
    "FFMPEG_LOCAL": "Local FFmpeg program",
    "USE_FFMPEG": "Use FFmpeg instead of HandBrake",
    "MAINFEATURE": "Main feature only",
    "HB_ARGS_DVD": "Extra DVD arguments",
    "HB_ARGS_BD": "Extra Blu-ray arguments",
    "EMBY_REFRESH": "Refresh Emby library",
    "EMBY_SERVER": "Emby server",
    "EMBY_PORT": "Emby port",
    "EMBY_CLIENT": "Emby client name",
    "EMBY_DEVICE": "Emby device name",
    "EMBY_DEVICEID": "Emby device id",
    "EMBY_USERNAME": "Emby username",
    "EMBY_USERID": "Emby user id",
    "EMBY_PASSWORD": "Emby password hash",
    "EMBY_API_KEY": "Emby API key",
    "NOTIFY_RIP": "Notify when rip finishes",
    "NOTIFY_TRANSCODE": "Notify when transcode finishes",
    "NOTIFY_JOBID": "Include job id in notifications",
    "PB_KEY": "Pushbullet key",
    "IFTTT_KEY": "IFTTT key",
    "IFTTT_EVENT": "IFTTT event name",
    "PO_USER_KEY": "Pushover user key",
    "PO_APP_KEY": "Pushover app key",
    "BASH_SCRIPT": "Notification script",
    "OMDB_API_KEY": "OMDb API key",
    "TMDB_API_KEY": "TMDb API key",
    "JSON_URL": "JSON webhook URL",
    "APPRISE": "Apprise config file",
    "index_refresh": "Home refresh interval (ms)",
    "database_limit": "Jobs per page",
    "notify_refresh": "Notification display time (ms)",
}

GENERAL_SETTING_GROUPS = (
    ("general", "General", (
        "ARM_NAME", "DISABLE_LOGIN", "DATE_FORMAT", "LOGLEVEL", "LOGLIFE",
        "ARM_CHILDREN",
    )),
    ("web", "Web server", (
        "WEBSERVER_IP", "WEBSERVER_PORT", "UI_BASE_URL",
    )),
    ("permissions", "File permissions", (
        "SET_MEDIA_PERMISSIONS", "CHMOD_VALUE", "SET_MEDIA_OWNER",
        "CHOWN_USER", "CHOWN_GROUP",
    )),
    ("paths", "Install paths", (
        "LOGPATH", "DBFILE", "INSTALLPATH", "ABCDE_CONFIG_FILE",
    )),
)

RIPPER_SETTING_GROUPS = (
    ("general", "General", (
        "GET_VIDEO_TITLE", "VIDEOTYPE", "METADATA_PROVIDER", "OMDB_API_KEY",
        "TMDB_API_KEY", "MINLENGTH", "MAXLENGTH", "MANUAL_WAIT", "MANUAL_WAIT_TIME",
        "ALLOW_DUPLICATES", "AUTO_EJECT", "SKIP_TRANSCODE", "PREVENT_99",
        "ARM_CHECK_UDF", "RIP_POSTER", "GET_AUDIO_TITLE", "DATA_RIP_PARAMETERS",
        "ARM_API_KEY",
    )),
    ("directories", "Directories", (
        "RAW_PATH", "TRANSCODE_PATH", "COMPLETED_PATH", "EXTRAS_SUB",
    )),
    ("makemkv", "MakeMKV", (
        "RIPMETHOD", "MAKEMKV_PERMA_KEY", "MKV_ARGS",
        "MAX_CONCURRENT_MAKEMKVINFO", "DELRAWFILES",
    )),
    ("handbrake", "HandBrake", (
        "HB_PRESET_DVD", "HB_PRESET_BD", "DEST_EXT", "MAINFEATURE",
        "HB_ARGS_DVD", "HB_ARGS_BD", "HANDBRAKE_CLI", "HANDBRAKE_LOCAL",
        "MAX_CONCURRENT_TRANSCODES",
    )),
    ("ffmpeg", "FFmpeg", (
        "USE_FFMPEG", "FFMPEG_CLI", "FFMPEG_LOCAL",
        "FFMPEG_PRE_FILE_ARGS", "FFMPEG_POST_FILE_ARGS",
    )),
)

NOTIFY_SETTING_GROUPS = (
    ("notify", "General", (
        "NOTIFY_RIP", "NOTIFY_TRANSCODE", "NOTIFY_JOBID", "PB_KEY",
        "IFTTT_KEY", "IFTTT_EVENT", "PO_USER_KEY", "PO_APP_KEY",
        "BASH_SCRIPT", "JSON_URL", "APPRISE",
    )),
    ("emby", "Emby", (
        "EMBY_REFRESH", "EMBY_SERVER", "EMBY_PORT", "EMBY_USERNAME",
        "EMBY_USERID", "EMBY_PASSWORD", "EMBY_API_KEY", "EMBY_CLIENT",
        "EMBY_DEVICE", "EMBY_DEVICEID",
    )),
)

SETTING_GROUPS = GENERAL_SETTING_GROUPS + RIPPER_SETTING_GROUPS + NOTIFY_SETTING_GROUPS

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
            settings, RIPPER_SETTING_GROUPS, exclude_keys=general_keys | notify_keys
        ),
        "notify": grouped_setting_keys(
            settings, NOTIFY_SETTING_GROUPS, leftovers=False
        ),
    }


def validate_ripper_form(form_data, current_settings=None):
    """Return {key: message} for invalid submitted ripper settings."""
    errors = {}
    current_settings = current_settings or {}
    values = {}
    for key, raw in form_data.items():
        if key == "csrf_token":
            continue
        values[key] = "" if raw is None else str(raw).strip()

    def _int(key, minimum=None, maximum=None):
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

    for key in INTEGER_SETTING_KEYS:
        if key in PORT_SETTING_KEYS:
            _int(key, 1, 65535)
        elif key in ("LOGLIFE", "MAX_CONCURRENT_TRANSCODES", "MAX_CONCURRENT_MAKEMKVINFO"):
            _int(key, 0)
        else:
            _int(key, 0)

    for key in NONEMPTY_SETTING_KEYS:
        if key in values and values[key] == "":
            errors[key] = "This field is required."

    chmod = values.get("CHMOD_VALUE")
    if chmod is not None and chmod != "":
        import re
        if not re.fullmatch(r"[0-7]{3,4}", chmod):
            errors["CHMOD_VALUE"] = "Use 3 or 4 octal digits, for example 775."

    min_len = values.get("MINLENGTH")
    max_len = values.get("MAXLENGTH")
    try:
        if min_len not in (None, "") and max_len not in (None, ""):
            if int(min_len) > int(max_len):
                errors["MAXLENGTH"] = "Must be greater than or equal to minimum title length."
    except ValueError:
        pass

    for key, choices in ENUM_SETTING_CHOICES.items():
        if key not in values:
            continue
        allowed = {item[0] for item in choices}
        if values[key] not in allowed:
            errors[key] = "Choose one of the listed options."

    for key in BOOLEAN_SETTING_KEYS:
        if key in values and values[key].lower() not in ("true", "false"):
            errors[key] = "Choose Yes or No."

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
