"""MakeMKV default selection rules and playlist-obfuscation helpers.

MakeMKV does not take ``-sel:`` on the ARM Extra Arguments line. The
selection string belongs in ``~/.MakeMKV/settings.conf`` as
``app_DefaultSelectionString``. ARM generates that string from the Movie
Ripper MakeMKV dropdowns.
"""

import os
import re
import tempfile

from arm.config.config_utils import yaml_is_true

SELECTION_DEFAULTS = {
    "MKV_LANG": "eng",
    "MKV_VIDEO": "all",
    "MKV_AUDIO": "best",
    "MKV_INCLUDE_CORE": "false",
    "MKV_EXCLUDE_COMMENTARY": "true",
    "MKV_SUBTITLES": "one_plus_forced",
}

DEFAULT_SETTINGS_CONF = "/home/arm/.MakeMKV/settings.conf"
SELECTION_LINE_RE = re.compile(
    r'^app_DefaultSelectionString\s*=\s*".*"\s*$',
    re.MULTILINE,
)
LANG_RE = re.compile(r"^[a-z]{3}$")
PLAYLIST_MIN_MATCHES = 3
PLAYLIST_SIMILAR_RATIO = 0.02
PLAYLIST_SIMILAR_FLOOR = 90


def apply_selection_defaults(config):
    """Fill missing MakeMKV selection keys and keep them next to MKV_ARGS."""
    if not isinstance(config, dict):
        return config
    for key, value in SELECTION_DEFAULTS.items():
        config.setdefault(key, value)
    if "MKV_ARGS" not in config:
        return config
    ordered = {}
    for key, value in config.items():
        if key in SELECTION_DEFAULTS:
            continue
        if key == "MKV_ARGS":
            for sel_key in SELECTION_DEFAULTS:
                ordered[sel_key] = config[sel_key]
        ordered[key] = value
    for sel_key in SELECTION_DEFAULTS:
        if sel_key not in ordered:
            ordered[sel_key] = config[sel_key]
    config.clear()
    config.update(ordered)
    return config


def selection_language(config):
    """Return a 3-letter MakeMKV language code, defaulting to English."""
    config = config or {}
    lang = str(config.get("MKV_LANG") or SELECTION_DEFAULTS["MKV_LANG"])
    lang = lang.strip().lower()
    if not LANG_RE.fullmatch(lang):
        return SELECTION_DEFAULTS["MKV_LANG"]
    return lang


def build_selection_string(config=None):
    """Build MakeMKV ``app_DefaultSelectionString`` from ARM settings."""
    config = config or {}
    lang = selection_language(config)
    video = str(config.get("MKV_VIDEO") or SELECTION_DEFAULTS["MKV_VIDEO"]).strip().lower()
    audio = str(config.get("MKV_AUDIO") or SELECTION_DEFAULTS["MKV_AUDIO"]).strip().lower()
    subs = str(
        config.get("MKV_SUBTITLES") or SELECTION_DEFAULTS["MKV_SUBTITLES"]
    ).strip().lower()
    include_core = yaml_is_true(config.get("MKV_INCLUDE_CORE"))
    if "MKV_EXCLUDE_COMMENTARY" in config:
        exclude_commentary = yaml_is_true(config.get("MKV_EXCLUDE_COMMENTARY"))
    else:
        exclude_commentary = True

    parts = ["-sel:all"]
    if video == "lang":
        parts.append(f"+sel:video&({lang})")
    else:
        parts.append("+sel:video")
    parts.append("-sel:mvcvideo")

    if audio != "none":
        parts.append(f"+sel:audio&({lang})")
        if exclude_commentary:
            parts.append("-sel:special")
        if audio == "best":
            parts.append(f"-sel:audio&({lang}&havemulti)")
            parts.append(f"-sel:audio&({lang}&havelossless)")
            if not include_core:
                parts.append(f"-sel:audio&({lang}&core)")
            parts.append(f"-sel:audio&({lang}&2)")
        elif not include_core:
            parts.append(f"-sel:audio&({lang}&core)")

    if subs == "all":
        parts.append(f"+sel:forced&({lang})")
        parts.append(f"+sel:subtitle&({lang})")
    elif subs == "forced":
        parts.append(f"+sel:forced&({lang})")
    elif subs != "none":
        parts.append(f"+sel:forced&({lang})")
        parts.append(f"+sel:subtitle&({lang})")
        parts.append(f"-sel:subtitle&({lang}&2)")

    return ",".join(parts)


