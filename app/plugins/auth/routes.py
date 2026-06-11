import smtplib
import threading
from email.mime.text import MIMEText
from email.header import Header
from app.utils.time_utils import beijing_now
from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse as url_parse
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.extensions.init_limiter import limiter
from app.plugins.auth.forms import (
    LoginForm, TOTPForm, RegisterForm, ForgotPasswordForm,
    ResetPasswordForm, ChangePasswordForm, SetupTOTPForm,
    DisableTOTPForm, NicknameForm, EmailForm
)
from app.models.user import User
from app.models.settings import Setting
from app.logger import log_auth, log_error
from app.utils.settings import get_setting, get_setting_int, get_setting_bool
import jwt
import time
from app.utils.plugin_utils import require_plugin

def _send_email_async(cfg, to_addr, subject, html_body, log_label):
    """Send email via background thread using smtplib directly."""
    def _do_send():
        try:
            msg = MIMEText(html_body, "html", "utf-8")
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = cfg.get("MAIL_DEFAULT_SENDER", "noreply@agentapp.local")
            msg["To"] = to_addr

            server = cfg.get("MAIL_SERVER", "localhost")
            port = int(cfg.get("MAIL_PORT", 587))
            username = cfg.get("MAIL_USERNAME", "") or ""
            password = cfg.get("MAIL_PASSWORD", "") or ""
            use_tls = not (port == 465)
            use_ssl = (port == 465)

            if use_ssl:
                s = smtplib.SMTP_SSL(server, port, timeout=15)
            else:
                s = smtplib.SMTP(server, port, timeout=15)
                if use_tls:
                    s.starttls()

            if username:
                s.login(username, password)
            s.sendmail(msg["From"], [to_addr], msg.as_bytes())
            s.quit()
        except Exception as e:
            log_error("%s 异步发送失败 (%s): %s", log_label, to_addr, str(e))

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()


def _build_mail_cfg():
    """Read mail config from DB settings + app.config (safe for threads)."""
    c = current_app.config
    return {
        "MAIL_SERVER": get_setting("mail_server", c.get("MAIL_SERVER", "localhost")),
        "MAIL_PORT": get_setting("mail_port", c.get("MAIL_PORT", 587)),
        "MAIL_USERNAME": get_setting("mail_username", c.get("MAIL_USERNAME", "")),
        "MAIL_PASSWORD": get_setting("mail_password", c.get("MAIL_PASSWORD", "")),
        "MAIL_DEFAULT_SENDER": get_setting("mail_default_sender", c.get("MAIL_DEFAULT_SENDER", "noreply@agentapp.local")),
    }


def send_verification_email(user):
    """Send email verification link (async)."""
    cfg = _build_mail_cfg()
    secret = current_app.config["SECRET_KEY"]
    expiry = get_setting_int("email_verify_token_expiry", 86400)
    token = jwt.encode(
        {"user_id": user.id, "type": "verify", "exp": time.time() + expiry},
        secret, algorithm="HS256"
    )
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    html = f"""<h2>欢迎注册 DeepAgent Chat</h2>
<p>请点击以下链接验证您的邮箱：</p>
<p><a href="{verify_url}">{verify_url}</a></p>
<p>此链接有效期为1小时。</p>"""
    _send_email_async(cfg, user.email, "验证您的邮箱 - DeepAgent Chat", html, "验证邮件")


def send_reset_email(user):
    """Send password reset link (async)."""
    cfg = _build_mail_cfg()
    secret = current_app.config["SECRET_KEY"]
    token = jwt.encode(
        {"user_id": user.id, "type": "reset", "exp": time.time() + get_setting_int("password_reset_token_expiry", 3600)},
        secret, algorithm="HS256"
    )
    reset_url = url_for("auth.reset_password", token=token, _external=True)
    html = f"""<h2>密码重置</h2>
<p>请点击以下链接重置您的密码：</p>
<p><a href="{reset_url}">{reset_url}</a></p>
<p>此链接有效期为1小时。</p>"""
    _send_email_async(cfg, user.email, "重置密码 - DeepAgent Chat", html, "重置邮件")


def _is_safe_redirect_url(target: str) -> bool:
    """Validate redirect target to prevent open redirect attacks."""
    if not target:
        return False
    # Only allow relative URLs (same-origin)
    parsed = url_parse(target)
    return not parsed.netloc and not parsed.scheme


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@require_plugin(blueprint_name)

