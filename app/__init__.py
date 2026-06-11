import os
import secrets
import markdown as md_lib
from flask import Flask, render_template, redirect, url_for, request, current_app
from flask_login import current_user
from dotenv import load_dotenv
from app.extensions import init_extensions
from app.plugins import init_plugins
from app.extensions.init_csrf import csrf_protect
from app.extensions.init_sqlalchemy import db
from app.models.settings import Setting
from app.models.user import User


# Load .env from project root, override any pre-existing env vars
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_env_path, override=True)

from app.logger import get_logger
logger = get_logger()


def create_app(env=None):
    """Flask application factory."""
    app = Flask(__name__)

    # Load configuration
    app.config.from_object("app.config.DefaultConfig")
    if env == "production":
        app.config.from_object("app.config.ProductionConfig")
    elif env == "testing":
        app.config.from_object("app.config.TestingConfig")
    else:
        app.config.from_object("app.config.DevelopmentConfig")

    # Override from environment
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", app.config.get("SECRET_KEY"))
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", app.config.get("SQLALCHEMY_DATABASE_URI"))

    # Initialize extensions
    init_extensions(app)
    init_plugins(app)

    # Register blueprints
    from app.plugins.chat.main import bp as chat_bp

    # Chat blueprint — CSRF 保护已启用，前端通过 meta tag + header/form field 提交 token
    #
    #
    #
    #
    @app.route("/")
    def index():
        return redirect(url_for("main.index"))


    # Custom Jinja2 filters
    @app.template_filter("markdown")
    def markdown_filter(text):
        if not text:
            return ""
        return md_lib.markdown(
            text,
            extensions=["fenced_code", "tables", "codehilite"],
        )

    # Context processors
    @app.context_processor
    def inject_settings():
        return {
            "site_name": current_app.config.get("site_name", "DeepAgent Chat"),
            "site_description": current_app.config.get("site_description", "智能体对话平台"),
        }


    @app.context_processor
    def inject_unread():
        if current_user.is_authenticated:
            return {"unread_count": 0}
        return {"unread_count": 0}

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    # ── 维护模式 ──────────────────────────────────────────────────────
    @app.before_request
    def check_maintenance_mode():
        # 从 app.config 读取（已在启动时从 DB 加载），避免每次请求查 DB
        maintenance = current_app.config.get("maintenance_mode", False)
        if maintenance:
            # Allow admins and login page
            if request.path.startswith("/admin") or request.path == "/auth/login" or \
               request.path.startswith("/static"):
                return None
            try:
                if current_user and current_user.is_authenticated and current_user.is_admin:
                    return None
            except Exception:
                pass
            return render_template("main/maintenance.html"), 503


    # ── 安全响应头 ────────────────────────────────────────────────────
    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        # 移除 Server 头，避免暴露技术栈信息
        if "Server" in response.headers:
            del response.headers["Server"]
        if app.config.get("SESSION_COOKIE_SECURE", False):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Create tables
    with app.app_context():
        db.create_all()
        # Seed default admin if not exists
        if not User.query.filter_by(username="admin").first():
            # 使用环境变量 ADMIN_PASSWORD；未设置则自动生成 24 位随机密码
            admin_password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(24)
            admin = User(
                username="admin",
                email="admin@agentapp.local",
                role="admin",
                is_active=True,
                totp_enabled=False,
            )
            admin.set_password(admin_password)
            db.session.add(admin)
            db.session.commit()
            logger.info("=" * 60)
            logger.info("  默认管理员账户已创建")
            logger.info("   用户名: admin")
            logger.info("   密  码: %s", admin_password)
            logger.info("   邮  箱: admin@agentapp.local")
            logger.info("  ⚠ 请首次登录后立即修改密码！")
            logger.info("=" * 60)

    # ── 自动启动 local_todo 定时提醒服务 ────────────────────────────
    try:
        from skills.local_todo.local_todo import start_scheduler
        result = start_scheduler(interval=30)
        logger.info("local_todo 提醒服务: %s", result.get("message", str(result)))
    except Exception as e:
        logger.warning("local_todo 提醒服务启动失败: %s", e)

    return app
