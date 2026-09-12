"""Describe Identify → Rip → Transcode → Copy for the UI.

Movie discs: MakeMKV (optional HandBrake) then Completed.
Audio CDs: MusicBrainz then abcde into Completed.
"""
from arm.config.config_utils import yaml_is_true

_STATUS_FALLBACK = {
    "success": "Success",
    "fail": "Failed",
    "waiting_manual": "Waiting for Title",
    "waiting_playlist": "Pick Playlist",
    "active": "Active",
    "ripping": "Ripping",
    "waiting": "Waiting",
    "info": "Reading Disc",
    "transcoding": "Transcoding",
    "waiting_transcode": "Waiting to Transcode",
}


def _lang_name(code):
    names = {
        "eng": "English",
        "spa": "Spanish",
        "fre": "French",
        "ger": "German",
        "ita": "Italian",
        "jpn": "Japanese",
    }
    code = str(code or "eng").strip().lower()
    return names.get(code, code or "English")


def movie_pipeline(settings):
    """Live movie path from current arm.yaml values."""
    settings = settings or {}
    skip = yaml_is_true(settings.get("SKIP_TRANSCODE"))
    main = yaml_is_true(settings.get("MAINFEATURE"))
    method = str(settings.get("RIPMETHOD") or "mkv").strip().lower()
    lang = _lang_name(settings.get("MKV_LANG"))
    use_ffmpeg = yaml_is_true(settings.get("USE_FFMPEG"))
    encoder = "FFmpeg" if use_ffmpeg else "HandBrake"

    identify = "Identify the title (OMDb or TMDb)."
    if main:
        tracks = "Pick one main title (longest/largest playlist)."
    else:
        tracks = "Rip titles inside the min/max length window."
    if method == "backup":
        rip = "MakeMKV copies the full decrypted disc to Raw."
    else:
        rip = f"MakeMKV rips selected titles to Raw ({lang} audio/subs)."
    eject = "Eject so the drive can take the next disc."
    if skip:
        copy = "Copy Raw to Completed. HandBrake is off."
        steps = [identify, tracks, rip, eject, copy]
        sentence = (
            f"Movie: identify → MakeMKV ({'one title' if main else 'matching titles'}, "
            f"{lang}) → eject → Completed. {encoder} is off."
        )
    else:
        transcode = f"{encoder} reads Raw and writes Transcode."
        copy = "Copy Transcode to Completed."
        steps = [identify, tracks, rip, eject, transcode, copy]
        sentence = (
            f"Movie: identify → MakeMKV → eject → {encoder} → Completed."
        )
    return {
        "kind": "movie",
        "sentence": sentence,
        "steps": steps,
        "skip_transcode": skip,
        "encoder": encoder,
    }


def music_pipeline(settings=None):
    """Audio CD path: MusicBrainz, then abcde into Completed."""
    _ = settings
    steps = [
        "Identify the album with MusicBrainz.",
        "abcde rips every track into Completed (music folder).",
    ]
    return {
        "kind": "music",
        "sentence": "CD: MusicBrainz identifies the album → abcde rips all tracks to Completed.",
        "steps": steps,
    }


def job_workflow_status(job):
    """Status label that names the tool currently running."""
    if job is None:
        return ""
    status = str(getattr(job, "status", "") or "").lower()
    disc = str(getattr(job, "disctype", "") or "").lower()
    video = str(getattr(job, "video_type", "") or "").lower()
    is_music = disc == "music" or video == "music"
    use_ffmpeg = False
    config = getattr(job, "config", None)
    if config is not None:
        use_ffmpeg = bool(getattr(config, "USE_FFMPEG", False))
    encoder = "FFmpeg" if use_ffmpeg else "HandBrake"
    if is_music:
        if status == "info":
            return "MusicBrainz"
        if status == "ripping":
            return "abcde"
    if status == "info":
        return "Identify"
    if status == "ripping":
        return "MakeMKV"
    if status == "transcoding":
        return encoder
    if status == "waiting_transcode":
        return f"Waiting for {encoder}"
    mapped = _STATUS_FALLBACK.get(status)
    if mapped:
        return mapped
    if not status:
        return ""
    return status.replace("_", " ").title()
