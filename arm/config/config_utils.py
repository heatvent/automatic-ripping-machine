import os
import re
import secrets

SECRET_SETTING_KEYS = frozenset({
    "OMDB_API_KEY", "EMBY_USERID", "EMBY_PASSWORD",
    "EMBY_API_KEY", "PB_KEY", "IFTTT_KEY", "PO_KEY",
    "PO_USER_KEY", "PO_APP_KEY", "ARM_API_KEY",
    "TMDB_API_KEY", "MAKEMKV_PERMA_KEY",
})


def is_secret_setting_key(key):
    """True for yaml keys that should be masked in the Settings UI."""
    if not key:
        return False
    if key in SECRET_SETTING_KEYS:
        return True
    return bool(re.search(r"(_KEY|_API|_PASSWORD)$", str(key)))


def mask_last(value, n=4):
    """Replace the last n characters of a string with asterisks."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if not value:
        return value
    if len(value) > n:
        return value[:-n] + ("*" * n)
    return "*" * len(value)


def restore_masked_value(submitted, current):
    """Keep the stored secret when the form posted the masked display value."""
    submitted_text = "" if submitted is None else str(submitted).strip()
    current_text = "" if current is None else str(current)
    if submitted_text == mask_last(current_text):
        return current_text
    return submitted_text


def load_or_create_secret_key(secret_path, environ=None):
    """
    Flask session key: ARM_SECRET_KEY env, else a file next to the DB.
    Generates and persists a random key when neither exists.
    """
    env = (environ if environ is not None else os.environ).get("ARM_SECRET_KEY")
    if env:
        return env
    try:
        if os.path.isfile(secret_path):
            with open(secret_path, encoding="utf-8") as handle:
                existing = handle.read().strip()
            if existing:
                return existing
        key = secrets.token_hex(32)
        directory = os.path.dirname(secret_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(key)
        return key
    except FileExistsError:
        with open(secret_path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return secrets.token_hex(32)


HIDDEN_SETTING_KEYS = frozenset({
    "UNIDENTIFIED_EJECT",
    "UMASK",
    "RIPMETHOD_DVD",
    "RIPMETHOD_BR",
})

BOOLEAN_SETTING_KEYS = frozenset({
    "PREVENT_99", "ARM_CHECK_UDF", "DISABLE_LOGIN", "SKIP_TRANSCODE",
    "MANUAL_WAIT", "ALLOW_DUPLICATES", "RIP_POSTER", "AUTO_EJECT",
    "SET_MEDIA_PERMISSIONS", "SET_MEDIA_OWNER", "DELRAWFILES",
    "USE_FFMPEG", "MAINFEATURE", "EMBY_REFRESH", "NOTIFY_RIP",
    "NOTIFY_TRANSCODE", "NOTIFY_JOBID", "GET_VIDEO_TITLE",
    "MKV_INCLUDE_CORE", "MKV_EXCLUDE_COMMENTARY",
})

ENUM_SETTING_CHOICES = {
    "RIPMETHOD": (
        ("mkv", "MKV Titles"),
        ("backup", "Blu-ray Disc Backup"),
        ("backup_dvd", "DVD Backup Extract"),
    ),
    "VIDEOTYPE": (
        ("auto", "Auto"),
        ("series", "Series"),
        ("movie", "Movie"),
    ),
    "LOGLEVEL": (
        ("DEBUG", "Debug"),
        ("INFO", "Info"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
        ("CRITICAL", "Critical"),
    ),
    "METADATA_PROVIDER": (
        ("omdb", "OMDb"),
        ("tmdb", "TMDb"),
    ),
    "GET_AUDIO_TITLE": (
        ("musicbrainz", "MusicBrainz"),
        ("none", "None"),
    ),
    "DEST_EXT": (
        ("mkv", "MKV"),
        ("mp4", "MP4"),
    ),
    "MKV_LANG": (
        ("eng", "English"),
        ("spa", "Spanish"),
        ("fre", "French"),
        ("ger", "German"),
        ("ita", "Italian"),
        ("jpn", "Japanese"),
        ("kor", "Korean"),
        ("chi", "Chinese"),
        ("por", "Portuguese"),
        ("rus", "Russian"),
        ("dut", "Dutch"),
        ("swe", "Swedish"),
        ("nor", "Norwegian"),
        ("dan", "Danish"),
        ("fin", "Finnish"),
        ("pol", "Polish"),
        ("hun", "Hungarian"),
        ("cze", "Czech"),
        ("tur", "Turkish"),
        ("ara", "Arabic"),
        ("hin", "Hindi"),
        ("tha", "Thai"),
        ("ukr", "Ukrainian"),
        ("gre", "Greek"),
        ("heb", "Hebrew"),
        ("vie", "Vietnamese"),
    ),
    "MKV_VIDEO": (
        ("all", "All video"),
        ("lang", "Language-tagged only"),
    ),
    "MKV_AUDIO": (
        ("best", "Best one (lossless, else surround)"),
        ("all", "All in this language"),
        ("none", "None"),
    ),
    "MKV_SUBTITLES": (
        ("one_plus_forced", "One + forced"),
        ("all", "All in this language"),
        ("forced", "Forced only"),
        ("none", "None"),
    ),
}


def yaml_is_true(value):
    """Interpret yaml/form values that mean boolean true."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def setting_value_as_text(value):
    """Normalize a config value to the string form written to arm.yaml."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def cors_origins_from_children(arm_children):
    """CORS origins for ARM_CHILDREN URLs. Empty means same-origin only."""
    origins = []
    for part in str(arm_children or "").split(","):
        origin = part.strip().rstrip("/")
        if origin:
            origins.append(origin)
    return origins


def arm_yaml_check_groups(comments, key):
    """
    Check the current key to be added to arm.yaml and insert the group
    separator comment, if the key matches\n
    :param comments: comments dict, containing all comments from the arm.yaml
    :param key: the current post key from form.args
    :return: arm.yaml config with any new comments added
    """
    comment_groups = {'COMPLETED_PATH': "\n" + comments['ARM_CFG_GROUPS']['DIR_SETUP'],
                      'WEBSERVER_IP': "\n" + comments['ARM_CFG_GROUPS']['WEB_SERVER'],
                      'SET_MEDIA_PERMISSIONS': "\n" + comments['ARM_CFG_GROUPS']['FILE_PERMS'],
                      'RIPMETHOD': "\n" + comments['ARM_CFG_GROUPS']['MAKE_MKV'],
                      'HB_PRESET_DVD': "\n" + comments['ARM_CFG_GROUPS']['HANDBRAKE'],
                      'EMBY_REFRESH': "\n" + comments['ARM_CFG_GROUPS']['EMBY']
                                      + "\n" + comments['ARM_CFG_GROUPS']['EMBY_ADDITIONAL'],
                      'NOTIFY_RIP': "\n" + comments['ARM_CFG_GROUPS']['NOTIFY_PERMS'],
                      'APPRISE': "\n" + comments['ARM_CFG_GROUPS']['APPRISE']}
    if key in comment_groups:
        arm_cfg = comment_groups[key]
    else:
        arm_cfg = ""
    return arm_cfg


def arm_yaml_test_bool(key, value):
    """
    we need to test if the key is a bool, as we need to lower() it for yaml\n\n
    or check if key is the webserver ip. \nIf not we need to wrap the value with quotes\n
    :param key: the current key
    :param value: the current value
    :return: the new updated arm.yaml config with new key: values
    """
    if value.lower() == 'false' or value.lower() == "true":
        arm_cfg = f"{key}: {value.lower()}\n"
    else:
        # If we got here, the only key that doesn't need quotes is the webserver key
        # everything else needs "" around the value
        if key == "WEBSERVER_IP":
            arm_cfg = f"{key}: {value.lower()}\n"
        else:
            # This isn't intended to be safe, it's to stop breakages - replace all non escaped quotes with escaped
            escaped = re.sub(r"(?<!\\)[\"\'`]", r'\"', value)
            arm_cfg = f"{key}: \"{escaped}\"\n"
    return arm_cfg
