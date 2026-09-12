"""Log viewer (/logs, /logreader) and a bookmark redirect for /listlogs."""

import os
from pathlib import Path
from flask_login import LoginManager, login_required  # noqa: F401
from flask import render_template, request, Blueprint, send_file, session, redirect, url_for
from werkzeug.routing import ValidationError

import arm.ui.utils as ui_utils
from arm.ui import app
import arm.config.config as cfg

route_logs = Blueprint('route_logs', __name__,
                       template_folder='templates',
                       static_folder='../static')


@route_logs.route('/logs')
@login_required
def logs():
    """
    This is the main page for viewing a logfile

    this holds the XHR request that sends to other routes for the data
    """
    mode = request.args['mode']
    logfile = request.args['logfile']
    session["page_title"] = "Log"

    return render_template('logview.html', file=logfile, mode=mode)


@route_logs.route('/listlogs', defaults={'path': ''})
@login_required
def listlogs(path):
    """Old log-list page; the files now sit at the bottom of History."""
    return redirect(url_for("route_jobs.view_jobs") + "#other-logs")


@route_logs.route('/logreader')
@login_required
def logreader():
    """
    The default logreader output function

    This will display or allow downloading the requested logfile
    This is where the XHR requests are sent when viewing /logs?=logfile
    """
    log_path = cfg.arm_config['LOGPATH']
    mode = request.args.get('mode')
    session["page_title"] = "Logs"

    # We should use the job id and not get the raw logfile from the user
    # Maybe search database and see if we can match the logname with a previous rip ?
    full_path = os.path.join(log_path, request.args.get('logfile'))
    ui_utils.validate_logfile(request.args.get('logfile'), mode, Path(full_path))

    # Only ARM logs
    if mode == "armcat":
        generate = ui_utils.generate_arm_cat(full_path)
    # Give everything / Tail
    elif mode == "full":
        generate = ui_utils.generate_full_log(full_path)
    elif mode == "download":
        return send_file(full_path, as_attachment=True)
    else:
        # No mode - error out
        raise ValidationError

    return app.response_class(generate, mimetype='text/plain')
