"""
Runtime-configurable settings from DB (Setting model) with fallback defaults.
In-memory TTL cache to reduce redundant DB queries.
"""
import time

_setting_cache = {}         # key → (value, expiry_ts)
_cache_ttl = 30             # seconds, configs change rarely


def _cache_get(key: str):
    """Get from cache if still fresh."""
    entry = _setting_cache.get(key)
    if entry and entry[1] > time.time():
        return entry[0]
    return None


def _cache_set(key: str, value):
    _setting_cache[key] = (value, time.time() + _cache_ttl)


def clear_settings_cache():
    """Force-clear the entire cache (e.g. after admin saves settings)."""
    _setting_cache.clear()


def get_setting(key: str, default=None):
    """Read a setting from the DB Setting model at runtime.

    Priority:
    1. Local TTL cache (fastest)
    2. app.config (loaded at startup from DB, no DB query)
    3. Direct DB query (fallback)

    Results are cached for {_cache_ttl}s to avoid repeated DB hits.
    Falls back to `default` if the key is not set or the DB is unreachable.
    """
    # 1. Check local TTL cache first
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # 2. Try app.config (loaded at startup from DB, zero DB query)
    try:
        from flask import current_app
        if current_app and key in current_app.config:
            val = current_app.config[key]
            _cache_set(key, val)
            return val
    except Exception:
        pass

    # 3. Fallback: direct DB query
    try:
        from app.models.settings import Setting
        val = Setting.get(key)
        if val is not None:
            _cache_set(key, val)
            return val
    except Exception:
        pass
    return default



def get_setting_int(key: str, default: int = 0) -> int:
    """Read a setting and convert to int."""
    try:
        return int(get_setting(key, default))
    except (ValueError, TypeError):
        return default


def get_setting_float(key: str, default: float = 0.0) -> float:
    """Read a setting and convert to float."""
    try:
        return float(get_setting(key, default))
    except (ValueError, TypeError):
        return default


def get_setting_bool(key: str, default: bool = False) -> bool:
    """Read a setting and convert to bool."""
    val = get_setting(key, None)
    if val is None:
        return default
    return str(val).lower() in ("true", "1", "yes")


def coerce_setting_value(key: str, value: str):
    """将字符串设置值转换为适当类型。

    与 load_settings_from_db 的逻辑一致：
    - "true"/"false" → bool
    - 纯数字 → int
    - 浮点数 → float
    - 逗号分隔的特定 key → list
    - 其他 → 原样返回
    """
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if v.isdigit():
        return int(v)
    try:
        return float(v)
    except ValueError:
        pass
    if key in ("PLUGIN_ENABLE_FOLDERS", "ALLOWED_EXTENSIONS") and v:
        return [item.strip() for item in v.split(",") if item.strip()]
    return value