def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        # ── 账号锁定检查 ──────────────────────────────────────────
        if user and user.locked_until:
            # SQLite 不保存时区信息，locked_until 读取为 naive datetime
            # 因此使用 naive 的当前时间进行比较
            from datetime import datetime as dt_mod
            now_naive = dt_mod.now()
            if user.locked_until > now_naive:
                remaining = int((user.locked_until - now_naive).total_seconds())
                log_auth("登录被拒（账号已锁定）— username=%s, remaining=%ds",
                         form.username.data, remaining)
                flash(f"账户已被锁定，请 {remaining} 秒后再试。", "danger")
                return render_template("auth/login.html", form=form)
            else:
                # 锁定时间已过，重置
                user.login_attempts = 0
                user.locked_until = None
                db.session.commit()

        if user is None or not user.check_password(form.password.data):
            log_auth("登录失败 — 用户名=%s", form.username.data)
            # ── 记录失败次数并锁定 ──────────────────────────────
            if user:
                user.login_attempts = (user.login_attempts or 0) + 1
                if user.login_attempts >= 5:
                    from datetime import timedelta
                    user.locked_until = beijing_now() + timedelta(minutes=15)
                    log_auth("账号已锁定 — username=%s, attempts=%d",
                             user.username, user.login_attempts)
                db.session.commit()
            flash("用户名或密码错误。", "danger")
            return render_template("auth/login.html", form=form)

        if not user.is_active:
            flash("账户已被禁用，请联系管理员。", "danger")
            return render_template("auth/login.html", form=form)

        if get_setting_bool("email_verification_required", False) and not user.email_verified:
            send_verification_email(user)
            flash("请先验证您的邮箱后再登录。验证邮件已发送至 %s" % user.email, "warning")
            return render_template("auth/login.html", form=form, _unverified_user_id=user.id)

        if user.is_totp_required():
            session["_login_user_id"] = user.id
            session["_login_remember"] = form.remember.data
            return redirect(url_for("auth.totp_verify"))

        # ── 登录成功，重置失败计数 ──────────────────────────────
        user.login_attempts = 0
        user.locked_until = None
        login_user(user, remember=form.remember.data)
        user.last_login = beijing_now()
        user.last_login_ip = request.remote_addr
        db.session.commit()
        log_auth("登录成功 — username=%s", user.username)
        flash(f"欢迎回来，{user.username}！", "success")

        next_page = request.args.get("next")
        if next_page and _is_safe_redirect_url(next_page):
            return redirect(next_page)
        if user.is_admin:
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("chat.index"))

    return render_template("auth/login.html", form=form)


@bp.route("/totp-verify", methods=["GET", "POST"])
@limiter.limit("10 per minute")
@require_plugin(blueprint_name)

