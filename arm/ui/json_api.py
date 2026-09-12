"""JSON helpers for /json AJAX (Home cards, History search/delete, job actions).

Also talks to OMDb/TMDb when the UI looks up titles. Keep /json from 500ing:
a crash here blanks every Home card until the next successful poll.
"""
import os
import signal
import threading
import re
import html
from collections import deque
from pathlib import Path
import datetime
import psutil
from sqlalchemy import or_
from flask import request
from time import time, strftime, gmtime, sleep

from arm.config.makemkv_select import (
    choose_main_feature_track,
    find_similar_movie_titles,
    format_hms,
)
import arm.config.config as cfg
from arm.models.config import Config
from arm.models.job import Job, JobState, JOB_STATUS_FINISHED
from arm.models.track import Track
from arm.ui import app, db
from arm.ui.forms import ChangeParamsForm
from arm.ui.utils import job_id_validator, database_updater, authenticated_state
from arm.ui.settings import DriveUtils as drive_utils # noqa E402
from arm.ripper import music_brainz
from arm.ui.workflow import job_workflow_status


def _job_minlength(job):
    if job.config is None:
        return 0
    try:
        return int(job.config.MINLENGTH or 0)
    except (TypeError, ValueError):
        return 0


def playlist_picks_for_job(job):
    """Titles ARM thinks are playlist clones, for the Home picker."""
    tracks = list(job.tracks) if job.tracks is not None else []
    similar = find_similar_movie_titles(tracks, _job_minlength(job))
    if not similar:
        similar = [track for track in tracks if track.process] or tracks
    suggested = choose_main_feature_track(similar)
    picks = []
    for track in similar:
        suggested_match = (
            suggested is not None and track.track_id == suggested.track_id
        )
        picks.append({
            "track_id": track.track_id,
            "track_number": str(track.track_number),
            "length": int(track.length or 0),
            "length_hms": format_hms(track.length),
            "chapters": int(track.chapters or 0),
            "filesize": int(track.filesize or 0),
            "suggested": bool(suggested_match),
            "process": bool(track.process),
        })
    return picks


def select_playlist(job_id, track=""):
    """Confirm which MakeMKV title(s) to rip after playlist obfuscation."""
    json_return = {
        "success": False,
        "job": job_id,
        "mode": "select_playlist",
    }
    try:
        job = Job.query.get(int(job_id))
    except (TypeError, ValueError):
        json_return["error"] = "Invalid job"
        return json_return
    if job is None:
        json_return["error"] = "Job not found"
        return json_return
    if job.status != JobState.PLAYLIST_WAIT.value:
        json_return["error"] = "Job is not waiting for a playlist pick"
        return json_return
    similar = find_similar_movie_titles(list(job.tracks or []), _job_minlength(job))
    choice = str(track or "").strip().lower()
    wanted = set()
    if choice in {"all", "similar"}:
        wanted = {str(item.track_number) for item in similar}
    elif choice in {"", "suggested"}:
        suggested = choose_main_feature_track(similar or list(job.tracks or []))
        if suggested is not None:
            wanted = {str(suggested.track_number)}
    else:
        wanted = {part.strip() for part in str(track).split(",") if part.strip()}
    if not wanted:
        json_return["error"] = "No titles selected"
        return json_return
    for item in job.tracks:
        item.process = str(item.track_number) in wanted
        item.main_feature = item.process and len(wanted) == 1
    job.manual_start = True
    db.session.commit()
    json_return["success"] = True
    json_return["tracks"] = sorted(wanted)
    return json_return


