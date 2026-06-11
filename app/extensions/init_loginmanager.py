from flask import Flask, abort, flash, redirect, url_for
from flask_login import LoginManager, current_user, login_required
from functools import wraps

login_manager = LoginManager()

def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash("需要管理员权限。", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated


@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    user = User.query.get(int(user_id))
    return user

def init_loginManager(app: Flask):
    login_manager.init_app(app)
    

login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录以访问此页面。"
login_manager.login_message_category = "warning"