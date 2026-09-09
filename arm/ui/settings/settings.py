"""
ARM route blueprint for settings pages
Covers
- settings [GET]
- system [GET]
- save_settings [POST]
- save_ui_settings [POST]
- save_abcde_settings [POST]
- save_apprise_cfg [POST]
- systeminfo [POST]
- systemdrivescan [GET]
- update_arm [POST]
- drive_eject [GET]
- drive_remove [GET]
- testapprise [GET]
- updatesysinfo [GET]
"""
import platform
import importlib
import re
import subprocess
from datetime import datetime
import os
import time

import sqlalchemy

from flask_login import login_required, \
    current_user, login_user, UserMixin, logout_user  # noqa: F401
from flask import render_template, request, flash, \
    redirect, Blueprint, session, url_for

import arm.ui.utils as ui_utils
from arm.ripper.ProcessHandler import arm_subprocess
from arm.ui import app, db
from arm.models.job import Job
from arm.models.system_drives import SystemDrives
from arm.models.system_info import SystemInfo
from arm.models.ui_settings import UISettings
import arm.config.config as cfg
from arm.ui.settings import DriveUtils as drive_utils
from arm.config.config_utils import (
    BOOLEAN_SETTING_KEYS,
    ENUM_SETTING_CHOICES,
    HIDDEN_SETTING_KEYS,
    is_secret_setting_key,
    mask_last,
    yaml_is_true,
)
from arm.ui.settings.setting_meta import (
    INTEGER_SETTING_KEYS,
    PORT_SETTING_KEYS,
    SETTING_LABELS,
    page_setting_groups,
    setting_label,
    validate_ripper_form,
    validate_ui_form,
)
from arm.ui.settings.abcde_utils import (
    abcde_fields_for_ui,
    apply_abcde_updates,
    validate_abcde_form,
)
from arm.ui.forms import SettingsForm, UiSettingsForm, AbcdeForm, SystemInfoDrives
from arm.ui.settings.ServerUtil import ServerUtil
import arm.ripper.utils as ripper_utils

route_settings = Blueprint('route_settings', __name__,
                           template_folder='templates',
                           static_folder='../static')
REDIRECT_SETTINGS = "route_settings.settings"


def redirect_to_settings_tab(tab="drives"):
    return redirect(url_for(REDIRECT_SETTINGS) + f"#{tab}")


def is_read_only(path: os.PathLike) -> bool:
    return not os.access(path, os.W_OK)


def _first_form_errors(form):
    """Flatten WTForms errors to {field: first message}."""
    errors = {}
    for key, messages in (form.errors or {}).items():
        if not messages:
            continue
        errors[key] = messages[0]
    return errors


route_settings.add_app_template_filter(mask_last, name='mask_last')
route_settings.add_app_template_filter(yaml_is_true, name='as_bool')
route_settings.add_app_template_global(setting_label, name='setting_label')


def redacted_config(settings):
    """Return a copy of a config dict with secret values masked."""
    if not isinstance(settings, dict):
        return settings
    redacted = dict(settings)
    for key, value in redacted.items():
        if value and is_secret_setting_key(key):
            redacted[key] = mask_last(str(value))
    return redacted


def _system_page_context():
    """Stats, hardware, and drive data for the System page."""
    failed_rips = Job.query.filter_by(status="fail").count()
    total_rips = Job.query.filter_by().count()
    movies = Job.query.filter_by(video_type="movie").count()
    series = Job.query.filter_by(video_type="series").count()
    cds = Job.query.filter_by(disctype="music").count()

    server_timezone = os.environ.get("TZ", "Etc/UTC")
    current_time = datetime.now()
    server_datetime = current_time.strftime(cfg.arm_config['DATE_FORMAT'])
    [arm_version_local, arm_version_remote] = ui_utils.git_check_version()
    local_git_hash = ui_utils.get_git_revision_hash()

    stats = {'server_datetime': server_datetime,
             'server_timezone': server_timezone,
             'python_version': platform.python_version(),
             'arm_version_local': arm_version_local,
             'arm_version_remote': arm_version_remote,
             'git_commit': local_git_hash,
             'movies_ripped': movies,
             'series_ripped': series,
             'cds_ripped': cds,
             'no_failed_jobs': failed_rips,
             'total_rips': total_rips,
             'updated': ui_utils.git_check_updates(local_git_hash),
             'hw_support': check_hw_transcode_support()
             }

    server = SystemInfo.query.filter_by(id="1").first()
    serverutil = ServerUtil()
    drive_utils.update_job_status()
    drives = drive_utils.get_drives()
    drive_utils.update_tray_status(drives)

    return {
        'stats': stats,
        'server': server,
        'serverutil': serverutil,
        'arm_path': cfg.arm_config['TRANSCODE_PATH'],
        'media_path': cfg.arm_config['COMPLETED_PATH'],
        'drives': drives,
        'form_drive': SystemInfoDrives(request.form),
    }