def get_x_jobs(job_status):
    """
    function for getting all Failed/Successful jobs \n
    or\n
    currently active jobs from the database\n

    :return: dict/json
    """
    success = False
    if job_status == "joblist":
        finished_values = [js.value for js in JOB_STATUS_FINISHED]
        jobs = db.session.query(Job).filter(
            or_(Job.status.is_(None), ~Job.status.in_(finished_values))
        ).all()
    elif JobState(job_status) in JOB_STATUS_FINISHED:
        jobs = Job.query.filter_by(status=job_status)
    else:
        raise ValueError(f"{job_status} is not a valid option")

    job_results = {}
    i = 0
    for j in jobs:
        job_results[i] = {}
        try:
            job_log = os.path.join(cfg.arm_config['LOGPATH'], str(j.logfile or ""))
            process_logfile(job_log, j, job_results[i])
        except Exception as err:  # noqa: BLE001
            app.logger.debug("process_logfile failed for job %s: %s", j.job_id, err)
        try:
            job_results[i]['config'] = j.config.get_d()
        except AttributeError:
            job_results[i]['config'] = {}
            app.logger.debug("couldn't get config")

        for key, value in j.get_d().items():
            if key != "config":
                # Job.get_d() stringifies None as "None", which the UI then
                # treats as a real title/year/poster and fails to refresh.
                text = "" if value in (None, "None", "null") else str(value)
                job_results[i][str(key)] = text
        job_results[i]["tool_status"] = job_workflow_status(j)
        if j.start_time:
            job_results[i]["start_display"] = format_job_start(j.start_time)
        if not job_results[i].get("poster_url"):
            cover = music_brainz.cover_url_for_release(job_results[i].get("crc_id"))
            if cover:
                job_results[i]["poster_url"] = cover
        if j.status == JobState.PLAYLIST_WAIT.value:
            job_results[i]["playlist_picks"] = playlist_picks_for_job(j)
        i += 1
    if jobs:
        app.logger.debug("jobs  - we have " + str(len(job_results)) + " jobs")
        success = True

    # Get authentication state
    authenticated = authenticated_state()

    payload = {"success": success,
               "mode": job_status,
               "results": job_results,
               "arm_name": cfg.arm_config['ARM_NAME'],
               "authenticated": authenticated}
    return payload


def format_job_start(start_time):
    """Format a job start timestamp with Settings → General → Date Format."""
    if not start_time:
        return ""
    pattern = cfg.arm_config.get("DATE_FORMAT") or "%m-%d-%Y %H:%M:%S"
    try:
        return start_time.strftime(pattern)
    except (TypeError, ValueError):
        return str(start_time)


def process_logfile(logfile, job, job_results):
    """
        Decide if we need to process HandBrake or MakeMKV
        :param logfile: the logfile for parsing
        :param job: the Job class
        :param job_results: the {} of
        :return: should be dict for the json api
    """
    app.logger.debug(f"Disc Type: {job.disctype}, Status: {job.status}")
    if job.disctype in {"dvd", "bluray"}:
        if job.status == JobState.VIDEO_RIPPING.value:
            app.logger.debug("using mkv - " + logfile)
            return process_makemkv_logfile(job, job_results)
        if job.status == JobState.TRANSCODE_ACTIVE.value:
            app.logger.debug("using handbrake")
            return process_handbrake_logfile(logfile, job, job_results)
    if job.disctype == "music" and job.status == JobState.AUDIO_RIPPING.value:
        app.logger.debug("using audio disc")
        return process_audio_logfile(job.logfile, job, job_results)
    return job_results


def percentage(part, whole):
    """percent calculator"""
    whole_value = float(whole)
    if whole_value == 0:
        return 0.0
    return 100 * float(part) / whole_value


def find_last_regex_match(pattern, iterable):
    """
    Find the last matching regex pattern in a given iterable
    """
    regex = re.compile(pattern)
    if isinstance(iterable, (list, tuple, str)):
        reversed_iterable = reversed(iterable)
    else:
        reversed_iterable = reversed(list(iterable))
    for item in reversed_iterable:
        retval = regex.search(item)
        if retval:
            return retval
    return None


