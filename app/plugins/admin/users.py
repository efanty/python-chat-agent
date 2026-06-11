from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.models.user import User
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int

# ============ User Management ============

@bp.route("/users")
@admin_required
@require_plugin(blueprint_name)
def users():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    pagination = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    users = pagination.items
    return render_template("admin/users.html", users=users, pagination=pagination)


@bp.route("/users/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def user_add():
    data = request.form
    if User.query.filter_by(username=data.get("username")).first():
        flash("用户名已存在。", "danger")
        return redirect(url_for("admin.users"))
    if User.query.filter_by(email=data.get("email")).first():
        flash("邮箱已注册。", "danger")
        return redirect(url_for("admin.users"))

    user = User(
        username=data.get("username"),
        email=data.get("email"),
        role=data.get("role", "user"),
        is_active=data.get("is_active") == "true",
        totp_required=data.get("totp_required", "false") == "true",
    )
    user.set_password(data.get("password", "12345678"))
    db.session.add(user)
    db.session.commit()
    log_admin("用户已添加 — username=%s, role=%s", data.get("username"), data.get("role"))
    flash("用户添加成功。", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    data = request.form

    if "username" in data and data["username"] != user.username:
        if User.query.filter_by(username=data["username"]).first():
            flash("用户名已存在。", "danger")
            return redirect(url_for("admin.users"))
        user.username = data["username"]

    if "email" in data and data["email"] != user.email:
        if User.query.filter_by(email=data["email"]).first():
            flash("邮箱已注册。", "danger")
            return redirect(url_for("admin.users"))
        user.email = data["email"]

    user.role = data.get("role", user.role)
    user.is_active = data.get("is_active") == "true"
    user.totp_required = data.get("totp_required", "false") == "true"

    if data.get("password"):
        user.set_password(data["password"])

    if "totp_enabled" in data:
        user.totp_enabled = data["totp_enabled"] == "true"
        if not user.totp_enabled:
            user.totp_secret = None

    db.session.commit()
    log_admin("用户已编辑 — user_id=%d, username=%s", user.id, user.username)
    flash("用户更新成功。", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def user_delete(user_id):
    if user_id == current_user.id:
        flash("不能删除自己的账户。", "danger")
        return redirect(url_for("admin.users"))
    log_admin("用户已删除 — user_id=%d", user_id)
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("用户已删除。", "success")
    return redirect(url_for("admin.users"))