@route_settings.route('/system')
@login_required
def system_page():
    """Keep /system working; it now opens Settings → System Information."""
    return redirect_to_settings_tab("sysinfo")


@route_settings.route('/settings')
@login_required
def settings():
    """
    Page - settings
    Method - GET
    Overview - allows the user to update the all configs of A.R.M without
    needing to open a text editor
    """
    # ARM UI config
    armui_cfg = ui_utils.arm_db_cfg()

    # Load up the comments.json, so we can comment the arm.yaml
    comments = ui_utils.generate_comments()
    form = SettingsForm()
    pages = page_setting_groups(cfg.arm_config)
    system_context = _system_page_context()

    session["page_title"] = "Settings"

    return render_template("settings/settings.html",
                           settings=cfg.arm_config,
                           ui_settings=armui_cfg,
                           apprise_cfg=cfg.apprise_config,
                           form=form,
                           jsoncomments=comments,
                           abcde_cfg=cfg.abcde_config,
                           ripper_read_only=is_read_only(cfg.arm_config_path),
                           apprise_read_only=is_read_only(cfg.apprise_config_path),
                           abcde_read_only=is_read_only(cfg.abcde_config_path),
                           secret_setting_keys=frozenset(
                               key for key in cfg.arm_config if is_secret_setting_key(key)
                           ),
                           hidden_setting_keys=HIDDEN_SETTING_KEYS,
                           boolean_setting_keys=BOOLEAN_SETTING_KEYS,
                           enum_setting_choices=ENUM_SETTING_CHOICES,
                           enum_setting_values={
                               key: [choice[0] for choice in choices]
                               for key, choices in ENUM_SETTING_CHOICES.items()
                           },
                           integer_setting_keys=INTEGER_SETTING_KEYS,
                           port_setting_keys=PORT_SETTING_KEYS,
                           setting_labels=SETTING_LABELS,
                           setting_label=setting_label,
                           general_setting_groups=pages["general"],
                           ripper_setting_groups=pages["ripper"],
                           notify_setting_groups=pages["notify"],
                           abcde_fields=abcde_fields_for_ui(cfg.abcde_config),
                           **system_context)


_HW_TRANSCODE_CACHE = {"ts": 0.0, "status": None}
_HW_TRANSCODE_CACHE_TTL = 3600


def check_hw_transcode_support():
    if yaml_is_true(cfg.arm_config.get("SKIP_TRANSCODE")):
        return {"nvidia": False, "intel": False, "amd": False, "skipped": True}

    now = time.time()
    cached = _HW_TRANSCODE_CACHE["status"]
    if cached is not None and (now - _HW_TRANSCODE_CACHE["ts"]) < _HW_TRANSCODE_CACHE_TTL:
        return cached

    cmd = f"nice {cfg.arm_config['HANDBRAKE_CLI']}"

    app.logger.debug(f"Sending command: {cmd}")
    hw_support_status = {
        "nvidia": False,
        "intel": False,
        "amd": False,
        "skipped": False,
    }
    try:
        hand_brake_output = arm_subprocess(f"{cmd}", shell=True, check=True)

        # NVENC
        if re.search(r'nvenc: version ([0-9\\.]+) is available', str(hand_brake_output)):
            app.logger.info("NVENC supported!")
            hw_support_status["nvidia"] = True
        # Intel QuickSync
        if re.search(r'qsv:\sis(.*?)available\son', str(hand_brake_output)):
            app.logger.info("Intel QuickSync supported!")
            hw_support_status["intel"] = True
        # AMD VCN
        if re.search(r'vcn:\sis(.*?)available\son', str(hand_brake_output)):
            app.logger.info("AMD VCN supported!")
            hw_support_status["amd"] = True
        app.logger.info("Handbrake call successful")
        app.logger.debug(hand_brake_output)
    except subprocess.CalledProcessError:
        pass
    _HW_TRANSCODE_CACHE["status"] = hw_support_status
    _HW_TRANSCODE_CACHE["ts"] = now
    return hw_support_status