def process_makemkv_logfile(job, job_results):
    """
    Process the logfile and find current status and job progress percent\n
    :return: job_results dict
    """
    job_progress_status = None
    job_stage_index = None
    batch_log_path = os.path.join(cfg.arm_config['LOGPATH'], 'progress', str(job.job_id)) + '.log.batchinfo'
    lines = read_log_line(os.path.join(cfg.arm_config['LOGPATH'], 'progress', str(job.job_id)) + '.log')
    batch_index = read_log_line(batch_log_path)
    # Correctly get last entry for progress bar

    job_progress_status = find_last_regex_match(r"PRGV:(\d{3,}),(\d+),(\d{3,})", lines)
    job_stage_index = find_last_regex_match(r"PRGC:(\d+),(\d+),\"([\w -]{2,})\"", lines)
    job_batch_info = find_last_regex_match(r"BINF:(\d{10}),(\d+),(\d+),(\d+)", batch_index)

    if job_progress_status is not None:
        app.logger.debug(f"job_progress_status: {job_progress_status}")
        job.progress = job_results['progress'] = \
            f"{percentage(job_progress_status.group(1), job_progress_status.group(3)):.2f}"
        job.progress_round = percentage(job_progress_status.group(1),
                                        job_progress_status.group(3))
        # The ETA calc needs the batch-info (BINF) file, but that file is only
        # written further down, in the `job_stage_index` block. On the first
        # poll for a job it does not exist yet, so `job_batch_info` is None and
        # `job_batch_info.group(1)` raises
        # "'NoneType' object has no attribute 'group'", which 500s the whole
        # /json endpoint and leaves Home cards blank. Because the
        # crash happens *before* the code that creates the BINF file, it never
        # bootstraps and stays broken for the entire rip. Guard it (and the
        # divide-by-zero when progress is still 0) and report an Unknown ETA
        # until the batch info is available.
        if job_batch_info is not None and float(job.progress) > 0:
            job_start_time = int(job_batch_info.group(1))
            current_time = int(time())
            elapsed_time = current_time - job_start_time
            total_time = int((elapsed_time * 100) / float(job.progress))
            time_remaining = total_time - elapsed_time
            app.logger.debug(f"ETA values for job {job.job_id}: Elapsed seconds: {elapsed_time}, "
                             f"Percent: {job.progress}, "
                             f"Projected time: {total_time}, "
                             f"Time remaining: {time_remaining}"
                             )
            job.eta = strftime("%Hh%Mm%Ss", gmtime(time_remaining))
        else:
            job.eta = "Unknown"
    else:
        app.logger.debug(f"Job [{job.job_id}] MakeMKV status not defined - setting progress to 0%")
        job.progress = job.progress_round = job_results['progress'] = 0
        job.eta = "Unknown"

    if job_stage_index is not None:
        try:
            if job_batch_info.group(4) != job_stage_index.group(1):
                app.logger.debug(f"Appending new batch position info for job {job.job_id}: "
                                 f"BINF:{int(time())},"
                                 f"{job_batch_info.group(2)},"
                                 f"{job_batch_info.group(3)},"
                                 f"{job_stage_index.group(1)}"
                                 )
                with open(batch_log_path, 'a') as f:
                    f.write(f"\nBINF:{int(time())},"
                            f"{job_batch_info.group(2)},"
                            f"{job_batch_info.group(3)},"
                            f"{job_stage_index.group(1)}"
                            )
            app.logger.debug(f"job_stage_index: {job_stage_index}")
            current_index = f"Track {job_batch_info.group(2)}/{job_batch_info.group(3)}<br>{job_stage_index.group(3)}"
            job.stage = job_results['stage'] = current_index
            db.session.commit()
        except Exception as error:
            job.stage = f"Unknown -  {error}"

    return job_results


