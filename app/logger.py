"""
Unified logging module for DeepAgent Chat.

Usage:
    from app.logger import log_action, log_error, log_auth, log_admin

    log_auth("登录成功 — username=%(user)s", user="admin")
    log_admin("用户已删除 — target_id=%(target)s", target=user_id)
    log_action("对话已创建 — conv_id=%(id)s", id=conv.id)
    log_error("API 调用失败: %(detail)s", detail=str(e))

Output format:
    2026-04-26 19:35:00 | INFO  | user(admin/1) | 192.168.1.100 | POST /api/chat/stream | [操作] 消息已发送
    2026-04-26 19:35:05 | ERROR | user(admin/1) | 192.168.1.100 | POST /api/auth/login | [认证] 登录失败 — 密码错误
                                                                     Traceback (most recent call last): ...

Log files (under logs/):
    app.log       — 全部日志 (DEBUG+)
    app-error.log — 仅错误日志 (ERROR+)
"""
import os
import logging
import logging.handlers
from typing import Optional


# ── Log directory ─────────────────────────────────────────────────────────

_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_log_dir, exist_ok=True)


# ── Custom formatter ──────────────────────────────────────────────────────

class RequestFormatter(logging.Formatter):
    """Formatter that injects request context (user, IP, method, path)."""

    def format(self, record: logging.LogRecord) -> str:
        # Inject extra fields if available; fall back to safe defaults
        user_str = getattr(record, "_user", "-")
        ip = getattr(record, "_ip", "-")
        method = getattr(record, "_method", "-")
        path = getattr(record, "_path", "-")
        tag = getattr(record, "_tag", "")

        # Build display message WITHOUT mutating record.msg (shared across handlers)
        display_msg = f"{tag} {record.msg}" if tag else record.msg
        # Temporarily substitute so super().format() applies the % formatting
        saved = record.msg
        record.msg = display_msg
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(5)
        message = super().format(record)
        record.msg = saved  # restore
        return f"{timestamp} | {level} | {user_str} | {ip} | {method} {path} | {message}"


# ── Logger setup ──────────────────────────────────────────────────────────

_logger = logging.getLogger("deepagent")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False  # prevent duplicate logs via root logger

# Format (without prefix — prefix is added by RequestFormatter)
_base_fmt = "%(message)s"
_formatter = RequestFormatter(_base_fmt)

# 1) File handler — everything
_fh = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5,
    encoding="utf-8",
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_formatter)
_logger.addHandler(_fh)

# 2) File handler — errors only
_eh = logging.handlers.RotatingFileHandler(
    os.path.join(_log_dir, "app-error.log"), maxBytes=10 * 1024 * 1024, backupCount=3,
    encoding="utf-8",
)
_eh.setLevel(logging.ERROR)
_eh.setFormatter(_formatter)
_logger.addHandler(_eh)

# 3) Console handler — INFO+
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(_formatter)
_logger.addHandler(_ch)


# ── Request-context helpers ───────────────────────────────────────────────

def _extract_request_context():
    """Extract user/IP/method/path from the current Flask request context.

    Returns a dict suitable for passing as extra to logging.
    """
    from flask import request, has_request_context
    from flask_login import current_user

    ip = "-"
    method = "-"
    path = "-"
    user_str = "-"

    if has_request_context():
        ip = request.remote_addr or "-"
        method = request.method
        path = request.path

        try:
            if current_user and current_user.is_authenticated:
                uid = getattr(current_user, "id", "?")
                uname = getattr(current_user, "username", "?")
                user_str = f"user({uname}/{uid})"
        except (RuntimeError, Exception):
            pass

    return {"_user": user_str, "_ip": ip, "_method": method, "_path": path}


# ── Public API ────────────────────────────────────────────────────────────

def log_action(message: str, *args, **kwargs):
    """Log a general business operation.  Tag: [操作]"""
    ctx = _extract_request_context()
    ctx["_tag"] = "[操作]"
    _logger.info(message, *args, extra=ctx)


def log_error(message: str, *args, exc_info: Optional[bool] = True, **kwargs):
    """Log an error with optional traceback.  Tag: [错误]"""
    ctx = _extract_request_context()
    ctx["_tag"] = "[错误]"
    _logger.error(message, *args, extra=ctx, exc_info=exc_info)


def log_auth(message: str, *args, **kwargs):
    """Log an authentication event (login, logout, register, TOTP).  Tag: [认证]"""
    ctx = _extract_request_context()
    ctx["_tag"] = "[认证]"
    _logger.info(message, *args, extra=ctx)


def log_admin(message: str, *args, **kwargs):
    """Log an admin panel operation (CRUD, settings).  Tag: [管理]"""
    ctx = _extract_request_context()
    ctx["_tag"] = "[管理]"
    _logger.info(message, *args, extra=ctx)


# ── Convenience alias for general logging ─────────────────────────────────

def get_logger() -> logging.Logger:
    """Return the underlying logger for advanced usage."""
    return _logger