def default_settings_path():
    """Path to MakeMKV settings.conf (ARM user home, unless overridden)."""
    override = os.environ.get("MAKEMKV_SETTINGS")
    if override:
        return override
    return DEFAULT_SETTINGS_CONF


def write_default_selection(path, selection):
    """Set ``app_DefaultSelectionString`` without touching ``app_Key``."""
    if '"' in str(selection):
        raise ValueError("MakeMKV selection string cannot contain quotes")
    line = f'app_DefaultSelectionString = "{selection}"'
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except FileNotFoundError:
        current = ""
    stripped = SELECTION_LINE_RE.sub("", current).strip("\n")
    if stripped:
        stripped += "\n"
    updated = stripped + line + "\n"
    if not updated.endswith("\n"):
        updated += "\n"
    fd, tmp_path = tempfile.mkstemp(prefix="settings.conf.", dir=directory or None)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return path


def apply_default_selection(config=None, path=None):
    """Write the generated selection string into MakeMKV settings.conf."""
    selection = build_selection_string(config)
    write_default_selection(path or default_settings_path(), selection)
    return selection


def choose_main_feature_track(tracks):
    """Pick one title: most chapters, then largest, then longest, then lowest number.

    Longest duration alone is a poor Blu-ray heuristic: some discs repeat the
    movie playlist many times at the same length. Chapter count and reported
    size usually separate the real playlist from the decoys. Duration remains
    a tie-breaker for ordinary discs.
    """
    chosen = None
    best = None
    for track in tracks or []:
        score = main_feature_sort_key(track)
        if best is None or score > best:
            best = score
            chosen = track
    return chosen


def main_feature_sort_key(track):
    """Comparable tuple for main-title guessing (higher is better)."""
    try:
        number = int(getattr(track, "track_number", 0) or 0)
    except (TypeError, ValueError):
        number = 0
    return (
        _int_attr(track, "chapters"),
        _int_attr(track, "filesize"),
        track_length_seconds(track),
        -number,
    )


def _int_attr(obj, name):
    try:
        return int(getattr(obj, name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def track_length_seconds(track):
    """Best-effort integer length from a Track row or duck-typed object."""
    try:
        return int(getattr(track, "length", 0) or 0)
    except (TypeError, ValueError):
        return 0


def find_similar_movie_titles(tracks, minlength=0, min_matches=PLAYLIST_MIN_MATCHES):
    """Titles at main-feature length that look like playlist clones.

    Uses the longest title at or above ``minlength`` as the reference, then
    collects others within 2% or 90 seconds of that length. Returns [] unless
    at least ``min_matches`` titles share that duration.
    """
    try:
        floor = int(minlength or 0)
    except (TypeError, ValueError):
        floor = 0
    candidates = []
    for track in tracks or []:
        length = track_length_seconds(track)
        if length >= floor:
            candidates.append((track, length))
    if len(candidates) < min_matches:
        return []
    longest = max(length for _track, length in candidates)
    window = max(int(longest * PLAYLIST_SIMILAR_RATIO), PLAYLIST_SIMILAR_FLOOR)
    similar = [track for track, length in candidates if abs(length - longest) <= window]
    if len(similar) < min_matches:
        return []
    return similar


def format_hms(seconds):
    """Format a duration as H:MM:SS."""
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def format_playlist_warning(similar_tracks, mainfeature=False):
    """User-facing warning when a disc repeats the movie playlist."""
    lengths = [track_length_seconds(track) for track in similar_tracks]
    typical = max(lengths) if lengths else 0
    numbers = []
    for track in similar_tracks:
        number = getattr(track, "track_number", None)
        if number is None:
            continue
        numbers.append(str(number))
    shown = numbers[:20]
    extra = len(numbers) - len(shown)
    track_list = ", ".join(shown)
    if extra > 0:
        track_list = f"{track_list}, … +{extra} more"
    message = (
        f"This Blu-ray has {len(similar_tracks)} titles about "
        f"{format_hms(typical)} long (main-feature length). Studios sometimes "
        "repeat the movie playlist to confuse ripping; only one of those "
        "titles is usually the real movie. ARM cannot tell which from "
        "duration alone. Check the ripped file, or use a manual-mode drive "
        "and pick titles after playing the disc on a PC to see which "
        "playlist it actually uses."
    )
    if track_list:
        message += f" Matching title numbers: {track_list}."
    if mainfeature:
        message += (
            " Main Feature Only is on, so ARM will rip one title (most "
            "chapters, then largest, then longest). Confirm that file is "
            "the movie."
        )
    else:
        message += (
            " Without Main Feature Only, ARM may rip every matching title."
        )
    return message
