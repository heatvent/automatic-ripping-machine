"""Normalize movie and music titles for display and filesystem paths.

Keep letters, numbers, apostrophes, commas, ampersands, and other readable
marks. Replace only characters that break paths or Windows filenames.
"""

import re
import unicodedata

WINDOWS_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

_CHAR_MAP = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u00b4": "'",
    "`": "'",
    "\u201c": "'",
    "\u201d": "'",
    "\u201e": "'",
    "\u201f": "'",
    "\u00ab": "'",
    "\u00bb": "'",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u00a0": " ",
    "\u202f": " ",
    "\u2007": " ",
    "\u2009": " ",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
    "\u2026": "...",
    "\u2122": "",
    "\u00ae": "",
    "\u00a9": "",
    "_": " ",
})

_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_HYPHEN = re.compile(r"-{2,}")
_REPEAT_DASH = re.compile(r"(?: - ){2,}")
_TRAILING_JUNK = re.compile(r"[\s.\-]+$")
_LEADING_JUNK = re.compile(r"^[\s.\-]+")
_TRADEMARKS = ("\u2122", "\u00ae", "\u00a9", "™", "®", "©")


def normalize_title_text(value):
    """Unicode and punctuation cleanup that still reads as the original title."""
    if value is None:
        return ""
    text = str(value).replace("\x00", "")
    for mark in _TRADEMARKS:
        text = text.replace(mark, "")
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_CHAR_MAP)
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C"):
            if char in "\t\n\r":
                cleaned.append(" ")
            continue
        cleaned.append(char)
    return "".join(cleaned)


def clean_for_filename(value, fallback="untitled", max_length=180):
    """Make a title safe as a folder or file name without flattening it.

    Spaces stay spaces so media servers see ``Movie Title (2010)``. Apostrophes,
    commas, ampersands, and non-Latin letters are kept. Colons become `` - ``.
    Slashes become hyphens (``AC/DC`` → ``AC-DC``).
    """
    text = normalize_title_text(value)
    text = text.replace(" : ", " - ").replace(":", " - ")
    text = text.replace("/", "-").replace("\\", "-")
    text = "".join(char for char in text if char not in '<>"|?*')
    text = _MULTI_SPACE.sub(" ", text)
    text = _REPEAT_DASH.sub(" - ", text)
    text = _MULTI_HYPHEN.sub("-", text)
    text = _LEADING_JUNK.sub("", text)
    text = _TRAILING_JUNK.sub("", text)
    text = text.strip()
    if not text:
        return fallback
    if max_length and len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0].rstrip(" -.")
        if not text:
            text = fallback
    stem = text.split(".")[0].upper()
    if stem in WINDOWS_RESERVED or text.upper() in WINDOWS_RESERVED:
        text = f"{text} disc"
    return text
