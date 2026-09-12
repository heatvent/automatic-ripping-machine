"""Old /history URL. The job list now lives at /jobs; keep this redirect."""

from flask_login import login_required  # noqa: F401
from flask import request, Blueprint, redirect, url_for

route_history = Blueprint('route_history', __name__,
                          template_folder='templates',
                          static_folder='../static')


@route_history.route('/history')
@login_required
def history():
    """Old /history bookmark → History (/jobs)."""
    return redirect(url_for('route_jobs.view_jobs', page=request.args.get('page')))