@route_settings.route('/save_settings', methods=['POST'])
@login_required
def save_settings():
    """
    Page - save_settings
    Method - POST
    Overview - Save arm ripper settings from post. Not a user page
    """
    # Load up the comments.json, so we can comment the arm.yaml
    comments = ui_utils.generate_comments()
    success = False
    arm_cfg = {}
    restart_needed = False
    restart_keys = ("DISABLE_LOGIN", "WEBSERVER_IP", "WEBSERVER_PORT", "ARM_CHILDREN")
    before = {key: str(cfg.arm_config.get(key)) for key in restart_keys}
    form = SettingsForm()
    if form.validate_on_submit():
        errors = validate_ripper_form(request.form.to_dict(), cfg.arm_config)
        if errors:
            return {
                'success': False,
                'errors': errors,
                'form': 'arm ripper settings',
            }
        # Build the new arm.yaml with updated values from the user
        arm_cfg = ui_utils.build_arm_cfg(request.form.to_dict(), comments)
        # Save updated arm.yaml
        try:
            with open(cfg.arm_config_path, "w") as settings_file:
                settings_file.write(arm_cfg)
                settings_file.close()
            success = True
            importlib.reload(cfg)
            # Set the ARM Log level to the config
            app.logger.info(f"Setting log level to: {cfg.arm_config['LOGLEVEL']}")
            app.logger.setLevel(cfg.arm_config['LOGLEVEL'])
            restart_needed = any(
                str(cfg.arm_config.get(key)) != before[key] for key in restart_keys
            )
            if restart_needed:
                app.config['LOGIN_DISABLED'] = cfg.arm_config['DISABLE_LOGIN']
        except OSError as e:
            # arm.yaml is read-only
            app.logger.error(f"{cfg.arm_config_path} is read-only", exc_info=e)
    elif request.method == "POST":
        return {
            'success': False,
            'errors': _first_form_errors(form),
            'form': 'arm ripper settings',
        }

    return {
        'success': success,
        'settings': redacted_config(cfg.arm_config),
        'form': 'arm ripper settings',
        'restart_needed': restart_needed,
    }


@route_settings.route('/save_ui_settings', methods=['POST'])
@login_required
def save_ui_settings():
    """
    Page - save_ui_settings
    Method - POST
    Overview - Save 'UI Settings' page settings to database. Not a user page
    """
    form = UiSettingsForm()
    success = False
    arm_ui_cfg = UISettings.query.get(1)
    if form.validate_on_submit():
        errors = validate_ui_form(form.index_refresh.data, form.database_limit.data)
        if errors:
            return {
                'success': False,
                'errors': errors,
                'form': 'arm ui settings',
            }
        arm_ui_cfg.index_refresh = format(form.index_refresh.data)
        arm_ui_cfg.database_limit = format(form.database_limit.data)
        arm_ui_cfg.notify_refresh = format(form.notify_refresh.data)
        db.session.commit()
        success = True
        ui_utils.arm_db_cfg()
    elif request.method == "POST":
        return {
            'success': False,
            'errors': _first_form_errors(form),
            'form': 'arm ui settings',
        }
    return {
        'success': success,
        'settings': str(arm_ui_cfg),
        'form': 'arm ui settings',
        'reload_needed': success,
    }


