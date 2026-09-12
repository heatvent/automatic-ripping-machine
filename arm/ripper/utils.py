#!/usr/bin/env python3
"""Collection of utility functions"""
import os
import logging
import subprocess
import shutil
import time
import random
from logging import Logger
from pathlib import Path, PurePath
from math import ceil

import bcrypt
import requests
import apprise
import psutil

from netifaces import interfaces, ifaddresses, AF_INET

import arm.config.config as cfg
from arm.ripper.ProcessHandler import arm_subprocess
from arm.ui import db  # needs to be imported before models
from arm.models.job import Job, JobState, job_holds_drive
from arm.models.track import Track
from arm.models.user import User
from arm.models.system_drives import SystemDrives
from arm.ripper import apprise_bulk
from arm.title_format import clean_for_filename

NOTIFY_TITLE = "ARM notification"


class RipperException(Exception):
    pass


def format_job_errors(errors):
    """Turn job.errors into a single message.

    job.errors is a Text column, so joining it as a sequence splits the
    message into letters.
    """
    if not errors:
        return ""
    if isinstance(errors, str):
        return errors
    if isinstance(errors, (list, tuple, set)):
        return ", ".join(str(item) for item in errors)
    return str(errors)


def should_wait_for_manual(job):
    """True when this job should pause for a UI title override."""
    if not job.config.MANUAL_WAIT:
        return False
    if not getattr(job, "manual_mode", False):
        return False
    return True


def notify(job, title: str, body: str):
    """Send outbound alerts (Apprise, IFTTT, Pushover, Pushbullet, bash, JSON).

    This does not write an in-app inbox. Home and History are the on-machine
    view of jobs; Settings → Notifications only configures these remote sends.
    Failures are logged and ripping continues.
    """

    # Prepend Site Name if configured
    if cfg.arm_config["ARM_NAME"] != "":
        title = f"[{cfg.arm_config['ARM_NAME']}] - {title}"

    # append Job ID if configured
    if cfg.arm_config["NOTIFY_JOBID"] and job is not None:
        title = f"{title} - {job.job_id}"

    logging.debug(f"apprise message, title: {title} body: {body}")

    bash_notify(cfg.arm_config, title, body)

    # Sent to remote sites
    # Create an Apprise instance
    apobj = apprise.Apprise()
    if cfg.arm_config["PB_KEY"] != "":
        apobj.add('pbul://' + str(cfg.arm_config["PB_KEY"]))
    if cfg.arm_config["IFTTT_KEY"] != "":
        apobj.add('ifttt://' + str(cfg.arm_config["IFTTT_KEY"]) + "@" + str(cfg.arm_config["IFTTT_EVENT"]))
    if cfg.arm_config["PO_USER_KEY"] != "":
        apobj.add('pover://' + str(cfg.arm_config["PO_USER_KEY"]) + "@" + str(cfg.arm_config["PO_APP_KEY"]))
    if cfg.arm_config["JSON_URL"] != "":
        apobj.add(str(cfg.arm_config["JSON_URL"]).replace("http://", "json://").replace("https://", "jsons://"))
    try:
        apobj.notify(body, title=title)
    except Exception as error:  # noqa: E722
        logging.error(f"Failed sending notifications. error:{error}. Continuing processing...")

    # Bulk send notifications, using the config set on the ripper config page
    if cfg.arm_config["APPRISE"] != "":
        try:
            apprise_bulk.apprise_notify(cfg.arm_config["APPRISE"], title, body)
            logging.debug(f"apprise-config: {cfg.arm_config['APPRISE']}")
        except Exception as error:  # noqa: E722
            logging.error(f"Failed sending apprise notifications. {error}")


def bash_notify(cfg, title, body):
    """Optional local script from Settings → Notifications (BASH_SCRIPT)."""
    if cfg['BASH_SCRIPT'] != "":
        arm_subprocess(["/usr/bin/env", "bash", cfg['BASH_SCRIPT'], title, body])


def notify_entry(job):
    """Outbound alert when a disc is identified, before ripping starts."""
    if job.disctype in ["dvd", "bluray"]:
        if cfg.arm_config["UI_BASE_URL"] == "":
            display_address = (f"http://{check_ip()}:{job.config.WEBSERVER_PORT}")
        else:
            display_address = str(cfg.arm_config["UI_BASE_URL"])
        # Send the notifications
        notify(job, NOTIFY_TITLE,
               f"Found disc: {job.title}. Disc type is {job.disctype}. Main Feature is {job.config.MAINFEATURE}."
               f"Edit entry here: {display_address}/jobdetail?job_id={job.job_id}")
    elif job.disctype == "music":
        notify(job, NOTIFY_TITLE, f"Found music CD: {job.label}. Ripping all tracks.")
    elif job.disctype == "data":
        notify(job, NOTIFY_TITLE, "Found data disc.  Copying data.")
    else:
        raise RipperException("Could not determine disc type")


