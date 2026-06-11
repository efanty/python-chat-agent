from flask import Flask, request, flash, redirect, url_for
from flask_wtf import CSRFProtect
from flask_wtf.csrf import validate_csrf as _validate_csrf, CSRFError
from functools import wraps

csrf_protect = CSRFProtect()

def init_csrf(app: Flask):
    csrf_protect.init_app(app)


def csrf_protected(f):
    """CSRF token validation for admin POST requests.

    Reads token from: form field 'csrf_token', header 'X-CSRFToken', or JSON body.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "POST":
            token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken") or ""
            if not token and request.is_json:
                body = request.get_json(silent=True) or {}
                token = body.get("csrf_token", "")
            if not token:
                flash("安全令牌缺失，请刷新页面重试。", "danger")
                return redirect(url_for("admin.dashboard"))
            try:
                _validate_csrf(token)
            except CSRFError:
                flash("安全令牌无效，请刷新页面重试。", "danger")
                return redirect(url_for("admin.dashboard"))
        return f(*args, **kwargs)
    return decorated
