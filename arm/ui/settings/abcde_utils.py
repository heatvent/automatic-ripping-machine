"""Parse and update abcde.conf as named settings instead of a raw dump."""

import re

ABCDE_FIELDS = (
    {
        "key": "CDDBMETHOD",
        "label": "Album lookup",
        "help": "Where abcde gets artist and album names. musicbrainz is the default and recommended.",
        "kind": "enum",
        "choices": (
            ("musicbrainz", "MusicBrainz"),
            ("cddb", "CDDB"),
            ("cdtext", "CD-Text"),
        ),
    },
    {
        "key": "OUTPUTTYPE",
        "label": "Output format",
        "help": "Encoded format. Common choices: flac, mp3, ogg, opus, wav, m4a. You can also comma-separate more than one.",
        "kind": "enum",
        "choices": (
            ("flac", "FLAC"),
            ("mp3", "MP3"),
            ("ogg", "Ogg Vorbis"),
            ("opus", "Opus"),
            ("wav", "WAV"),
            ("m4a", "M4A / AAC"),
        ),
        "allow_custom": True,
    },
    {
        "key": "OUTPUTDIR",
        "label": "Output folder",
        "help": "Folder where ripped CDs are written. Include a trailing slash.",
        "kind": "text",
    },
    {
        "key": "OUTPUTFORMAT",
        "label": "File name pattern",
        "help": "Path pattern using ${ARTISTFILE}, ${ALBUMFILE}, ${TRACKNUM}, and ${TRACKFILE}. Keep this in single quotes in the file.",
        "kind": "text",
    },
    {
        "key": "VAOUTPUTFORMAT",
        "label": "Various-artists pattern",
        "help": "Name pattern used for Various Artists discs.",
        "kind": "text",
    },
    {
        "key": "PADTRACKS",
        "label": "Pad track numbers",
        "help": "Yes writes 01, 02, 03 instead of 1, 2, 3.",
        "kind": "yn",
    },
    {
        "key": "INTERACTIVE",
        "label": "Ask questions while ripping",
        "help": "No (recommended for ARM) rips without prompts. Yes waits for keyboard input.",
        "kind": "yn",
    },
    {
        "key": "EJECTCD",
        "label": "Eject after reading",
        "help": "Eject the CD after tracks have been read. ARM also has its own eject setting.",
        "kind": "yn",
    },
    {
        "key": "KEEPWAVS",
        "label": "Keep WAV files",
        "help": "Yes keeps the temporary WAV files after encoding.",
        "kind": "yn",
    },
    {
        "key": "MAXPROCS",
        "label": "Parallel encoders",
        "help": "How many encode processes to run at once. Higher is faster on multi-core systems.",
        "kind": "int",
        "minimum": 1,
        "maximum": 32,
    },
    {
        "key": "ACTIONS",
        "label": "Rip actions",
        "help": "Comma-separated abcde actions, for example musicbrainz,read,encode,tag,move,clean,playlist,getalbumart,embedalbumart.",
        "kind": "text",
    },
)

_ASSIGN_RE = re.compile(
    r"^(?P<comment>#\s*)?(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$"
)


def strip_abcde_value(value):
    text = (value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def format_abcde_value(value):
    text = "" if value is None else str(value)
    if text == "":
        return '""'
    if any(ch in text for ch in (' ', '$', "'", '"', '{', '}')) and not (
        len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"')
    ):
        escaped = text.replace("'", r"'\''")
        return f"'{escaped}'"
    return text


def parse_abcde_values(conf_text):
    """Return {key: value} for uncommented assignments, then commented defaults."""
    active = {}
    commented = {}
    for line in (conf_text or "").splitlines():
        match = _ASSIGN_RE.match(line.rstrip())
        if not match:
            continue
        key = match.group("key")
        value = strip_abcde_value(match.group("value"))
        if match.group("comment"):
            commented.setdefault(key, value)
        else:
            active[key] = value
    merged = dict(commented)
    merged.update(active)
    return merged, set(active)


def abcde_fields_for_ui(conf_text):
    values, active = parse_abcde_values(conf_text)
    fields = []
    for spec in ABCDE_FIELDS:
        key = spec["key"]
        item = dict(spec)
        item["value"] = values.get(key, "")
        item["active"] = key in active
        item["choice_values"] = [choice[0] for choice in spec.get("choices", ())]
        fields.append(item)
    return fields


def apply_abcde_updates(conf_text, form_data):
    """Write curated keys into abcde.conf, preserving comments and other lines."""
    wanted = {}
    for spec in ABCDE_FIELDS:
        key = spec["key"]
        if key not in form_data:
            continue
        value = "" if form_data.get(key) is None else str(form_data.get(key)).strip()
        if spec["kind"] == "yn":
            value = normalize_abcde_yn(value)
        wanted[key] = value

    lines = (conf_text or "").splitlines()
    replaced = set()

    def _replace(prefer_commented):
        for index, line in enumerate(lines):
            match = _ASSIGN_RE.match(line.rstrip())
            if not match:
                continue
            key = match.group("key")
            if key not in wanted or key in replaced:
                continue
            is_comment = bool(match.group("comment"))
            if is_comment != prefer_commented:
                continue
            lines[index] = f"{key}={format_abcde_value(wanted[key])}"
            replaced.add(key)

    _replace(False)
    _replace(True)
    for key, value in wanted.items():
        if key not in replaced:
            lines.append(f"{key}={format_abcde_value(value)}")
    return "\n".join(lines) + "\n"


def validate_abcde_form(form_data):
    errors = {}
    for spec in ABCDE_FIELDS:
        key = spec["key"]
        if key not in form_data:
            continue
        value = "" if form_data.get(key) is None else str(form_data.get(key)).strip()
        kind = spec["kind"]
        if kind == "yn":
            if value.lower() not in ("y", "n", "yes", "no", "true", "false"):
                errors[key] = "Choose Yes or No."
        elif kind == "int":
            try:
                number = int(value)
            except ValueError:
                errors[key] = "Must be a whole number."
                continue
            minimum = spec.get("minimum")
            maximum = spec.get("maximum")
            if minimum is not None and number < minimum:
                errors[key] = f"Must be at least {minimum}."
            if maximum is not None and number > maximum:
                errors[key] = f"Must be at most {maximum}."
        elif kind == "enum" and not spec.get("allow_custom"):
            allowed = {choice[0] for choice in spec["choices"]}
            if value not in allowed:
                errors[key] = "Choose one of the listed options."
    return errors


def normalize_abcde_yn(value):
    text = str(value or "").strip().lower()
    if text in ("y", "yes", "true", "1", "on"):
        return "y"
    return "n"