def sleep_check_process(process_str, max_processes, sleep=(20, 120, 10)):
    """
    New function to check for max_transcode from job.config and force obey limits\n
    :param str process_str: The process string from arm.yaml
    :param int max_processes: The user defined limit for maximum transcodes
    :param (tuple, int) sleep: tuple: (min sleep time, max sleep time, step) or sleep time as int.
    :return bool: when we have space in the transcode queue
    """
    if max_processes <= 0:
        return False  # sleep limit disabled
    if isinstance(sleep, int):
        sleep = (sleep, sleep + 1, 1)
    if not isinstance(sleep, tuple):
        raise TypeError(sleep)
    loop_count = max_processes + 1
    logging.info(f"Starting sleep check of {process_str}")
    while loop_count >= max_processes:
        # The process might disappear during loops, so we need to query the
        # name upfront.
        loop_count = sum(
            1 for proc in psutil.process_iter(['name'])
            if proc.info.get('name') == process_str
        )
        if max_processes > loop_count:
            break
        # Try to make each check at different times
        random_time = random.randrange(*sleep)
        logging.debug(f"{loop_count} processes running. Sleeping for {random_time}s.")
        time.sleep(random_time)
    logging.info(f"Exiting sleep check of {process_str}")
    return True


def convert_job_type(video_type):
    """
    Converts the job_type to the correct sub-folder
    :param video_type: job.video_type
    :return: string of the correct folder
    """
    if video_type == "movie":
        type_sub_folder = "movies"
    elif video_type == "series":
        type_sub_folder = "tv"
    else:
        type_sub_folder = "unidentified"
    return type_sub_folder


def fix_job_title(job):
    """
    Validate the job title remove/add job year as needed\n
    :param job:
    :return: corrected job.title
    """
    base = job.title_manual or job.title or ""
    if job.year and job.year != "0000" and job.year != "":
        job_title = f"{base} ({job.year})"
    else:
        job_title = str(base)
    return clean_for_filename(job_title)


#  ############## Start of post processing functions
def move_files(base_path, filename, job, is_main_feature=False):
    """
    Run extra checks then move files from RAW_PATH or TRANSCODE_PATH to final media directory\n
    :param str base_path: Path to source directory\n
    :param str filename: name of file to be moved\n
    :param job: instance of Job class\n
    :param bool is_main_feature: if current is main feature move to main dir
    :return str: Full movie path
    """
    video_title = fix_job_title(job)
    logging.debug(f"Arguments: {base_path} : {filename} : "
                  f"{job.hasnicetitle} : {video_title} : {is_main_feature}")
    # If filename is blank skip and return
    if filename == "":
        logging.info(f"{filename} is empty... Skipping")
        return None

    movie_path = job.path
    logging.info(f"Moving {job.video_type} {filename} to {movie_path}")
    # For series there are no extras so always use the base path
    extras_path = os.path.join(movie_path, job.config.EXTRAS_SUB) if job.video_type != "series" else movie_path
    make_dir(movie_path)

    if is_main_feature:
        movie_file = os.path.join(movie_path, video_title + "." + job.config.DEST_EXT)
        logging.info(f"Track is the Main Title.  Moving '{os.path.join(base_path, filename)}' to {movie_file}")
        move_files_main(os.path.join(base_path, filename), movie_file, movie_path)
    else:
        # Don't make the extra's path unless we need it
        make_dir(extras_path)
        logging.info(f"Moving '{os.path.join(base_path, filename)}' to {extras_path}")
        # This also handles series - But it doesn't use the extras folder
        move_files_main(os.path.join(base_path, filename), os.path.join(extras_path, filename), extras_path)
    return movie_path


def _calculate_filename_similarity(expected_base, actual_base):
    """
    Calculate similarity score between two filenames.

    :param str expected_base: Expected filename without extension
    :param str actual_base: Actual filename without extension
    :return int: Similarity score
    """
    score = 0
    min_len = min(len(expected_base), len(actual_base))

    # Count matching characters from the start
    for i in range(min_len):
        if expected_base[i] == actual_base[i]:
            score += 1
        else:
            break

    # Count matching characters from the end
    for i in range(1, min_len + 1):
        if expected_base[-i] == actual_base[-i]:
            score += 1
        else:
            break

    # Bonus for similar length
    length_diff = abs(len(expected_base) - len(actual_base))
    if length_diff <= 2:  # Within 2 characters difference
        score += (3 - length_diff) * 2

    return score


