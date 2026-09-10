#!/usr/bin/env python3
"""
Main code for setting up the logging for all of A.R.M
Also triggers CD identification
"""
# set up logging

import os
import logging
import logging.handlers
import time

import arm.config.config as cfg
from arm.title_format import clean_for_filename


short_format = (
    "%(levelname)s:"
    + (" %(module)s.%(funcName)s:" if cfg.arm_config["LOGLEVEL"] == "DEBUG" else "")
    + " %(message)s"
)
long_format = f"%(asctime)s ARM: {short_format}"

short_formatter = logging.Formatter(short_format, datefmt=cfg.arm_config["DATE_FORMAT"])
long_formatter = logging.Formatter(long_format, datefmt=cfg.arm_config["DATE_FORMAT"])


def setup_job_log(job):
    """
    Setup logging and return the path to the logfile for redirection of external calls\n
    We need to return the full logfile path but set the job.logfile to just the filename
    """
    # This isn't catching all of them
    if job.label == "" or job.label is None:
        if job.disctype == "music":
            valid_label = job.identify_audio_cd()
        else:
            valid_label = "no_label"
    else:
        valid_label = job.label

    valid_label = safe_log_basename(valid_label)
    log_file_name = f"{valid_label}.log"
    new_log_file = f"{valid_label}_{job.stage}.log"
    temp_log_full = os.path.join(cfg.arm_config['LOGPATH'], log_file_name)
    log_file = new_log_file if os.path.isfile(temp_log_full) else log_file_name
    log_full = os.path.join(cfg.arm_config['LOGPATH'], log_file)

    job.logfile = log_file

    # Keep arm.log (INFO+) and add the per-job file. Removing arm.log used to
    # force the docker wrapper to tee stdout back into arm.log, which duplicated
    # every line while LOGLEVEL was DEBUG.
    logger = logging.getLogger()
    log_path = os.path.abspath(cfg.arm_config["LOGPATH"])
    arm_log_path = os.path.join(log_path, "arm.log")
    job_log_path = os.path.abspath(log_full)
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.FileHandler):
            continue
        existing = os.path.abspath(getattr(handler, "baseFilename", "") or "")
        if existing not in (arm_log_path, job_log_path):
            logger.removeHandler(handler)
            handler.close()
        elif existing == job_log_path:
            return log_full

    logger.addHandler(_create_file_handler(log_file))

    # These stop apprise and others spitting our secret keys if users post log online
    logging.getLogger("apprise").setLevel(logging.WARN)
    logging.getLogger("requests").setLevel(logging.WARN)
    logging.getLogger("urllib3").setLevel(logging.WARN)

    # Return the full logfile location to the logs
    return log_full


def clean_up_logs(logpath, loglife, keep_names=None):
    """
    Delete leftover log files older than {loglife} days.

    arm.log and any log still attached to a job in History are kept, even when
    older than {loglife}. 0 disables deletion.

    :param logpath: path of log files
    :param loglife: days to let orphan logs live
    :param keep_names: basenames that must not be deleted (job.logfile values)
    :return: True if cleanup ran
    """
    if loglife < 1:
        logging.info("loglife is set to 0. Removal of logs is disabled")
        return False
    now = time.time()
    logging.info(f"Looking for leftover log files older than {loglife} days old.")
    keep = {"arm.log"}
    for name in keep_names or []:
        if name:
            keep.add(os.path.basename(str(name)))

    logs_folders = [logpath, os.path.join(logpath, 'progress')]
    for log_dir in logs_folders:
        logging.info(f"Checking path {log_dir} for old log files...")
        if not os.path.isdir(log_dir):
            logging.info(f"{log_dir} is not a directory or doesn't exist. Skipping.")
            continue
        for filename in os.listdir(log_dir):
            if filename in keep:
                continue
            fullname = os.path.join(log_dir, filename)
            try:
                aged_out = (
                    filename.endswith(".log")
                    and os.stat(fullname).st_mtime < now - loglife * 86400
                )
            except OSError:
                continue
            if aged_out:
                logging.info(f"Deleting leftover log file: {filename}")
                os.remove(fullname)
    return True


def safe_log_basename(label):
    """Make a log filename that is readable and safe on common filesystems."""
    return clean_for_filename(label, fallback="music_cd")


def _create_file_handler(filename):
    file_handler = logging.FileHandler(os.path.join(cfg.arm_config["LOGPATH"], filename))
    file_handler.setFormatter(long_formatter)
    return file_handler


def create_early_logger(stdout=True, syslog=True, file=True):
    """
    From: https://gist.github.com/danielkraic/a1657f19bad9c158cbf9532e1ed1503b\n
    Create logging object with logging to syslog, file and stdout\n
    Will log to `/var/log/arm.log`\n
    :param app_name: app name
    :param log_level: logging log level
    :param stdout: log to stdout
    :param syslog: log to syslog
    :param file: log to file
    :return: logging object
    """
    # disable requests logging
    # logging.getLogger("requests").setLevel(logging.ERROR)
    # logging.getLogger("urllib3").setLevel(logging.ERROR)

    # create logger
    logger = logging.getLogger()
    logger.setLevel(cfg.arm_config["LOGLEVEL"])
    # Named "ARM" loggers used by some modules should reach the same handlers.
    logging.getLogger("ARM").setLevel(cfg.arm_config["LOGLEVEL"])

    if file:
        # Combined log stays readable while a job log is at DEBUG.
        arm_handler = _create_file_handler("arm.log")
        arm_handler.setLevel(logging.INFO)
        logger.addHandler(arm_handler)

    if syslog:
        # create syslog logger handler
        stream_handler = logging.handlers.SysLogHandler(address='/dev/log')
        stream_handler.setFormatter(short_formatter)
        logger.addHandler(stream_handler)

    if stdout:
        # create stream logger handler
        stream_print = logging.StreamHandler()
        stream_print.setFormatter(short_formatter)
        logger.addHandler(stream_print)

    return logger
