"""\u65f6\u95f4\u5de5\u5177\u51fd\u6570\u3002

\u9ed8\u8ba4\u4f7f\u7528\u5317\u4eac\u65f6\u95f4\uff08Asia/Shanghai, UTC+8\uff09\uff0c\u53ef\u901a\u8fc7 TIMEZONE \u73af\u5883\u53d8\u91cf\u6216
\u6570\u636e\u8868 settings \u4e2d app_timezone \u952e\u81ea\u5b9a\u4e49\u3002
"""

import os
import threading
from datetime import datetime, timezone, timedelta

try:
    import zoneinfo
except ImportError:
    try:
        from backports import zoneinfo
    except ImportError:
        zoneinfo = None


_tz_cache = None
_tz_cache_lock = threading.Lock()


def _get_zoneinfo(tz_name: str):
    """Try to create a ZoneInfo object, returns None on failure."""
    if zoneinfo is not None:
        try:
            return zoneinfo.ZoneInfo(tz_name)
        except (KeyError, TypeError):
            pass
    return None


def _load_timezone_from_db():
    """从数据库加载时区设置，失败返回 None。"""
    try:
        from app.models.settings import Setting
        val = Setting.get("app_timezone")
        if val:
            return _get_zoneinfo(val)
    except Exception:
        pass
    return None


def get_app_tz():
    """返回当前应用时区，优先级：环境变量 > DB 设置 > 默认北京时间。

    环境变量每次调用都检查，DB 值缓存在内存中。
    调用 clear_tz_cache() 可清除缓存，使 DB 新值生效。
    """
    global _tz_cache

    # 环境变量优先级最高，每次都检查（无 DB 开销）
    tz_name = os.environ.get("APP_TIMEZONE", "")
    if tz_name:
        tz = _get_zoneinfo(tz_name)
        if tz is not None:
            return tz

    # 检查缓存
    if _tz_cache is not None:
        return _tz_cache

    # 从 DB 加载
    with _tz_cache_lock:
        if _tz_cache is not None:
            return _tz_cache
        tz = _load_timezone_from_db()
        if tz is not None:
            _tz_cache = tz
            return _tz_cache

    # 默认：北京时间
    return timezone(timedelta(hours=8), name="Asia/Shanghai")


def clear_tz_cache():
    """\u6e05\u9664\u65f6\u533a\u7f13\u5b58\uff0c\u4e0b\u6b21\u8c03\u7528 get_app_tz() \u65f6\u4ece DB \u91cd\u65b0\u52a0\u8f7d\u3002"""
    global _tz_cache
    with _tz_cache_lock:
        _tz_cache = None


APP_TZ = get_app_tz()


def beijing_now() -> datetime:
    """\u8fd4\u56de\u5f53\u524d\u5e94\u7528\u65f6\u533a\u7684 aware datetime\u3002"""
    return datetime.now(get_app_tz())