def find_matching_file(expected_file):
    """
    Find a file that matches the expected filename, handling minor naming discrepancies.
    This is particularly useful for MKV files transcoded by HandBrake where the output
    filename may differ slightly from what's stored in the database.

    :param str expected_file: The full path to the expected file
    :return str: The actual file path if found, or the original expected_file if no match
    """
    if os.path.isfile(expected_file):
        return expected_file

    directory = os.path.dirname(expected_file)
    expected_filename = os.path.basename(expected_file)

    if not os.path.isdir(directory):
        return expected_file

    expected_base, expected_ext = os.path.splitext(expected_filename)

    # Get candidate files with same extension
    try:
        files_in_dir = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    except OSError:
        return expected_file

    candidate_files = []
    for file in files_in_dir:
        base, ext = os.path.splitext(file)
        if ext.lower() == expected_ext.lower():
            candidate_files.append((file, base))

    if not candidate_files:
        return expected_file

    # Find best match
    best_match = None
    best_score = 0

    for file, base in candidate_files:
        score = _calculate_filename_similarity(expected_base, base)
        if score > best_score:
            best_score = score
            best_match = file

    # Use match if similar enough (at least 80% of expected length matched)
    min_score = len(expected_base) * 0.8
    if best_match and best_score >= min_score:
        actual_file = os.path.join(directory, best_match)
        if actual_file != expected_file:
            logging.info(f"Found similar file '{best_match}' for expected '{expected_filename}' (score: {best_score})")
        return actual_file

    return expected_file


def move_files_main(old_file, new_file, base_path):
    """
    The base function for moving files with logging\n
    :param str old_file: The file to be moved - must include full path
    :param str new_file: Final destination of file - must include full path
    :param str base_path: The base path of the new file - used for logging
    :return: None
    """
    if not os.path.isfile(new_file):
        # Try to find the file, handling minor naming discrepancies
        actual_old_file = find_matching_file(old_file)

        try:
            shutil.move(actual_old_file, new_file)
        except Exception as error:
            logging.error(f"Unable to move '{actual_old_file}' to '{base_path}' - Error: {error}")
    else:
        logging.info(f"File: {new_file} already exists.  Not moving.")


def move_movie_poster(final_directory, hb_out_path):
    """move movie poster\n
    ---------\n
    DEPRECIATED - Arm already builds the final path so moving is no longer needed"""
    src_poster = os.path.join(hb_out_path, "poster.png")
    dst_poster = os.path.join(final_directory, "poster.png")
    if os.path.isfile(src_poster):
        if not os.path.isfile(dst_poster):
            try:
                shutil.move(src_poster, dst_poster)
            except Exception as poster_error:
                logging.error(f"Unable to move poster.png to '{final_directory}' - Error: {poster_error}")
        else:
            logging.info("File: poster.png already exists.  Not moving.")


def scan_emby():
    """Trigger a media scan on Emby"""

    if cfg.arm_config["EMBY_REFRESH"]:
        logging.info("Sending Emby library scan request")
        url = f"http://{cfg.arm_config['EMBY_SERVER']}:{cfg.arm_config['EMBY_PORT']}/Library/Refresh?api_key={cfg.arm_config['EMBY_API_KEY']}"  # noqa: E501
        try:
            req = requests.post(url)
            if req.status_code > 299:
                req.raise_for_status()
            logging.info("Emby Library Scan request successful")
        except requests.exceptions.HTTPError:
            logging.error(f"Emby Library Scan request failed with status code: {req.status_code}")
    else:
        logging.info("EMBY_REFRESH config parameter is false.  Skipping emby scan.")


def delete_raw_files(dir_list):
    """
    Delete the raw folders from arm after job has finished
    :param list dir_list: Python list containing strings of the folders to be deleted

    """
    if cfg.arm_config["DELRAWFILES"]:
        for raw_folder in dir_list:
            try:
                logging.info(f"Removing raw path - {raw_folder}")
                shutil.rmtree(raw_folder)
            except UnboundLocalError as error:
                logging.debug(f"No raw files found to delete in {raw_folder}- {error}")
            except OSError as error:
                logging.debug(f"No raw files found to delete in {raw_folder} - {error}")
            except TypeError as error:
                logging.debug(f"No raw files found to delete in {raw_folder} - {error}")


#  ############## End of post processing functions


def make_dir(path: str, exist_ok: bool = True) -> bool:
    """
    Make a directory\n
    :param path: Path to directory
    :param exist_ok: If ``True``, simply returns ``False`` in case the
        directory exists. If ``False``, raises a ``RipperException`` in that case.
    :return: ``True`` if the directory was created, ``False`` if it already existed
    :raises: ``RipperException``
    """
    try:
        os.makedirs(path)
        logging.debug(f"Created directory: {path}")
        return True
    except FileExistsError as err:
        if exist_ok:
            return False
        else:
            raise RipperException(f"Folder exists: {path}") from err
    except OSError as err:
        raise RipperException(f"Could not create folder: {path}") from err


def find_file(filename, search_path):
    """
    Check to see if file exists by searching a directory recursively\n
    :param filename: filename to look for
    :param search_path: path to search recursively
    :return bool:
    """
    for dirpath, dirnames, filenames in os.walk(search_path):
        if filename in filenames:
            return True
    return False


def find_largest_file(files, mkv_out_path):
    """
    Step through given dir and return the largest file name\n
    :param files: dir in os.listdir() format
    :param mkv_out_path: RAW_PATH
    :return: largest file name
    """
    largest_file_name = ""
    for file in files:
        # initialize largest_file_name
        if largest_file_name == "":
            largest_file_name = file
        temp_path_f = os.path.join(mkv_out_path, file)
        temp_path_largest = os.path.join(mkv_out_path, largest_file_name)
        if os.stat(temp_path_f).st_size > os.stat(temp_path_largest).st_size:
            largest_file_name = file
    return largest_file_name


