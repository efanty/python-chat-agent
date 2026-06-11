"""
Security middleware — request pre-processing hooks for real-time defense.

Provides Flask before_request hooks that:
1. Check if the requesting IP is blocked
2. Return 403 for blocked IPs
3. Log suspicious request patterns

This middleware is optional and can be enabled/disabled via settings.
"""
from flask import request, abort, current_app
from app.logger import log_auth



def check_blocked_ip():
    """Flask before_request handler: block requests from blocked IPs.

    Returns 403 if the requesting IP is in the blocklist.
    Skips static files and certain public endpoints.
    """
    # Skip if security middleware is disabled
    # 从 app.config 读取（已在启动时从 DB 加载），避免每次请求查 DB
    enabled = current_app.config.get("security_middleware_enabled", True)
    if not enabled:
        return None


    # Skip static files
    if request.path.startswith("/static/"):
        return None

    # Get client IP
    ip = request.remote_addr or ""
    if not ip:
        return None

    # Check blocklist
    from .defender import is_blocked
    if is_blocked(ip):
        log_auth("已拦截被封禁IP的请求 — ip=%s, path=%s", ip, request.path)
        abort(403)


def init_middleware(app):
    """Register security middleware hooks on the Flask app.

    Args:
        app: Flask application instance.
    """
    app.before_request(check_blocked_ip)