def process_handbrake_logfile(logfile, job, job_results):
    """
    process a logfile looking for HandBrake or FFMPEG progress
    :param logfile: the logfile for parsing
    :param job: the Job class
    :param job_results: the {} of
    :return: should be dict for the json api
    """
    job_status = None
    job_status_index = None
    ffmpeg_job_status = None
    lines = read_log_line(logfile)
    for line in lines:
        # This correctly get the very last ETA and % for HandBrake
        hb_search = re.search(r"Encoding: task (\d of \d), (\d{1,3}\.\d{2}) %.*?"
                              r"\((\d+\.\d+) fps, avg (\d+\.\d+) fps, ETA ([\dhms]*?)\)(?!\\rEncod)", str(line))
        if hb_search:
            job_status = hb_search

        hb_index_search = re.search(r"Processing track #(\d{1,2}) of (\d{1,2})"
                                    r"(?!.*Processing track #)", str(line))
        if hb_index_search:
            job_status_index = hb_index_search

        # Check for FFMPEG status
        ffmpeg_search = re.search(r"ARM: .* - (\d{1,3}\.\d{2})%", str(line))
        if ffmpeg_search:
            ffmpeg_job_status = ffmpeg_search

    # Check ARM can read the Handbrake library and get a status
    if job_status is not None:
        app.logger.debug(job_status.group())
        job.stage = job_status.group(1)
        job.progress = job_status.group(2)
        job.cur_fps = job_status.group(3)
        job.avg_fps = job_status.group(4)
        job.eta = job_status.group(5)
        job.progress_round = int(float(job.progress))
    elif ffmpeg_job_status is not None:
        job.stage = "Transcoding"
        job.progress = ffmpeg_job_status.group(1)
        job.eta = "Unknown"
        job.progress_round = int(float(job.progress))
    else:
        app.logger.debug(f"Job [{job.job_id}] handbrake/ffmpeg status not defined - setting progress to 0%")
        job.stage = "Unknown"
        job.progress = job.progress_round = 0
        job.eta = "Unknown"

    job_results['stage'] = job.stage
    job_results['progress'] = job.progress
    job_results['eta'] = job.eta
    job_results['cur_fps'] = getattr(job, 'cur_fps', 0)
    job_results['avg_fps'] = getattr(job, 'avg_fps', 0)
    job_results['progress_round'] = int(float(job_results['progress']))

    if job_status_index:
        try:
            current_index = int(job_status_index.group(1))
            job.stage = job_results['stage'] = f"{job.stage} - {current_index}/{job.no_of_titles}"
        except Exception as error:
            app.logger.debug(f"Problem finding the current track {error}")
            job.stage = f"{job.stage} - %0%/%0%"
    else:
        app.logger.debug("Cant find index")

    return job_results


_ABCDE_ENCODE_RE = re.compile(r"Encoding track\s+(\d+)\s+of\s+(\d+)", re.I)
_ABCDE_TAG_RE = re.compile(r"Tagging track\s+(\d+)\s+of\s+(\d+)", re.I)
_ABCDE_GRAB_RE = re.compile(r"Grabbing track\s+(\d+)", re.I)
_ABCDE_ENTIRE_RE = re.compile(r"Grabbing entire CD - tracks:\s+(.+)")
_ABCDE_FINISHED_RE = re.compile(r"^Finished\.?$")


def parse_abcde_progress(lines, known_track_count=None):
    """Read abcde log lines and return (current_track, total_tracks, finished)."""
    current = None
    try:
        total = int(known_track_count or 0) or None
    except (TypeError, ValueError):
        total = None
    finished = False
    for raw in lines or []:
        line = str(raw).strip()
        entire = _ABCDE_ENTIRE_RE.search(line)
        if entire:
            names = entire.group(1).split()
            if names:
                total = len(names)
        counted = _ABCDE_ENCODE_RE.search(line) or _ABCDE_TAG_RE.search(line)
        if counted:
            current = int(counted.group(1))
            total = int(counted.group(2))
            continue
        grab = _ABCDE_GRAB_RE.search(line)
        if grab:
            current = int(grab.group(1))
            continue
        if _ABCDE_FINISHED_RE.match(line):
            finished = True
    if finished and total:
        current = total
    return current, total, finished