def abcde_output_dir():
    """Folder abcde writes ripped CDs into, from abcde.conf."""
    from arm.ui.settings.abcde_utils import parse_abcde_values
    values, _ = parse_abcde_values(getattr(cfg, "abcde_config", "") or "")
    path = (values.get("OUTPUTDIR") or "").strip()
    return os.path.expanduser(path) if path else ""


def _is_abcde_workdir(path):
    """True for abcde session folders like abcde.a00a3c0a (CDDB disc id)."""
    name = Path(path).name
    if not name.startswith("abcde."):
        return False
    suffix = name[6:]
    return bool(suffix) and all(char in "0123456789abcdefABCDEF" for char in suffix)


def abcde_work_dirs(base=None):
    """Temporary abcde session folders in the ARM home (and TMPDIR)."""
    if base is not None:
        roots = [Path(base)]
    else:
        roots = [Path.home()]
        tmp = Path(os.environ.get("TMPDIR") or "/tmp")
        if tmp not in roots:
            roots.append(tmp)
    found = []
    for root in roots:
        try:
            entries = root.iterdir()
        except OSError:
            continue
        for path in entries:
            if path.is_dir() and _is_abcde_workdir(path):
                found.append(path)
    return found


def _path_in_process_cmd(path, cmdline):
    text = " ".join(cmdline or [])
    return str(path) in text


def abcde_workdir_in_use(path):
    """True when a running process still has this abcde session folder open."""
    target = str(path)
    for proc in psutil.process_iter(["cmdline"]):
        try:
            if _path_in_process_cmd(target, proc.info.get("cmdline")):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def stop_stray_abcde(devpath):
    """Kill abcde/cdparanoia left on this drive after an abandoned job."""
    if not devpath:
        return 0
    markers = (str(devpath), os.path.basename(str(devpath)))
    killed = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name not in ("abcde", "cdparanoia") and "abcde" not in cmd and "cdparanoia" not in cmd:
            continue
        if not any(marker and marker in cmd for marker in markers):
            continue
        try:
            proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        logging.info("Stopped %s leftover abcde/cdparanoia process(es) on %s", killed, devpath)
    return killed


def clear_abcde_work_dirs(base=None):
    """Delete leftover abcde session folders so the next CD rip starts at track 1."""
    removed = []
    for path in abcde_work_dirs(base):
        if abcde_workdir_in_use(path):
            logging.info("Leaving in-use abcde session %s", path)
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except OSError as error:
            logging.warning("Could not remove abcde session %s: %s", path, error)
    if removed:
        logging.info("Removed leftover abcde session(s): %s", ", ".join(removed))
    return removed


def promote_album_cover(output_dir, max_age_seconds=7200):
    """Copy a freshly ripped abcde cover.jpg next to the tracks.

    abcde leaves cover art in albumart_backup/ after embedalbumart. Media
    servers look for cover.jpg beside the files.
    """
    if not output_dir or not os.path.isdir(output_dir):
        return 0
    copied = 0
    cutoff = time.time() - max_age_seconds
    output_dir = os.path.abspath(output_dir)
    for dirpath, dirnames, filenames in os.walk(output_dir):
        rel = os.path.relpath(dirpath, output_dir)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth > 4:
            dirnames[:] = []
            continue
        if os.path.basename(dirpath) != "albumart_backup":
            continue
        cover_name = next(
            (name for name in ("cover.jpg", "cover.jpeg", "cover.png") if name in filenames),
            None,
        )
        if not cover_name:
            continue
        src = os.path.join(dirpath, cover_name)
        try:
            if os.path.getmtime(src) < cutoff:
                continue
        except OSError:
            continue
        dest = os.path.join(os.path.dirname(dirpath), cover_name)
        if os.path.isfile(dest):
            continue
        try:
            shutil.copy2(src, dest)
        except OSError as error:
            logging.debug(f"Could not copy album cover to {dest}: {error}")
            continue
        logging.info(f"Copied album cover to {dest}")
        copied += 1
    return copied


def abcde_rip_command(devpath, logfile, logpath, abcfile=None):
    """Build the unattended abcde command. ``-N`` never waits for a prompt."""
    log_target = os.path.join(logpath, logfile)
    cmd = f'abcde -N -d "{devpath}"'
    if abcfile and os.path.isfile(abcfile):
        cmd += f' -c {abcfile}'
    return f'{cmd} >> "{log_target}" 2>&1'