@route_settings.route('/save_abcde_settings', methods=['POST'])
@login_required
def save_abcde():
    """
    Page - save_abcde_settings
    Method - POST
    Overview - Save 'abcde Config' page settings to the database. Not a user page
    """
    success = False
    abcde_cfg_str = cfg.abcde_config
    form = AbcdeForm()
    if form.validate_on_submit():
        errors = validate_abcde_form(request.form)
        if errors:
            return {
                'success': False,
                'errors': errors,
                'form': 'cd ripper settings',
            }
        app.logger.debug(f"routes.save_abcde: Saving new abcde.conf: {cfg.abcde_config_path}")
        abcde_cfg_str = apply_abcde_updates(cfg.abcde_config, request.form)
        try:
            with open(cfg.abcde_config_path, "w") as abcde_file:
                abcde_file.write(abcde_cfg_str)
                abcde_file.close()
            success = True
            cfg.abcde_config = abcde_cfg_str
        except OSError as e:
            app.logger.error(f"{cfg.abcde_config_path} is read-only", exc_info=e)
    elif request.method == "POST":
        return {
            'success': False,
            'errors': _first_form_errors(form),
            'form': 'cd ripper settings',
        }

    return {'success': success,
            'settings': abcde_cfg_str,
            'form': 'cd ripper settings'}


@route_settings.route('/save_apprise_cfg', methods=['POST'])
@login_required
def save_apprise_cfg():
    """
    Page - save_apprise_cfg
    Method - POST
    Overview - Save 'Apprise Config' page settings to database. Not a user page
    """
    success = False
    # Since we can't be sure of any values, we can't validate it
    if request.method == 'POST':
        # Save updated apprise.yaml
        # Build the new arm.yaml with updated values from the user
        apprise_cfg = ui_utils.build_apprise_cfg(request.form.to_dict())
        try:
            with open(cfg.apprise_config_path, "w") as settings_file:
                settings_file.write(apprise_cfg)
                settings_file.close()
            success = True
            importlib.reload(cfg)
        except OSError as e:
            app.logger.error(f"{cfg.apprise_config_path} is read-only", exc_info=e)
    # If we get to here there was no post data
    apprise_out = cfg.apprise_config
    if isinstance(apprise_out, dict):
        apprise_out = {k: mask_last(str(v)) if v else v for k, v in apprise_out.items()}
    return {'success': success, 'settings': apprise_out, 'form': 'Apprise config'}


@route_settings.route('/systeminfo', methods=['POST'])
@login_required
def server_info():
    """
    Page - systeminfo
    Method - POST
    Overview - Save 'System Info' page settings to database. Not a user page
    """
    # System Drives (CD/DVD/Blueray drives)
    form_drive = SystemInfoDrives(request.form)
    if request.method == 'POST' and form_drive.validate():
        # Return for POST
        app.logger.debug(
            f"Drive id: {str(form_drive.id.data)} " +
            f"Updated name: {str(form_drive.name.data)} " +
            f"Updated description: [{str(form_drive.description.data)}] " +
            f"Updated mode: [{str(form_drive.drive_mode.data)}]")
        drive = SystemDrives.query.filter_by(drive_id=form_drive.id.data).first()
        drive.description = str(form_drive.description.data).strip()
        drive.name = str(form_drive.name.data).strip()
        drive.drive_mode = str(form_drive.drive_mode.data).strip()
        db.session.commit()
        flash(f"Updated Drive {drive.name} details", "success")
        return redirect_to_settings_tab()
    else:
        flash("Error: Unable to update drive details", "error")
        return redirect_to_settings_tab()


@route_settings.route('/systemdrivescan')
def system_drive_scan():
    """
    Page - systemdrivescan
    Method - GET
    Overview - Scan for the system drives and update the database.
    """
    # Update to scan for changes to the ripper system
    new_count = drive_utils.drives_update()
    flash(f"ARM found {new_count} new drives", "success")
    return redirect_to_settings_tab()


@route_settings.route('/drive/eject/<eject_id>')
@login_required
def drive_eject(eject_id):
    """
    Server System - change state of CD/DVD/BluRay drive - toggle eject status
    """
    try:
        drive = SystemDrives.query.filter_by(drive_id=eject_id).one()
    except sqlalchemy.exc.NoResultFound as e:
        app.logger.error(f"Drive eject encountered an error: {e}")
        flash(f"Cannot find drive {eject_id} in database.", "error")
        return redirect_to_settings_tab()
    # block for running jobs
    if drive.job_id_current:
        drive.tray_status()  # update tray status
        if not drive.open:  # allow closing
            flash(f"Job [{drive.job_id_current}] in progress. Cannot eject {eject_id}.", "error")
            return redirect_to_settings_tab()
    # toggle open/close (with non-critical error)
    if (error := drive.eject(method="toggle")) is not None:
        flash(error, "error")
    return redirect_to_settings_tab()


