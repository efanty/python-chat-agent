"""
Security module initialization.

Registers the security middleware and starts the background
LLM-powered log analysis loop.

The security module can be enabled/disabled via settings:
- security_enabled (bool): Master switch (default: false)
- security_analysis_interval (int): Analysis interval in seconds (default: 300)
- security_middleware_enabled (bool): Enable IP blocking middleware (default: true)
"""
from flask import Flask
from app.logger import log_admin
from app.utils.settings import get_setting_bool, get_setting_int


def init_security(app: Flask) -> None:
    """Initialize the security module.

    Registers middleware and starts the background analysis loop
    if security is enabled in settings.

    Args:
        app: Flask application instance.
    """
    # Register middleware (always, but middleware checks its own enabled flag)
    from app.security.middleware import init_middleware
    init_middleware(app)

    # Start background analysis if enabled
    # 需要在应用上下文中查询数据库设置
    with app.app_context():
        enabled = get_setting_bool("security_enabled", False)
        if enabled:
            from app.security.analyzer import start_analysis
            interval = get_setting_int("security_analysis_interval", 300)
            start_analysis(app, interval)
            log_admin("安全模块已初始化 — interval=%ds", interval)
        else:
            log_admin("安全模块未启用（可在系统设置中开启）")