def rip_music(job, logfile):
    """
    Rip music CD using abcde config\n
    :param job: job object
    :param logfile: location of logfile\n
    :return: Bool on success or fail
    """

    abcfile = cfg.arm_config["ABCDE_CONFIG_FILE"]
    if job.disctype == "music":
        logging.info("Disc identified as music")
        # Abandoned rips leave abcde.<discid> in $HOME; abcde resumes that
        # session and skips tracks it already grabbed. Start clean.
        stop_stray_abcde(job.devpath)
        clear_abcde_work_dirs()
        cmd = abcde_rip_command(
            job.devpath,
            logfile,
            job.config.LOGPATH,
            abcfile if os.path.isfile(abcfile) else None,
        )

        logging.debug(f"Sending command: {cmd}")
        args = {"status": JobState.AUDIO_RIPPING.value}
        database_updater(args, job)

        try:
            # TODO check output and confirm all tracks ripped; find "Finished\.$"
            subprocess.check_output(cmd, shell=True).decode("utf-8")
            logging.info("abcde call successful")
            promote_album_cover(abcde_output_dir())
            return True
        except subprocess.CalledProcessError as ab_error:
            err = f"Call to abcde failed with code: {ab_error.returncode} ({ab_error.output})"
            args = {"status": JobState.FAILURE.value, "errors": err}
            database_updater(args, job)
            logging.error(err)
    return False


def rip_data(job):
    """
    Rip data disc using dd on the command line\n
    :param job: Current job
    :return: True/False for success/fail
    """
    success = False
    if job.label == "" or job.label is None:
        job.label = "data-disc"
    # get filesystem in order
    raw_path = os.path.join(job.config.RAW_PATH, str(job.label))
    final_path = os.path.join(job.config.COMPLETED_PATH, convert_job_type(job.video_type))
    final_file_name = str(job.label)

    if (make_dir(raw_path)) is False:
        random_time = str(round(time.time() * 100))
        raw_path = os.path.join(job.config.RAW_PATH, str(job.label) + "_" + random_time)
        final_file_name = f"{job.label}_{random_time}"
        make_dir(raw_path, False)

    final_path = os.path.join(final_path, final_file_name)
    incomplete_filename = os.path.join(raw_path, str(job.label) + ".part")
    make_dir(final_path)
    logging.info(f"Ripping data disc to: {incomplete_filename}")
    # Added from pull 366
    cmd = f'dd if="{job.devpath}" of="{incomplete_filename}" {cfg.arm_config["DATA_RIP_PARAMETERS"]} 2>> ' \
          f'{os.path.join(job.config.LOGPATH, job.logfile)}'
    logging.debug(f"Sending command: {cmd}")
    try:
        subprocess.check_output(cmd, shell=True).decode("utf-8")
        full_final_file = os.path.join(final_path, f"{str(job.label)}.iso")
        logging.info(f"Moving data-disc from '{incomplete_filename}' to '{full_final_file}'")
        move_files_main(incomplete_filename, full_final_file, final_path)
        logging.info("Data rip call successful")
        success = True
    except subprocess.CalledProcessError as dd_error:
        err = f"Data rip failed with code: {dd_error.returncode}({dd_error.output})"
        logging.error(err)
        os.unlink(incomplete_filename)
        args = {"status": JobState.FAILURE.value, "errors": err}
        database_updater(args, job)
    try:
        logging.info(f"Trying to remove raw_path: '{raw_path}'")
        shutil.rmtree(raw_path)
    except OSError as error:
        logging.error(f"Error: {error.filename} - {error.strerror}.")
    return success


def set_permissions(directory_to_traverse):
    """

    :param directory_to_traverse: directory to fix permissions
    :return: False if fails
    """
    if not cfg.arm_config['SET_MEDIA_PERMISSIONS']:
        return False
    try:
        corrected_chmod_value = int(str(cfg.arm_config["CHMOD_VALUE"]), 8)
        logging.info(f"Setting permissions to: {cfg.arm_config['CHMOD_VALUE']} on: {directory_to_traverse}")
        os.chmod(directory_to_traverse, corrected_chmod_value)

        for dirpath, l_directories, l_files in os.walk(directory_to_traverse):
            for cur_dir in l_directories:
                logging.debug(f"Setting path: {cur_dir} to permissions value: {cfg.arm_config['CHMOD_VALUE']}")
                os.chmod(os.path.join(dirpath, cur_dir), corrected_chmod_value)

            for cur_file in l_files:
                logging.debug(f"Setting file: {cur_file} to permissions value: {cfg.arm_config['CHMOD_VALUE']}")
                os.chmod(os.path.join(dirpath, cur_file), corrected_chmod_value)

        logging.info("Permissions set successfully: True")
    except Exception as error:
        logging.error(f"Permissions setting failed as: {error}")
    return True


def try_add_default_user():
    """
    Added to fix missmatch from the armui and armripper\n
    This will try to add a default user for the armui
    with the details\n
    Username: admin\n
    Password: password\n
    :return: None
    """
    try:
        username = "admin"
        pass1 = "password".encode('utf-8')
        hashed = bcrypt.gensalt(12)
        database_adder(User(email=username, password=bcrypt.hashpw(pass1, hashed), hashed=hashed))
        logging.warning("Created default admin user (admin/password). Change this password immediately.")
        perm_file = Path(PurePath(cfg.arm_config['INSTALLPATH'], "installed"))
        write_permission_file = open(perm_file, "w")
        write_permission_file.write("boop!")
        write_permission_file.close()
    except Exception as error:
        #  notify("", str(error), str(error))
        logging.error(error)