def process_audio_logfile(logfile, job, job_results):
    """
    Process audio disc logs to show current ripping tracks
    :param logfile: will come in as only the bare logfile, no path
    :param job: current job, so we can update the stage
    :param job_results:
    :return:
    """
    if not logfile:
        return job_results
    lines = read_all_log_lines(os.path.join(cfg.arm_config["LOGPATH"], logfile))
    try:
        current, total, finished = parse_abcde_progress(lines, job.no_of_titles)
        if total and not job.no_of_titles:
            job.no_of_titles = total
        if finished and total:
            job.stage = f"Track {total}/{total}"
            job.progress = 100
            job.eta = "0:00:00"
        elif current and total:
            job.stage = f"Track {current}/{total}"
            job.progress = round(percentage(current, total))
            job.eta = calc_process_time(job.start_time, current, total)
        elif current:
            job.stage = f"Track {current}"
            job.progress = 0
            job.eta = "Unknown"
        else:
            job.stage = "Starting"
            job.progress = 0
            job.eta = "Unknown"
        job.progress_round = int(job.progress or 0)
        job_results["stage"] = job.stage
        job_results["progress"] = job.progress
        job_results["progress_round"] = job.progress_round
        job_results["eta"] = job.eta
    except Exception as error:  # noqa: BLE001
        app.logger.debug("Error processing abcde logfile. Error dump"
                         f"-  {error}", exc_info=True)
        job.stage = "Unknown"
        job.eta = "Unknown"
        job.progress = job.progress_round = 0
    return job_results


def _format_eta_hms(seconds):
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def calc_process_time(starttime, cur_iter, max_iter):
    """Rough ETA from how far through a known track count we are."""
    try:
        current = int(cur_iter)
        total = int(max_iter)
        if current <= 0 or total <= 0 or starttime is None:
            return "Unknown"
        if current > total:
            current = total
        elapsed = (datetime.datetime.now() - starttime).total_seconds()
        if elapsed < 0:
            return "Unknown"
        estimated_total = (elapsed / current) * total
        remaining = estimated_total - elapsed
        if remaining < 0:
            remaining = 0
        finish = datetime.datetime.now() + datetime.timedelta(seconds=int(remaining))
        return f"{_format_eta_hms(remaining)} ({finish.strftime('%H:%M:%S')})"
    except (TypeError, ValueError, OverflowError, OSError):
        app.logger.debug("Failed to calculate audio ETA", exc_info=True)
        return "Unknown"


def read_log_line(log_file: os.PathLike):
    """
    :param log_file: path to log file
    :return: the last 20 lines of the file at ``log_file``
    """
    try:
        with open(log_file, encoding="utf8", errors="ignore") as read_log_file:
            lines = deque(read_log_file, maxlen=100)
    except OSError:
        app.logger.debug(f"Error while reading {log_file}, unable to calculate ETA")
        lines = ["", ""]
    return lines


def read_all_log_lines(log_file):
    """Try to catch if the logfile gets delete before the job is finished"""
    try:
        with open(log_file, encoding="utf8", errors='ignore') as read_log_file:
            line = read_log_file.readlines()
    except FileNotFoundError:
        line = ""
    return line


def escape_sql_like(value):
    """Escape LIKE wildcards so title search can keep spaces and punctuation."""
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def search(search_query):
    """ Queries ARMui db for the movie/show matching the query"""
    needle = " ".join(str(search_query or "").split())
    if not needle:
        return {'success': True, 'mode': 'search', 'results': {}}
    safe_search = f"%{escape_sql_like(needle)}%"
    app.logger.debug('-' * 30)

    posts = db.session.query(Job).filter(Job.title.like(safe_search, escape="\\")).all()
    search_results = {}
    i = 0
    for job in posts:
        search_results[i] = {}
        try:
            search_results[i]['config'] = job.config.get_d()
        except AttributeError:
            search_results[i]['config'] = {}
            app.logger.debug("couldn't get config")

        for key, value in iter(job.get_d().items()):
            if key != "config":
                text = "" if value in (None, "None", "null") else str(value)
                search_results[i][str(key)] = text
        i += 1
    return {'success': True, 'mode': 'search', 'results': search_results}


