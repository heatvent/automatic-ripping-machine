"""Main arm ui file"""
import sys  # noqa: F401
import os  # noqa: F401
from getpass import getpass  # noqa: F401
from logging.config import dictConfig
from flask import Flask, logging, current_app  # noqa: F401
from flask.logging import default_handler  # noqa: F401
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from arm.ripper.logger import short_format

from flask_login import LoginManager
import bcrypt  # noqa: F401
import arm.config.config as cfg
from arm.config.config_utils import cors_origins_from_children, load_or_create_secret_key

sqlitefile = 'sqlite:///' + cfg.arm_config['DBFILE']

# Setup logging, but because of werkzeug issues, we need to set up that later down file
dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': short_format,
        'datefmt': cfg.arm_config["DATE_FORMAT"],
    }},
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
        },
        "console": {"class": "logging.StreamHandler"},
        "null": {"class": "logging.NullHandler"},
    },
    'root': {
        'level': cfg.arm_config["LOGLEVEL"],
        'handlers': ['wsgi']
    },
})

app = Flask(__name__)
csrf = CSRFProtect()
csrf.init_app(app)
_cors_origins = cors_origins_from_children(cfg.arm_config.get("ARM_CHILDREN"))
if _cors_origins:
    CORS(app, resources={r"/json": {"origins": _cors_origins}})

login_manager = LoginManager()
login_manager.init_app(app)

# Set Flask database connection configurations
app.config['SQLALCHEMY_DATABASE_URI'] = sqlitefile
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "connect_args": {"check_same_thread": False, "timeout": 60},
}
_secret_path = os.path.join(os.path.dirname(cfg.arm_config.get("DBFILE") or ""),
                            ".flask_secret_key")
app.config['SECRET_KEY'] = load_or_create_secret_key(_secret_path)
# Set the global Flask Login state, set to True will ignore any @login_required
app.config['LOGIN_DISABLED'] = cfg.arm_config['DISABLE_LOGIN']
app.logger.debug(f"Disable Login: {cfg.arm_config['DISABLE_LOGIN']}")

db = SQLAlchemy(app)
migrate = Migrate(app, db)


@event.listens_for(Engine, "connect")
def _sqlite_enable_wal(dbapi_connection, _connection_record):
    """WAL plus a busy timeout so the UI and ripper contend less on arm.db."""
    try:
        import sqlite3
        if not isinstance(dbapi_connection, sqlite3.Connection):
            return
    except Exception:  # noqa: BLE001
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=60000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# Register route blueprints
# loaded post database declaration to avoid circular loops
from arm.ui.settings.settings import route_settings  # noqa: E402,F811
from arm.ui.logs.logs import route_logs  # noqa: E402,F811
from arm.ui.auth.auth import route_auth  # noqa: E402,F811
from arm.ui.database.database import route_database  # noqa: E402,F811
from arm.ui.history.history import route_history  # noqa: E402,F811
from arm.ui.jobs.jobs import route_jobs  # noqa: E402,F811
from arm.ui.sendmovies.sendmovies import route_sendmovies  # noqa: E402,F811
from arm.ui.notifications.notifications import route_notifications  # noqa: E402,F811
app.register_blueprint(route_settings)
app.register_blueprint(route_logs)
app.register_blueprint(route_auth)
app.register_blueprint(route_database)
app.register_blueprint(route_history)
app.register_blueprint(route_jobs)
app.register_blueprint(route_sendmovies)
app.register_blueprint(route_notifications)


@app.context_processor
def inject_arm_shell():
    """Sidebar extras: installed ARM version for every template."""
    version = "unknown"
    try:
        version_file = os.path.join(cfg.arm_config.get("INSTALLPATH", "/opt/arm"), "VERSION")
        with open(version_file, encoding="utf-8") as handle:
            version = handle.read().strip() or "unknown"
    except (OSError, TypeError, AttributeError):
        pass
    return {"arm_version": version}


# Remove GET/page loads from logging
import logging  # noqa: E402,F811
logging.getLogger('werkzeug').setLevel(logging.ERROR)