def put_track(job, t_no, seconds, aspect, fps, mainfeature, source, filename="",
              chapters=0, filesize=0):
    """
    Put data into a track instance.\n
    Having this here saves importing the models file everywhere\n

    :param job: instance of job class
    :param str t_no: track number
    :param int seconds: length of track in seconds
    :param str aspect: aspect ratio (ie '16:9')
    :param str fps: frames per second:str (-not a float-)
    :param bool mainfeature: If the file is identified as the mainfeature
    :param str source: Source of information (HandBrake, MakeMKV, abcde)
    :param str filename: filename of track
    :param int chapters: number of chapters in track
    :param int filesize: size of track in bytes
    """

    logging.debug(
        f"Track #{int(t_no):02} Length: {seconds: >4} fps: {float(fps):2.3f} "
        f"aspect: {aspect: >4} Mainfeature: {mainfeature} Source: {source} "
        f"Chapters: {chapters} Filesize: {filesize}")

    job_track = Track(
        job_id=job.job_id,
        track_number=t_no,
        length=seconds,
        aspect_ratio=aspect,
        fps=fps,
        main_feature=mainfeature,
        source=source,
        basename=job.title,
        filename=filename,
        chapters=chapters,
        filesize=filesize
    )
    job_track.ripped = track_meets_minlength(job, seconds, source)
    database_adder(job_track)


def track_meets_minlength(job, seconds, source=""):
    """True if this track is long enough to keep, or is a music-CD track."""
    if str(source).upper() == "ABCDE":
        return True
    raw = None
    try:
        if getattr(job, "config", None) is not None:
            raw = job.config.MINLENGTH
    except AttributeError:
        raw = None
    if raw is None:
        raw = cfg.arm_config.get("MINLENGTH", 0)
    try:
        minlength = int(raw)
    except (TypeError, ValueError):
        minlength = 0
    return seconds > minlength


def arm_setup(arm_log: Logger) -> None:
    """
    Setup arm - Create all the directories we need for arm to run
    check that folders are writeable, and the db file is writeable
    """
    arm_directories = (
        cfg.arm_config['RAW_PATH'],
        cfg.arm_config['TRANSCODE_PATH'],
        cfg.arm_config['COMPLETED_PATH'],
        cfg.arm_config['LOGPATH'],
        os.path.join(cfg.arm_config['LOGPATH'], "progress"),
    )
    # Check if DB file is writeable
    if not os.access(cfg.arm_config['DBFILE'], os.W_OK):
        arm_log.critical(f"Can't write to database file: {cfg.arm_config['DBFILE']}")
    from arm.config.path_health import ensure_writable_dir

    # Check directories for read/write permission -> create if they don't exist
    for folder in arm_directories:
        try:
            ensure_writable_dir(folder, arm_log)
        except OSError as err:
            arm_log.critical(f"Can't use folder: {folder} ({err})")
            raise
        if not os.access(folder, os.R_OK):
            arm_log.error(f"Can't read from folder: {folder}")
        if not os.access(folder, os.W_OK):
            arm_log.critical(f"Can't write to folder: {folder}")


def database_updater(args, job, wait_time=90):
    """
    Try to update our db for x seconds and handle it nicely if we can't
    If args isn't a dict assume we are wanting a rollback\n

    :param args: This needs to be a Dict with the key being the job.method
    you want to change and the value being
    the new value.
    :param job: This is the job object
    :param int wait_time: Number of times to try(1 sec sleep between try)
    :return: True if the commit succeeded
    :raises RipperException: if SQLite stays locked for wait_time seconds
    :raises RuntimeError: for non-lock database errors
    """
    if not isinstance(args, dict):
        db.session.rollback()
        return False
    # Loop through our args and try to set any of our job variables
    for (key, value) in args.items():
        setattr(job, key, value)
        logging.debug(f"ID:{job.job_id} {key}={value}:{type(value)}")

    for i in range(wait_time):  # give up after the users wait period in seconds
        try:
            db.session.commit()
            logging.debug("successfully written to the database")
            return True
        except Exception as error:
            if "locked" in str(error):
                time.sleep(1)
                logging.debug(f"database is locked - try {i}/{wait_time}")
            else:
                logging.debug(f"Error: {error}")
                db.session.rollback()
                raise RuntimeError(str(error)) from error
    logging.error(f"database is locked after {wait_time}s; update was not committed")
    db.session.rollback()
    raise RipperException(f"database is locked after {wait_time}s; update was not committed")