def delete_job(job_id, mode):
    """
    json api version of delete jobs\n
    :param job_id: job id to delete || str "all"/"title"
    :param str mode: should always be 'delete'
    :return: json/dict to be returned if success or fail
    """
    try:
        json_return = {}
        app.logger.debug(f"job_id= {job_id}")
        # Find the job the user wants to delete
        if mode == 'delete' and job_id is not None:
            # User wants to wipe the whole database
            # Make a backup and everything
            # The user can only access this by typing it manually
            if job_id == 'all':
                #  # if this gets put in final, the DB will need optimised
                #  if os.path.isfile(cfg.arm_config['DBFILE']):  # noqa: S125
                #    # Make a backup of the database file
                #    cmd = f"cp {cfg.arm_config['DBFILE']} {cfg.arm_config['DBFILE'])}.bak"
                #    app.logger.info(f"cmd  -  {cmd}")
                #    os.system(cmd)
                #  Track.query.delete()
                #  Job.query.delete()
                #  Config.query.delete()
                #  db.session.commit()
                app.logger.debug("Admin is requesting to delete all jobs from database!!! No deletes went to db")
                json_return = {'success': True, 'job': job_id, 'mode': mode}
            elif job_id == "title":
                #  The user can only access this by typing it manually
                #  This shouldn't be left on when on a full server
                # This causes db corruption!
                # logfile = request.args['title']
                # Job.query.filter_by(title=logfile).delete()
                # db.session.commit()
                # app.logger.debug("Admin is requesting to delete all jobs with (x) title.")
                json_return = {'success': True, 'job': job_id, 'mode': mode}
                # Not sure this is the greatest way of handling this
            else:
                try:
                    post_value = int(job_id)
                    app.logger.debug(f"Admin requesting delete job {job_id} from database!")
                except ValueError:
                    app.logger.debug("Admin is requesting to delete a job but didnt provide a valid job ID")
                    return {'success': False, 'job': 'invalid', 'mode': mode, 'error': 'Not a valid job'}
                else:
                    app.logger.debug("No errors: job_id=" + str(post_value))
                    drive_utils.job_cleanup(job_id)
                    Track.query.filter_by(job_id=job_id).delete()
                    Job.query.filter_by(job_id=job_id).delete()
                    Config.query.filter_by(job_id=job_id).delete()
                    db.session.commit()
                    app.logger.debug(f"Admin deleting  job {job_id} was successful")
                    json_return = {'success': True, 'job': job_id, 'mode': mode}
    # If we run into problems with the database changes
    # error out to the log and roll back
    except Exception as err:
        db.session.rollback()
        app.logger.error(f"Error:db-1 {err}")
        json_return = {'success': False}

    return json_return


def generate_log(logpath, job_id):
    """
    Generate log for json api and return it in a valid form\n
    :param str logpath:
    :param str job_id:
    :return:
    """
    try:
        job = Job.query.get(int(job_id))
    except Exception:
        app.logger.debug(f"Cant find job {job_id} ")
        job = None

    app.logger.debug("in logging")
    if job is None or job.logfile is None or job.logfile == "":
        app.logger.debug(f"Cant find the job {job_id}")
        return {'success': False, 'job': job_id, 'log': 'Not found'}
    # Assemble full path
    fullpath = os.path.join(logpath, job.logfile)
    # Check if the logfile exists
    my_file = Path(fullpath)
    if not my_file.is_file():
        # logfile doesnt exist throw out error template
        app.logger.debug("Couldn't find the logfile requested, Possibly deleted/moved")
        return {'success': False, 'job': job_id, 'log': 'File not found'}
    try:
        with open(fullpath) as full_log:
            read_log = full_log.read()
    except Exception:
        try:
            with open(fullpath, encoding="utf8", errors='ignore') as full_log:
                read_log = full_log.read()
        except Exception:
            app.logger.debug("Cant read logfile. Possibly encoding issue")
            return {'success': False, 'job': job_id, 'log': 'Cant read logfile'}
    html_escaped_log = html.escape(read_log)
    title_year = str(job.title) + " (" + str(job.year) + ") - file: " + str(job.logfile)
    return {'success': True, 'job': job_id, 'mode': 'logfile', 'log': html_escaped_log,
            'escaped': True, 'job_title': title_year}


