"""
ARM route blueprint for history pages
Covers
- history [GET] (redirects to /jobs)
"""

from flask_login import login_required  # noqa: F401
from flask import request, Blueprint, redirect, url_for

route_history = Blueprint('route_history', __name__,
                          template_folder='templates',
                          static_folder='../static')


@route_history.route('/history')
@login_required
def history():
    """Kept as a bookmark; jobs now live on /jobs."""
    return redirect(url_for('route_jobs.view_jobs', page=request.args.get('page')))