def database_adder(obj_class):
    """
    Adds model item to db\n
    Used to stop database locked error\n
    :param obj_class: Job/Config/Track/ etc
    :return: True if success
    :raises RipperException: if SQLite stays locked for 90 seconds
    :raises RuntimeError: for non-lock database errors
    """
    for i in range(90):  # give up after the users wait period in seconds
        try:
            logging.debug(f"Trying to add {type(obj_class).__name__}")
            db.session.add(obj_class)
            db.session.commit()
            logging.debug(f"successfully written {type(obj_class).__name__} to the database")
            return True
        except Exception as error:
            if "locked" in str(error):
                time.sleep(1)
                logging.debug(f"database is locked - try {i}/90")
            else:
                logging.error(f"Error: {error}")
                db.session.rollback()
                raise RuntimeError(str(error)) from error
    logging.error(f"database is locked after 90s; {type(obj_class).__name__} was not added")
    db.session.rollback()
    raise RipperException(f"database is locked after 90s; {type(obj_class).__name__} was not added")


def clean_old_jobs():
    """
    Check for running jobs - Update failed jobs that are no longer running\n
    :return: None
    """
    active_jobs = db.session.query(Job).filter(Job.status.notin_(['fail', 'success'])).all()
    # Clean up abandoned jobs
    for job in active_jobs:
        if psutil.pid_exists(job.pid):
            job_process = psutil.Process(job.pid)
            if job.pid_hash == hash(job_process):
                logging.info(f"Job #{job.job_id} with PID {job.pid} is currently running.")
        else:
            logging.info(f"Job #{job.job_id} with PID {job.pid} has been abandoned."
                         f"Updating job status to fail.")
            job.status = JobState.FAILURE.value
            db.session.commit()
            database_updater({'status': JobState.FAILURE.value}, job)


def check_ip():
    """
        Check if user has set an ip in the config file
        if not gets the most likely ip
        arguments:
        none
        return: the ip of the host or 127.0.0.1
    """
    if cfg.arm_config['WEBSERVER_IP'] != 'x.x.x.x':
        return cfg.arm_config['WEBSERVER_IP']
    # autodetect host IP address
    ip_list = []
    for interface in interfaces():
        inet_links = ifaddresses(interface).get(AF_INET, [])
        for link in inet_links:
            ip_address = link['addr']
            if ip_address != '127.0.0.1' and not ip_address.startswith('172'):
                ip_list.append(ip_address)
    if len(ip_list) > 0:
        return ip_list[0]
    return '127.0.0.1'


