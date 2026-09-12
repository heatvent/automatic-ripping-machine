"""Jobs UI: History list, job-detail page, title search, and /json AJAX.

History lives at /jobs. Home cards poll /json?mode=joblist.
/history, /database, and /listlogs redirect here so old bookmarks still work.
"""

import json
import os
from flask_login import LoginManager, login_required, current_user  # noqa: F401
from flask import render_template, request, Blueprint, flash, redirect, url_for, session
from werkzeug.routing import ValidationError

import arm.ui.utils as ui_utils
from arm.title_format import clean_for_filename
from arm.ui import app, db, constants, json_api
from arm.models.job import Job, JobState
import arm.config.config as cfg
from arm.ui.forms import TitleSearchForm, ChangeParamsForm, TrackFormDynamic
from arm.ui.workflow import movie_pipeline, music_pipeline

route_jobs = Blueprint('route_jobs', __name__,
                       template_folder='templates',
                       static_folder='../static')


def _is_music_job(job):
    """True for audio CD jobs.

    Type can live in video_type and/or disctype; older rows often have only one.
    """
    return (job.video_type or "").lower() == "music" or (job.disctype or "").lower() == "music"


def format_track_length(length, is_music=False):
    """Format stored track length for the job-detail table.

    MusicBrainz stores milliseconds; MakeMKV stores seconds.
    Returns M:SS, or H:MM:SS when the track is an hour or longer.
    """
    try:
        value = int(length or 0)
    except (TypeError, ValueError):
        return "—"
    seconds = round(value / 1000) if is_music else value
    if seconds < 0:
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _fact(label, value, href=None):
    """One labeled row for the job-detail info grid, or None if the value is empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None
    return {"label": label, "value": text, "href": href}


def _omdb_facts(search_results):
    """Movie/TV ratings and credits from OMDb or TMDb.

    Those APIs have no physical-media barcode; music jobs use MusicBrainz instead.
    """
    facts = []
    if not search_results or search_results.get("Error") or search_results.get("Response") == "False":
        return facts
    for rating in search_results.get("Ratings") or []:
        fact = _fact(rating.get("Source"), rating.get("Value"))
        if fact:
            facts.append(fact)
    extras = (
        ("Rated", "Rated"),
        ("Runtime", "Runtime"),
        ("Genre", "Genre"),
        ("Director", "Director"),
        ("Actors", "Cast"),
        ("Awards", "Awards"),
    )
    for key, label in extras:
        fact = _fact(label, search_results.get(key))
        if fact:
            facts.append(fact)
    imdb_id = search_results.get("imdbID")
    if imdb_id and str(imdb_id).upper() != "N/A":
        facts.append(_fact("IMDb", imdb_id, f"https://www.imdb.com/title/{imdb_id}/"))
    return [item for item in facts if item]


def _album_facts(job, album):
    """Album facts for job detail, including MusicBrainz barcode and catalog number."""
    facts = []
    if album:
        facts.extend([
            _fact("Artist", album.get("artist")),
            _fact("Album", album.get("album")),
            _fact("Year", album.get("year") or job.year),
            _fact("Label", album.get("label")),
            _fact("Barcode", album.get("barcode")),
            _fact("Catalog #", album.get("catalog")),
            _fact("Country", album.get("country")),
            _fact("Type", album.get("primary_type") or album.get("status")),
            _fact("MusicBrainz", album.get("mbid"), album.get("url")),
        ])
    else:
        facts.extend([
            _fact("Year", job.year),
            _fact("MusicBrainz", job.crc_id,
                  f"https://musicbrainz.org/release/{job.crc_id}"
                  if job.crc_id and len(str(job.crc_id)) == 36 else None),
        ])
    facts.append(_fact("Tracks", job.no_of_titles))
    facts.append(_fact("Disc label", job.label))
    return [item for item in facts if item]


def _other_log_files(jobs):
    """System logs that are not attached to a rip in the current result set."""
    other_logs = []
    log_path = cfg.arm_config.get("LOGPATH")
    if (
        not isinstance(jobs, dict)
        and getattr(jobs, "page", 1) == 1
        and log_path
        and os.path.isdir(log_path)
    ):
        try:
            job_logs = {
                name for (name,) in db.session.query(Job.logfile).filter(Job.logfile.isnot(None)).all()
                if name
            }
            other_logs = [
                entry for entry in ui_utils.get_info(log_path)
                if entry[0] not in job_logs
            ]
            other_logs.sort(key=lambda item: item[0].lower())
        except (OSError, Exception) as error:  # noqa: BLE001
            app.logger.error(f"Unable to list log files: {error}")
    return other_logs


@route_jobs.route('/jobs')
@login_required
def view_jobs():
    """Merged job list: History table plus Database search/delete."""
    armui_cfg = ui_utils.arm_db_cfg()
    page = request.args.get('page', 1, type=int)
    if os.path.isfile(cfg.arm_config['DBFILE']):
        jobs = Job.query.order_by(db.desc(Job.job_id)).paginate(
            page=page,
            max_per_page=int(armui_cfg.database_limit),
            error_out=False,
        )
    else:
        app.logger.error('ERROR: /jobs database file doesnt exist')
        jobs = {}
    session["page_title"] = "History"
    job_items = jobs.items if not isinstance(jobs, dict) else []
    return render_template(
        'jobs.html',
        jobs=job_items,
        pages=jobs,
        date_format=cfg.arm_config['DATE_FORMAT'],
        other_logs=_other_log_files(jobs),
    )


@route_jobs.route('/jobdetail')
@login_required
def jobdetail():
    """Job detail: plot/ratings for video, MusicBrainz facts for CDs, plus tracks.

    Missing job_id flashes "Job not found" and returns to History.
    Music jobs hide the cinematic background; album art uses object-fit: contain
    so non-square Cover Art Archive images are not cropped.
    """
    manual_edit = False

    # Initialise form
    track_form = TrackFormDynamic()

    job_id = request.args.get('job_id')
    job = Job.query.get(job_id) if job_id else None
    if job is None:
        flash("Job not found", "danger")
        return redirect(url_for("route_jobs.view_jobs"))

    waiting = {
        JobState.MANUAL_WAIT_STARTED.value,
        JobState.VIDEO_WAITING.value,
        JobState.PLAYLIST_WAIT.value,
    }
    if job.status in waiting and not job.manual_start:
        manual_edit = True

    # Get Job and Track data
    tracks = job.tracks.all()
    track_form.track_ref.min_entries = len(tracks)
    app.logger.debug(f"Found [{len(tracks)}] tracks")
    track_form.track_ref.entries.clear()
    # Loop through each track entry and build the WTForms dynamically
    for track_row in tracks:
        track_form.track_ref.append_entry({'track_ref': track_row.track_id,
                                           'checkbox': track_row.process})
    # For Jobs that are not waiting and in manual mode, disable the process checkbox
    if not manual_edit:
        for entry in track_form.track_ref.entries:
            entry.checkbox.render_kw = {'disabled': 'disabled'}

    is_music = _is_music_job(job)
    plot = None
    extra_facts = []
    if is_music:
        from arm.ripper import music_brainz
        album = music_brainz.release_details_for_ui(job.crc_id, job.arm_version)
        extra_facts = _album_facts(job, album)
        job.background = None
        pipeline = music_pipeline()
    else:
        search_results = ui_utils.metadata_selector("get_details", job.title, job.year, job.imdb_id)
        if search_results and "Error" not in search_results:
            plot = search_results.get("Plot")
            job.background = search_results.get("background_url")
            extra_facts = _omdb_facts(search_results)
        cfg_job = job.config
        pipeline = movie_pipeline({
            "SKIP_TRANSCODE": getattr(cfg_job, "SKIP_TRANSCODE", cfg.arm_config.get("SKIP_TRANSCODE")),
            "MAINFEATURE": getattr(cfg_job, "MAINFEATURE", cfg.arm_config.get("MAINFEATURE")),
            "RIPMETHOD": getattr(cfg_job, "RIPMETHOD", cfg.arm_config.get("RIPMETHOD")),
            "MKV_LANG": cfg.arm_config.get("MKV_LANG"),
            "USE_FFMPEG": getattr(cfg_job, "USE_FFMPEG", cfg.arm_config.get("USE_FFMPEG")),
        })

    return render_template('jobdetail.html',
                           jobs=job,
                           tracks=tracks,
                           is_music=is_music,
                           plot=plot,
                           extra_facts=extra_facts,
                           pipeline=pipeline,
                           format_track_length=format_track_length,
                           manual_edit=manual_edit,
                           form=track_form)


@route_jobs.route('/jobdetailload', methods=['POST'])
@login_required
def jobdetail_load():
    """
    Process updated track ID fields against a job and load to the ARM database if valid
    All data passed via POST
    """
    # Initialise form
    track_form = TrackFormDynamic()

    job_id = request.args.get('job_id')
    job = Job.query.get(job_id)

    # Data passed back from webpage, process and update track fields
    if request.method == 'POST' and track_form.validate_on_submit():
        app.logger.debug(f"Job id [{job.job_id}]")
        app.logger.debug(f"Returned [{len(track_form.track_ref.entries)}] tracks")
        for track_row in track_form.track_ref.entries:
            # app.logger.debug(f"Track deets [{track_row}]")
            track_id = track_row.data['track_ref']
            checkbox_value = track_row.data['checkbox']
            app.logger.debug(f"Setting [{track_id}] to [{checkbox_value}]")

            db_track = job.tracks.filter_by(track_id=track_id).first()
            if db_track:
                db_track.process = checkbox_value
                db.session.commit()

        # Set job to ready
        job.manual_start = True
        db.session.commit()
        app.logger.debug(f"Setting [{job.job_id}] to [{job.manual_start}], lets get ripping")
        flash("Tracks was updated", "success")

    return redirect(url_for('route_jobs.jobdetail', job_id=job_id))


@route_jobs.route('/titlesearch')
@login_required
def title_search():
    """
    The initial search page
    """
    job_id = request.args.get('job_id')
    job = Job.query.get(job_id)
    form = TitleSearchForm(request.args)
    if form.validate():
        flash(f'Search for {request.args.get("title")}, year={request.args.get("year")}', 'success')
        return redirect(url_for('route_jobs.list_titles', title=request.args.get("title"),
                                year=request.args.get("year"), job_id=job_id))
    return render_template('titlesearch.html', title='Update Title', form=form, job=job)


@route_jobs.route('/customTitle')
@login_required
def customtitle():
    """
    For setting custom title for series with multiple discs
    """
    job_id = request.args.get('job_id')
    ui_utils.job_id_validator(job_id)
    job = Job.query.get(job_id)
    form = TitleSearchForm(obj=job)
    if request.args.get("title"):
        cleaned_title = clean_for_filename(request.args.get("title"))
        args = {
            'title': cleaned_title,
            'title_manual': cleaned_title,
            'year': request.args.get("year")
        }
        ui_utils.database_updater(args, job)
        flash(f'Custom title changed. Title={job.title}, Year={job.year}.', "success")
        return redirect(url_for('home'))
    return render_template('customTitle.html', title='Change Title', form=form, job=job)


@route_jobs.route('/gettitle')
@route_jobs.route('/select_title')
@login_required
def gettitle():
    """
    Used to display plot info from the search result page when the user clicks the title
    and to forward the user to save the selected details

    This was also used previously for the getdetails page but it no longer needed there
    """
    imdb_id = request.args.get('imdbID').strip() if request.args.get('imdbID') else None
    job_id = request.args.get('job_id').strip() if request.args.get('job_id') else None
    if imdb_id == "" or imdb_id is None:
        app.logger.debug("gettitle - no imdb supplied")
        flash("No imdb supplied", "danger")
        raise ValidationError("No imdb supplied")
    if job_id == "" or job_id is None:
        app.logger.debug("gettitle - no job supplied")
        flash(constants.NO_JOB, "danger")
        raise ValidationError(constants.NO_JOB)
    dvd_info = ui_utils.metadata_selector("get_details", None, None, imdb_id)
    return render_template('showtitle.html', results=dvd_info, job_id=job_id)


@route_jobs.route('/updatetitle')
@login_required
def updatetitle():
    """
    used to save the details from the search
    Example URL
    updatetitle?title=Home&amp;year=2015&amp;imdbID=tt2224026&amp;type=movie&amp;
    poster=http://image.tmdb.org/t/p/original/usFenYnk6mr8C62dB1MoAfSWMGR.jpg&amp;job_id=109

    args
    title - new movie title
    year - new movie year
    imdbID - new movie IMDB reference
    type - new movie type
    poster - new movie poster URL
    job_id - job to update
    """
    #

    job_id = request.args.get('job_id')
    job = Job.query.get(job_id)
    old_title = job.title
    old_year = job.year
    app.logger.debug(f"Old Title and Year: {old_title}, {old_year}")

    app.logger.debug(f"New Title: {request.args.get('title')}")
    new_title = clean_for_filename(request.args.get('title'))
    app.logger.debug(f"Cleaned New Title: {new_title}")
    job.title = job.title_manual = new_title

    app.logger.debug(f"New Year: {request.args.get('year')}")
    app.logger.debug(f"New Type: {request.args.get('type')}")
    app.logger.debug(f"New IMDB: {request.args.get('imdbID')}")
    app.logger.debug(f"New Poster: {request.args.get('poster')}")

    job.year = job.year_manual = request.args.get('year')
    job.video_type = job.video_type_manual = request.args.get('type')
    job.imdb_id = job.imdb_id_manual = request.args.get('imdbID')
    job.poster_url = job.poster_url_manual = request.args.get('poster')

    job.hasnicetitle = True
    db.session.commit()
    flash(f'Title: {old_title} ({old_year}) was updated to '
          f'{request.args.get("title")} ({request.args.get("year")})', "success")
    return redirect("/")


@route_jobs.route('/changeparams')
@login_required
def changeparams():
    """
    For updating Config params or changing/correcting job.disctype manually
    """
    config_id = request.args.get('config_id')
    job = Job.query.get(config_id)
    config = job.config
    form = ChangeParamsForm(obj=config)
    return render_template('changeparams.html', title='Change Parameters', form=form, config=config)


@route_jobs.route('/list_titles')
@login_required
def list_titles():
    """
    The search results page

    This will display the returned search results from OMDB or TMDB from the users input search
    """
    title = request.args.get('title').strip() if request.args.get('title') else ''
    year = request.args.get('year').strip() if request.args.get('year') else ''
    job_id = request.args.get('job_id').strip() if request.args.get('job_id') else ''
    if job_id == "":
        app.logger.debug("list_titles - no job supplied")
        flash(constants.NO_JOB, "danger")
        raise ValidationError
    job = Job.query.get(job_id)
    form = TitleSearchForm(obj=job)
    search_results = ui_utils.metadata_selector("search", title, year)
    if search_results is None or 'Error' in search_results or (
            'Search' in search_results and len(search_results['Search']) < 1):
        app.logger.debug("No results found. Trying without year")
        flash(f"No search results found for {title} ({year})<br/> Trying without year", 'danger')
        search_results = ui_utils.metadata_selector("search", title, "")

    if search_results is None or 'Error' in search_results or (
            'Search' in search_results and len(search_results['Search']) < 1):
        flash(f"No search results found for {title}", 'danger')
    return render_template('list_titles.html', results=search_results, job_id=job_id,
                           form=form, title=title, year=year)


@route_jobs.route('/json', methods=['GET', 'POST'])
def feed_json():
    """AJAX endpoint used by Home, History, and job-detail buttons.

    mode= selects a handler in valid_modes (implemented in json_api or ui_utils).
    Unauthenticated callers get 401 except where Flask-Login is disabled.
    """
    # Check if users is authenticated
    authenticated = ui_utils.authenticated_state()
    mode = str(request.values.get('mode'))
    return_json = {'mode': mode, 'success': False}
    status = 200

    if authenticated:
        # Keys that handlers may request via valid_modes[mode]['args'].
        # Missing keys raise KeyError, so add new query params here first.
        valid_data = {
            'j_id': request.values.get('job'),
            'searchq': request.values.get('q'),
            'logpath': cfg.arm_config['LOGPATH'],
            'fail': 'fail',
            'success': 'success',
            'joblist': 'joblist',
            'mode': mode,
            'config_id': request.values.get('config_id'),
            'track': request.values.get('track'),
        }
        # Valid modes that should trigger functions
        valid_modes = {
            'delete': {'funct': json_api.delete_job, 'args': ('j_id', 'mode')},
            'abandon': {'funct': json_api.abandon_job, 'args': ('j_id',)},
            'full': {'funct': json_api.generate_log, 'args': ('logpath', 'j_id')},
            'search': {'funct': json_api.search, 'args': ('searchq',)},
            'getfailed': {
                'funct': json_api.get_x_jobs,
                'args': (JobState.FAILURE.value,),
            },
            'getsuccessful': {
                'funct': json_api.get_x_jobs,
                'args': (JobState.SUCCESS.value,),
            },
            'fixperms': {'funct': ui_utils.fix_permissions, 'args': ('j_id',)},
            'joblist': {'funct': json_api.get_x_jobs, 'args': ('joblist',)},
            'send_item': {'funct': ui_utils.send_to_remote_db, 'args': ('j_id',)},
            'change_job_params': {'funct': json_api.change_job_params, 'args': ('config_id',)},
            'restart': {'funct': json_api.restart_ui, 'args': ()},
            'select_playlist': {'funct': json_api.select_playlist, 'args': ('j_id', 'track')},
        }
    else:
        valid_data = {}
        valid_modes = {}
    if not authenticated:
        return_json = {
            'success': False,
            'mode': mode,
            'error': 'Authentication required',
            'results': {},
        }
        status = 401
    elif mode == 'change_job_params' and request.method != 'POST':
        return_json = {
            'success': False,
            'mode': mode,
            'error': 'POST required',
        }
        status = 405
    elif mode in valid_modes:
        args = [valid_data[x] for x in valid_modes[mode]['args']]
        return_json = valid_modes[mode]['funct'](*args)

    # return JSON data
    return app.response_class(response=json.dumps(return_json, indent=4, sort_keys=True),
                              status=status,
                              mimetype=constants.JSON_TYPE)
