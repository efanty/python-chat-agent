import os
from flask import render_template, redirect, url_for, send_from_directory, abort
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.utils.plugin_utils import require_plugin

@bp.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("chat.index"))
    return render_template("main/index.html")


@bp.route("/version")
def version():
    """Return the current project version."""
    version_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "VERSION")
    try:
        with open(version_path, "r", encoding="utf-8") as f:
            ver = f.read().strip()
        return ver, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception:
        return "unknown", 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/upgrade/<path:filename>")
def upgrade_file(filename):
    """Serve upgrade ZIP files from downloads directory."""
    downloads_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "downloads"
    )
    # Path traversal protection
    resolved = os.path.realpath(os.path.join(downloads_dir, filename))
    if not resolved.startswith(os.path.realpath(downloads_dir)):
        abort(403)
    if not filename.lower().endswith(".zip"):
        abort(403)
    return send_from_directory(downloads_dir, filename)