def duplicate_run_check(dev_path):
    """
    Kills this run if another run was triggered recently on the same device\n
    Some drives will trigger the udev twice causing 1 disc insert to add 2 jobs\n
    this stops that issue.

    A job that has already ejected and is only transcoding does not hold the
    drive, so a new disc may start.
    :return: None
    """
    # Log running jobs by job status
    running_jobs = (
        db.session.query(Job)
        .filter(
            ~Job.finished,
            Job.devpath == dev_path,
        )
        .all()
    )
    for job in running_jobs:
        logging.info(f"Device {dev_path}: Job ({job.job_id}) status '{job.status}'")
        # Catch a second udev fire before the first job is associated with the drive.
        if job_holds_drive(job) and job.start_time and job.run_time < 180:
            logging.critical(f"Job ({job.job_id}) still holds {dev_path}.")
            raise RipperException(f"Job already running on {dev_path}")
    # check for running jobs by associated drive.
    drive = SystemDrives.query.filter_by(mount=dev_path).first()
    if drive is None or not drive.processing:
        return  # unknown or idle drive is safe to start another run.
    job = drive.job_current
    if not job_holds_drive(job):
        logging.info(
            f"Drive {dev_path} has job ({job.job_id}) in '{job.status}', "
            "but ripping is finished; allowing a new job."
        )
        return
    logging.critical(f'Drive {dev_path} has an active Job ({job.job_id}): {job.status}.')
    job_time = ceil(job.run_time // 60)
    logging.info(f"Job was started {job_time}min ago.")
    raise RipperException(f"Job already running on {dev_path}")


def save_disc_poster(final_directory, job):
    """
     Use FFMPeg to convert Large Poster if enabled in config
    :param final_directory: folder to put the poster in
    :param job: Current Job
    :return: None
    """
    if job.disctype == "dvd" and cfg.arm_config["RIP_POSTER"]:
        os.system(f"mount {job.devpath}")
        if os.path.isfile(job.mountpoint + "/JACKET_P/J00___5L.MP2"):
            logging.info("Converting NTSC Poster Image")
            os.system(f'ffmpeg -i "{job.mountpoint}/JACKET_P/J00___5L.MP2" "{final_directory}/poster.png"')
        elif os.path.isfile(job.mountpoint + "/JACKET_P/J00___6L.MP2"):
            logging.info("Converting PAL Poster Image")
            os.system(f'ffmpeg -i "{job.mountpoint}/JACKET_P/J00___6L.MP2" "{final_directory}/poster.png"')
        os.system(f"umount {job.devpath}")


def check_for_dupe_folder(have_dupes, hb_out_path, job):
    """
    Check if the folder already exists
     if it exists lets make a new one using random numbers
    :param have_dupes: is this title in the local arm database
    :param hb_out_path: path to HandBrake out
    :param job: Current job
    :return: Final media directory path
    """
    if (make_dir(hb_out_path)) is False:
        logging.info(f"Output directory \"{hb_out_path}\" already exists.")
        # Only begin ripping if we are allowed to make duplicates
        # Or the successful rip of the disc is not found in our database
        logging.debug(f"Value of ALLOW_DUPLICATES: {cfg.arm_config['ALLOW_DUPLICATES']}")
        logging.debug(f"Value of have_dupes: {have_dupes}")
        if cfg.arm_config["ALLOW_DUPLICATES"] or not have_dupes:
            hb_out_path = hb_out_path + "_" + job.stage
            make_dir(hb_out_path, False)
        else:
            # We aren't allowed to rip dupes, notify and exit
            logging.info("Duplicate rips are disabled.")
            notify(job, NOTIFY_TITLE, f"ARM Detected a duplicate disc. For {job.title}. "
                                      f"Duplicate rips are disabled. "
                                      f"You can re-enable them from your config file. ")
            raise RipperException("Duplicate rips are disabled")
    logging.info(f"Final Output directory \"{hb_out_path}\"")
    return hb_out_path


def job_dupe_check(job):
    """
    function for checking the database to look for jobs that have completed
    successfully with the same label
    :param job: The job obj, so we can use the crc/title etc.
    :return: True/False, dict/None
    """
    logging.debug(f"Trying to find jobs with matching Label={job.label}")
    if job.label is None:
        logging.info("Disc title 'None' not searched in database")
        return False
    if job.disctype in (None, "unknown"):
        logging.info("Disc type is unknown; skipping previous-rip metadata copy")
        return False
    else:
        # Same label can exist on a CD and a Blu-ray; only reuse metadata
        # from a successful job of the same disc type.
        previous_rips = Job.query.filter_by(
            label=job.label,
            status=JobState.SUCCESS.value,
            disctype=job.disctype,
        )
        results = {}
        i = 0
        for j in previous_rips:
            # logging.debug(f"job obj= {j.get_d()}")
            job_dict = j.get_d().items()
            results[i] = {}
            for key, value in iter(job_dict):
                results[i][str(key)] = str(value)
            i += 1

    # logging.debug(f"previous rips = {results}")
    if results:
        logging.debug(f"we have {len(results)} jobs")
        # Check if results too large (over 1), skip if too many
        if len(results) == 1:
            # This might need some tweaks to because of title/year manual
            title = results[0]['title'] if results[0]['title'] else job.label
            year = results[0]['year'] if results[0]['year'] != "" else ""
            poster_url = results[0]['poster_url'] if results[0]['poster_url'] != "" else None
            hasnicetitle = (str(results[0]['hasnicetitle']).lower() == 'true')
            video_type = results[0]['video_type'] if results[0]['hasnicetitle'] != "" else "unknown"
            active_rip = {
                "title": title, "year": year, "poster_url": poster_url, "hasnicetitle": hasnicetitle,
                "video_type": video_type}
            database_updater(active_rip, job)
            return True
        else:
            logging.debug(f"Skipping - There are too many results [{len(results)}]")
            return False
    else:
        logging.info("We have no previous rips/jobs matching this label")
        return False


def check_for_wait(job):
    """
    Wait if we have waiting for user input updates\n\n
    Auto-mode drives start ripping immediately. Manual-mode drives still
    pause so the UI can override the title.
    :param job: Current Job
    :return: None
    """
    if not should_wait_for_manual(job):
        if job.config.MANUAL_WAIT and not getattr(job, "manual_mode", False):
            logging.info("Drive is in auto mode; skipping manual wait.")
        return
    logging.info(f"Waiting {job.config.MANUAL_WAIT_TIME} seconds for manual override.")
    database_updater({"status": JobState.MANUAL_WAIT_STARTED.value}, job)
    sleep_time = 0
    while sleep_time < job.config.MANUAL_WAIT_TIME:
        time.sleep(5)
        sleep_time += 5
        db.session.refresh(job)
        if job.title_manual:
            logging.info("Manual override found.  Overriding auto identification values.")
            job.updated = True
            job.hasnicetitle = True
            database_updater({"hasnicetitle": True, "updated": True}, job)
            break
    database_updater({"status": JobState.IDLE.value}, job)


def get_drive_mode(devpath: str) -> str:
    """
    Retrieve the drive mode for a specified device path.

    This function queries the database for a drive associated with the provided
    device path (`devpath`). If a drive is found, it returns the drive's mode;
    otherwise, it defaults to 'auto'.

    Parameters:
        devpath (str): The device path used to identify the drive in the database.

    Returns:
        str: The drive mode associated with the specified device path if found;
             otherwise, returns 'auto'.
    """
    drive = SystemDrives.query.filter_by(mount=devpath).first()
    if drive:
        mode = drive.drive_mode
    else:
        mode = 'auto'
    return mode