@route_settings.route('/drive/remove/<remove_id>')
@login_required
def drive_remove(remove_id):
    """
    Server System - remove a drive from the ARM UI
    """
    try:
        app.logger.debug(f"Removing drive {remove_id}")
        drive = SystemDrives.query.filter_by(drive_id=remove_id).first()
        dev_path = drive.mount
        SystemDrives.query.filter_by(drive_id=remove_id).delete()
        db.session.commit()
        flash(f"Removed drive [{dev_path}] from ARM", "success")
    except Exception as e:
        app.logger.error(f"Drive removal encountered an error: {e}")
        flash("Drive unable to be removed, check logs for error", "error")
    return redirect_to_settings_tab()


@route_settings.route('/drive/manual/<manual_id>')
@login_required
def drive_manual(manual_id):
    """
    Manually start a job on ARM
    """

    drive = SystemDrives.query.filter_by(drive_id=manual_id).first()
    dev_path = drive.mount.lstrip('/dev/')

    cmd = os.path.join(
        cfg.arm_config["INSTALLPATH"],
        f"scripts/docker/docker_arm_wrapper.sh {dev_path}",
    )
    app.logger.debug(f"Running command[{cmd}]")

    # Manually start ARM if the udev rules are not working for some reason
    try:
        manual_process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = manual_process.communicate()

        if manual_process.returncode != 0:
            raise subprocess.CalledProcessError(manual_process.returncode, cmd, output=stdout, stderr=stderr)

        message = f"Manually starting a job on Drive: '{drive.name}'"
        status = "success"
        app.logger.debug(stdout)

    except subprocess.CalledProcessError as e:
        message = f"Failed to start a job on Drive: '{drive.name}' See logs for info"
        status = "danger"
        app.logger.error(message)
        app.logger.error(f"error: {e}")
        app.logger.error(f"stdout: {e.output}")
        app.logger.error(f"stderr: {e.stderr}")

    flash(message, status)
    return redirect_to_settings_tab()


@route_settings.route('/testapprise')
def testapprise():
    """
    Page - testapprise
    Method - GET
    Overview - Send a test notification to Apprise.
    """
    # Send a sample notification
    message = "This is a notification by the ARM-Notification Test!"
    if cfg.arm_config["UI_BASE_URL"] and cfg.arm_config["WEBSERVER_PORT"]:
        message = message + f" Server URL: http://{cfg.arm_config['UI_BASE_URL']}:{cfg.arm_config['WEBSERVER_PORT']}"
    ripper_utils.notify(None, "ARM notification", message)
    flash("Test notification sent ", "success")
    return redirect_to_settings_tab("notifications")


@route_settings.route('/updatesysinfo')
def update_sysinfo():
    """
    Update system information
    """
    # Get current system information from database
    current_system = SystemInfo.query.first()
    # Query system for new information
    new_system = SystemInfo()

    app.logger.debug("****** System Information ******")
    if current_system is not None:
        app.logger.debug(f"Name old [{current_system.name}] new [{new_system.name}]")
        app.logger.debug(f"Name old [{current_system.cpu}] new [{new_system.cpu}]")
        app.logger.debug(f"Name old [{current_system.mem_total}] new [{new_system.mem_total}]")
        current_system.name = new_system.name
        current_system.cpu = new_system.cpu
        current_system.mem_total = new_system.mem_total
        db.session.add(current_system)
    else:
        app.logger.debug(f"Name old [No Info] new [{new_system.name}]")
        app.logger.debug(f"Name old [No Info] new [{new_system.cpu}]")
        app.logger.debug(f"Name old [No Info] new [{new_system.mem_total}]")
        db.session.add(new_system)

    app.logger.debug("****** End System Information ******")
    app.logger.info(f"Updated CPU Details with new info - {new_system.name} - {new_system.cpu} - "
                    f"{new_system.mem_total}")

    db.session.commit()

    return redirect_to_settings_tab("sysinfo")