def abandon_job(job_id):
    """
    json api abandon job\n
    :param str job_id: the job id
    :return: json/dict
    """
    json_return = {
        'success': False,
        'job': job_id,
        'mode': 'abandon'
    }
    if not job_id_validator(job_id):
        return json_return

    job = Job.query.get(int(job_id))
    if job is None:
        json_return["Error"] = "Job not found"
        return json_return
    job.status = JobState.FAILURE.value
    try:
        terminate_process(job.pid)
    except Exception as err:
        db.session.rollback()
        json_return["Error"] = str(err)
        json_return['success'] = False
        app.logger.debug("Job ERROR: %s couldn't be abandoned. Reverting db changes - %s",
                         job.pid, json_return["Error"])
        return json_return
    from arm.ripper.utils import clear_abcde_work_dirs, stop_stray_abcde
    stop_stray_abcde(job.devpath)
    if str(job.disctype or "").lower() == "music" or str(job.video_type or "").lower() == "music":
        clear_abcde_work_dirs()
    job.eject()
    json_return['success'] = True
    db.session.commit()
    return json_return


def terminate_process(pid):
    """
    Terminates the process associated with a given pid.
    :param pid: Process ID (int)
    :raises: ValueError if access is denied
    """
    if pid is None:
        message = "PID not found for job."
        app.logger.warning(message)
        return
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        message = f"Process id {pid} was not found. Job has already been terminated."
        app.logger.warning(message)
        return
    except psutil.AccessDenied as err:
        message = f"Access denied abandoning job: {pid}!"
        app.logger.error(message)
        raise ValueError(message) from err
    procs = parent.children(recursive=True)
    procs.append(parent)
    for proc in procs:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as err:
            message = f"Access denied abandoning job: {pid}!"
            app.logger.error(message)
            raise ValueError(message) from err
    _gone, alive = psutil.wait_procs(procs, timeout=5)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    app.logger.debug("Job with PID %s was terminated (%s process(es)).", pid, len(procs))


def change_job_params(config_id):
    """Update values for job"""
    if request.method != 'POST':
        return {'success': False, 'error': 'POST required', 'form': 'change_job_params'}
    job = Job.query.get(config_id)
    if job is None or job.config is None:
        return {'success': False, 'error': 'Job not found', 'form': 'change_job_params'}
    config = job.config
    form = ChangeParamsForm()
    app.logger.debug("Before valid")
    if form.validate():
        app.logger.debug("Valid")
        job.disctype = format(form.DISCTYPE.data)
        config.MINLENGTH = format(form.MINLENGTH.data)
        config.MAXLENGTH = format(form.MAXLENGTH.data)
        config.RIPMETHOD = format(form.RIPMETHOD.data)
        config.MAINFEATURE = bool(form.MAINFEATURE.data)
        args = {'disctype': job.disctype}
        message = f'Parameters changed. Rip Method={config.RIPMETHOD}, Main Feature={config.MAINFEATURE},' \
                  f'Minimum Length={config.MINLENGTH}, Maximum Length={config.MAXLENGTH}, Disctype={job.disctype}'
        database_updater(args, job)

        return {'message': message, 'form': 'change_job_params', "success": True}
    return {'return': '', 'success': False}


def restart_ui():
    """Restart only the ARM UI process. Runit/systemd will bring it back.

    Does not kill ripper processes (unlike the old pkill python3).
    """
    app.logger.info("ARM UI restart requested")

    def _signal_self():
        sleep(0.4)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_signal_self, daemon=True).start()
    return {
        'success': True,
        'mode': 'restart',
        'message': 'Restarting ARM UI',
    }
