import os
import sys
import datetime


basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

class DefaultConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # ── 数据库配置 ──────────────────────────────────────────────────
    # 默认 SQLite，切换 MySQL 只需修改 .env 中的 DATABASE_URL:
    #   SQLite:  sqlite:///app.db
    #   MySQL:   mysql+pymysql://user:pass@localhost:3306/dbname?charset=utf8mb4
    # 切换后首次启动会自动建表（需提前创建数据库）
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 连接池 / 线程安全 — SQLite 需要 check_same_thread=False
    _db_url = SQLALCHEMY_DATABASE_URI
    if _db_url and _db_url.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {
            "connect_args": {"check_same_thread": False},
        }
    else:
        # MySQL / PostgreSQL 连接池配置
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_recycle": 300,       # 5 分钟回收，避免 MySQL wait_timeout 断开
            "pool_pre_ping": True,
            "pool_use_lifo": True,     # LIFO 减少连接建立开销
        }


    #theme setting
    BOOTSTRAP_SERVE_LOCAL = 'True'
    THEMES = [('cerulean','cerulean'), ('cosmo','cosmo'), ('cyborg','cyborg'), ('darkly','darkly'), ('flatly','flatly'), 
                ('journal','journal'), ('litera','litera'), ('lumen','lumen'), ('lux','lux'), 
                ('materia','materia'), ('minty','minty'), ('pulse','pulse'), ('sandstone','sandstone'), 
                ('simplex','simplex'), ('sketchy','sketchy'), ('slate','slate'), ('solar','solar'), 
                ('spacelab','spacelab'), ('superhero','superhero'), ('united','united'), ('yeti','yeti')
                ]
    BOOTSTRAP_BOOTSWATCH_THEME = 'cosmo'  # 默认主题
    SLOW_QUERY_THRESHOLD = 1

    #Page setting
    POST_PER_PAGE = 15
    COMMENT_PER_PAGE = 15

     # 插件配置
    # 基础插件列表 - 这些插件是网站运行必需的，不可删除或停用
    CORE_PLUGINS = ['main', 'admin', 'auth', 'chat', 'plugin_manager']
    
    # 启用的插件文件夹列表
    PLUGIN_ENABLE_FOLDERS = ['main', 'admin', 'auth', 'chat', 'plugin_manager', 'test_plugin', 'todoism']
    
    # 插件上传配置
    PLUGIN_UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'plugins')
    PLUGIN_MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    PLUGIN_ALLOWED_EXTENSIONS = {'zip'}



    # Flask-Mail
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    # Port-based auto-detect: 465 → SSL, 587/25 → TLS
    MAIL_USE_SSL = (MAIL_PORT == 465)
    MAIL_USE_TLS = not MAIL_USE_SSL
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@agentapp.local")

    # 邮件验证配置
    EMAIL_VERIFICATION_REQUIRED = os.environ.get('EMAIL_VERIFICATION_REQUIRED', 'true').lower() in ['true', '1', 't']
    EMAIL_VERIFICATION_TOKEN_EXPIRY = 24 * 3600  # 24小时
    PASSWORD_RESET_TOKEN_EXPIRY = 3600  # 1小时

    # Upload — 安全网上限（1GB），各路由自行从数据库 max_upload_size_mb 读取实际限制
    MAX_CONTENT_LENGTH = 30 * 1024 * 1024  # 1GB
    _base_dir = os.path.dirname(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    SANDBOX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox")
    SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")

    # Chroma
    CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")

    # Session
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(days=14)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in ("true", "1")
    SESSION_TYPE = "filesystem" # 默认使用文件系统来保存会话
    SESSION_PERMANENT = False  # 会话是否持久化
    SESSION_USE_SIGNER = True  # 是否对发送到浏览器上 session 的 cookie 值进行加密


class DevelopmentConfig(DefaultConfig):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class TestingConfig(DefaultConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


class ProductionConfig(DefaultConfig):
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig
}