def totp_verify():
    user_id = session.get("_login_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    form = TOTPForm()
    if form.validate_on_submit():
        user = User.query.get(user_id)
        if user and user.verify_totp(form.code.data):
            login_user(user, remember=session.get("_login_remember", False))
            session.pop("_login_user_id", None)
            session.pop("_login_remember", None)
            user.last_login = beijing_now()
            user.last_login_ip = request.remote_addr
            db.session.commit()
            log_auth("TOTP 验证成功 — username=%s", user.username)
            flash(f"欢迎回来，{user.username}！", "success")
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("chat.index"))
        log_auth("TOTP 验证失败")
        flash("TOTP验证码无效。", "danger")

    return render_template("auth/totp_verify.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("3 per minute")
@require_plugin(blueprint_name)

def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if not get_setting_bool("registration_enabled", True):
        flash("管理员已关闭注册功能。", "warning")
        return redirect(url_for("auth.login"))

    email_verify_required = get_setting_bool("email_verification_required", False)
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("用户名已被使用。", "danger")
            return render_template("auth/register.html", form=form)
        if User.query.filter_by(email=form.email.data).first():
            flash("邮箱已被注册。", "danger")
            return render_template("auth/register.html", form=form)

        user = User(
            username=form.username.data,
            email=form.email.data,
            role="user",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        log_auth("注册成功 — username=%s, email=%s", user.username, user.email)

        # Send verification email (async — error logged in thread)
        send_verification_email(user)
        if email_verify_required:
            flash("注册成功！请检查邮箱以验证您的账号后再登录。", "success")
            return redirect(url_for("auth.login"))
        flash("注册成功！请检查邮箱以验证您的账号。", "success")

        login_user(user)
        return redirect(url_for("chat.index"))

    return render_template("auth/register.html", form=form)


@bp.route("/verify-email/<token>")
@require_plugin(blueprint_name)
def verify_email(token):
    secret = current_app.config["SECRET_KEY"]
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
        if data.get("type") != "verify":
            flash("无效的验证链接。", "danger")
            return redirect(url_for("main.index"))
        user = User.query.get(data["user_id"])
        if user:
            user.email_verified = True
            db.session.commit()
            flash("邮箱验证成功！", "success")
        else:
            flash("用户不存在。", "danger")
    except jwt.ExpiredSignatureError:
        flash("验证链接已过期，请重新发送。", "danger")
    except jwt.InvalidTokenError:
        flash("无效的验证链接。", "danger")
    return redirect(url_for("main.index"))


@bp.route("/resend-verification")
@login_required
@require_plugin(blueprint_name)
def resend_verification():
    """Resend email verification link."""
    if current_user.email_verified:
        flash("您的邮箱已验证，无需重复验证。", "info")
        return redirect(url_for("auth.profile"))
    send_verification_email(current_user)
    flash("验证邮件已发送，请检查您的邮箱。", "success")
    return redirect(url_for("auth.profile"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per minute")
@require_plugin(blueprint_name)

def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
        flash("如果该邮箱已注册，重置链接已发送。", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
@require_plugin(blueprint_name)
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    secret = current_app.config["SECRET_KEY"]
    try:
        data = jwt.decode(token, secret, algorithms=["HS256"])
        if data.get("type") != "reset":
            flash("无效的重置链接。", "danger")
            return redirect(url_for("auth.login"))
        user_id = data["user_id"]
    except jwt.ExpiredSignatureError:
        flash("重置链接已过期。", "danger")
        return redirect(url_for("auth.forgot_password"))
    except jwt.InvalidTokenError:
        flash("无效的重置链接。", "danger")
        return redirect(url_for("auth.login"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user = User.query.get(user_id)
        if user:
            user.set_password(form.password.data)
            db.session.commit()
            flash("密码重置成功，请登录。", "success")
            return redirect(url_for("auth.login"))
        flash("用户不存在。", "danger")

    return render_template("auth/reset_password.html", form=form)


@bp.route("/logout")
@require_plugin(blueprint_name)
@login_required
def logout():
    log_auth("登出成功")
    logout_user()
    flash("您已退出登录。", "info")
    return redirect(url_for("main.index"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
@require_plugin(blueprint_name)
def profile():
    pwd_form = ChangePasswordForm()
    totp_setup_form = SetupTOTPForm()
    totp_disable_form = DisableTOTPForm()
    nickname_form = NicknameForm()
    email_form = EmailForm()

    return render_template(
        "auth/profile.html",
        pwd_form=pwd_form,
        totp_setup_form=totp_setup_form,
        totp_disable_form=totp_disable_form,
        nickname_form=nickname_form,
        email_form=email_form,
    )


@bp.route("/change-password", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("当前密码不正确。", "danger")
        else:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            log_auth("密码修改成功")
            flash("密码修改成功。", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.profile"))


@bp.route("/update-nickname", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def update_nickname():
    form = NicknameForm()
    if form.validate_on_submit():
        nickname = form.nickname.data.strip()
        current_user.nickname = nickname if nickname else None
        db.session.commit()
        display = nickname or current_user.username
        flash(f"昵称已更新为「{display}」。", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.profile"))



@bp.route("/update-email", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def update_email():
    form = EmailForm()
    if form.validate_on_submit():
        new_email = form.email.data.strip().lower()
        if new_email == current_user.email:
            flash("新邮箱与当前邮箱相同。", "warning")
            return redirect(url_for("auth.profile"))
        if User.query.filter_by(email=new_email).first():
            flash("该邮箱已被其他账户使用。", "danger")
            return redirect(url_for("auth.profile"))
        current_user.email = new_email
        current_user.email_verified = False
        db.session.commit()
        log_auth("邮箱已更改 - new_email=%s", new_email)
        send_verification_email(current_user)
        flash("邮箱已更改，验证邮件已发送至新邮箱。", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{error}", "danger")
    return redirect(url_for("auth.profile"))

@bp.route("/setup-totp", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def setup_totp():
    form = SetupTOTPForm()
    if form.validate_on_submit():
        if not current_user.totp_secret:
            current_user.generate_totp_secret()
            db.session.commit()
            flash("TOTP密钥已生成，请使用验证码确认启用。", "info")
            return redirect(url_for("auth.profile"))

        if current_user.verify_totp(form.code.data):
            current_user.totp_enabled = True
            db.session.commit()
            flash("TOTP已成功启用。", "success")
        else:
            log_auth("TOTP 验证失败")
            flash("TOTP验证码无效。", "danger")
    return redirect(url_for("auth.profile"))


@bp.route("/disable-totp", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def disable_totp():
    form = DisableTOTPForm()
    if form.validate_on_submit():
        if current_user.verify_totp(form.code.data):
            current_user.totp_enabled = False
            current_user.totp_secret = None
            db.session.commit()
            flash("TOTP已禁用。", "success")
        else:
            log_auth("TOTP 验证失败")
            flash("TOTP验证码无效。", "danger")
    return redirect(url_for("auth.profile"))


@bp.route("/generate-totp-secret")
@login_required
@require_plugin(blueprint_name)
def generate_totp_secret():
    if not current_user.totp_secret:
        secret = current_user.generate_totp_secret()
        db.session.commit()
    else:
        secret = current_user.totp_secret
    qrcode_b64 = current_user.get_totp_qrcode()
    uri = current_user.get_totp_uri()
    return render_template("auth/totp_setup.html", secret=secret, qrcode=qrcode_b64, uri=uri)
