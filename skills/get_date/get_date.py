"""Get date skill — current time, lunar calendar, date arithmetic.

Real solar→lunar conversion using lookup table (1900–2100).
"""

import json
from datetime import datetime, timedelta
from app.utils.time_utils import beijing_now


# ── Lunar calendar data (1900–2100) ─────────────────────────────────────
# Each entry encodes one lunar year:
#   bits 0–3: leap month (0 = none)
#   bits 4–15: days in months 1–12, 0=29 days, 1=30 days
#   bit 16: leap month days (0=29, 1=30) — only valid if leap month > 0

LUNAR_DATA = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0,
    0x09ad0, 0x055d2, 0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540,
    0x0d6a0, 0x0ada2, 0x095b0, 0x14977, 0x04970, 0x0a4b0, 0x0b4b5, 0x06a50,
    0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970, 0x06566, 0x0d4a0,
    0x0ea50, 0x16a95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2,
    0x0a950, 0x0b557, 0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5b0, 0x14573,
    0x052b0, 0x0a9a8, 0x0e950, 0x06aa0, 0x0aea6, 0x0ab50, 0x04b60, 0x0aae4,
    0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0, 0x096d0, 0x04dd5,
    0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46,
    0x0ab60, 0x09570, 0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58,
    0x05ac0, 0x0ab60, 0x096d5, 0x092e0, 0x0c960, 0x0d954, 0x0d4a0, 0x0da50,
    0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5, 0x0a950, 0x0b4a0,
    0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260,
    0x0ea65, 0x0d530, 0x05aa0, 0x076a3, 0x096d0, 0x04afb, 0x04ad0, 0x0a4d0,
    0x1d0b6, 0x0d250, 0x0d520, 0x0dd45, 0x0b5a0, 0x056d0, 0x055b2, 0x049b0,
    0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0, 0x14b63, 0x09370,
    0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06aa0, 0x1a6c4, 0x0aae0,
    0x092e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0,
    0x0a6d0, 0x055d4, 0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50,
    0x055a0, 0x0aba4, 0x0a5b0, 0x052b0, 0x0b273, 0x06930, 0x07337, 0x06aa0,
    0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160, 0x0e968, 0x0d520,
    0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a4d0, 0x0d150, 0x0f252,
    0x0d520,
]

LUNAR_MONTHS = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
LUNAR_DAYS = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]
HEAVENLY_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ZODIACS = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# Base date: 1900-01-31 = 农历庚子年正月初一
LUNAR_BASE = datetime(1900, 1, 31)
LUNAR_BASE_YEAR = 1900


def _year_days(y: int) -> int:
    """Total days in lunar year y."""
    total = 0
    data = LUNAR_DATA[y - LUNAR_BASE_YEAR]
    for m in range(12):
        total += 29 + ((data >> (15 - m)) & 1)
    leap = data & 0xf
    if leap:
        total += 29 + ((data >> 16) & 1)
    return total


def _leap_month(y: int) -> int:
    """Leap month of lunar year y (0 if none)."""
    return LUNAR_DATA[y - LUNAR_BASE_YEAR] & 0xf


def _leap_days(y: int) -> int:
    """Days in leap month of lunar year y."""
    if _leap_month(y):
        return 29 + ((LUNAR_DATA[y - LUNAR_BASE_YEAR] >> 16) & 1)
    return 0


def _month_days(y: int, m: int) -> int:
    """Days in month m of lunar year y (m: 1–12, or negative for leap)."""
    data = LUNAR_DATA[y - LUNAR_BASE_YEAR]
    if m > 0:
        return 29 + ((data >> (15 - (m - 1))) & 1)
    elif m < 0:
        return _leap_days(y)
    return 0


def _solar_to_lunar(dt: datetime) -> dict:
    """Convert solar date to lunar date using lookup table."""
    offset = (dt.date() - LUNAR_BASE.date()).days
    if offset < 0:
        return {"lunar_date": "1900年前", "error": "仅支持1900年后"}

    y = LUNAR_BASE_YEAR
    # Skip whole years
    while offset >= _year_days(y):
        offset -= _year_days(y)
        y += 1

    # Find month
    leap = _leap_month(y)
    is_leap = False
    m = 1
    while m <= 12:
        days = _month_days(y, m)
        if offset < days:
            break
        offset -= days
        if leap and m == leap:
            ldays = _leap_days(y)
            if offset < ldays:
                is_leap = True
                break
            offset -= ldays
        m += 1

    day = offset + 1
    month_name = LUNAR_MONTHS[(m - 1) % 12]
    day_name = LUNAR_DAYS[(day - 1) % 30]

    if is_leap:
        lunar_str = f"闰{month_name}月{day_name}"
    else:
        lunar_str = f"{month_name}月{day_name}"

    return {
        "lunar_date": lunar_str,
        "lunar_year": y,
        "lunar_month": m,
        "lunar_day": day,
        "is_leap": is_leap,
        "zodiac": ZODIACS[(y - 4) % 12],
        "heavenly_stem": HEAVENLY_STEMS[(y - 4) % 10],
        "earthly_branch": EARTHLY_BRANCHES[(y - 4) % 12],
        "ganzhi": f"{HEAVENLY_STEMS[(y - 4) % 10]}{EARTHLY_BRANCHES[(y - 4) % 12]}年",
    }


def _parse_date(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {s}")


# ── Top-level entry point ───────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    action = action or kwargs.get("op", "")
    expr = expression or kwargs.get("query", "")

    if action in ("now", "当前时间", ""):
        return _now()
    elif action in ("date", "日期", "指定日期"):
        return _date_info(expr)
    elif action in ("calc", "计算", "日期计算"):
        return _date_calc(expr, **kwargs)
    else:
        if not expr or expr.lower() in ("now", "现在", "当前", "today"):
            return _now()
        return _date_info(expr)


def _now() -> str:
    now = datetime.now()
    utc = beijing_now()
    wn = now.weekday()
    lunar = _solar_to_lunar(now)
    return json.dumps({
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "utc": utc.strftime("%Y-%m-%d %H:%M:%S"),
        "year": now.year, "month": now.month, "day": now.day,
        "hour": now.hour, "minute": now.minute, "second": now.second,
        "weekday": WEEKDAYS[wn],
        "is_weekend": wn >= 5,
        "week_number": now.isocalendar()[1],
        "day_of_year": now.timetuple().tm_yday,
        "quarter": (now.month - 1) // 3 + 1,
        "timestamp": int(now.timestamp()),
        "lunar": lunar,
    }, ensure_ascii=False)


def _date_info(expr: str) -> str:
    try:
        dt = _parse_date(expr) if expr else datetime.now()
    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    wn = dt.weekday()
    is_leap = (dt.year % 4 == 0 and dt.year % 100 != 0) or (dt.year % 400 == 0)
    lunar = _solar_to_lunar(dt)
    return json.dumps({
        "success": True,
        "date": dt.strftime("%Y-%m-%d"),
        "year": dt.year, "month": dt.month, "day": dt.day,
        "weekday": WEEKDAYS[wn],
        "is_weekend": wn >= 5,
        "week_number": dt.isocalendar()[1],
        "day_of_year": dt.timetuple().tm_yday,
        "quarter": (dt.month - 1) // 3 + 1,
        "is_leap_year": is_leap,
        "lunar": lunar,
    }, ensure_ascii=False)


def _date_calc(expr: str, **kwargs) -> str:
    args = {}
    if expr and expr.strip().startswith("{"):
        try:
            args = json.loads(expr)
        except json.JSONDecodeError:
            pass
    base_str = args.get("base") or kwargs.get("base_date", "")
    days = int(args.get("days", kwargs.get("days", 0)))
    months = int(args.get("months", kwargs.get("months", 0)))
    years = int(args.get("years", kwargs.get("years", 0)))
    op = args.get("op", kwargs.get("operation", "add")).lower()

    try:
        base = _parse_date(base_str) if base_str else datetime.now()
    except ValueError:
        return json.dumps({"success": False, "error": f"日期格式错误: {base_str}"}, ensure_ascii=False)

    y, m, d = base.year, base.month, base.day
    if op in ("subtract", "sub", "减"):
        years, months, days = -years, -months, -days
    total_months = y * 12 + (m - 1) + months + years * 12
    y2, m2 = divmod(total_months, 12)
    m2 += 1
    try:
        result = datetime(y2, m2, min(d, 28)) + timedelta(days=days + (d - min(d, 28)))
    except ValueError:
        result = datetime(y2, m2, 1) + timedelta(days=days + d - 1)

    return json.dumps({
        "success": True,
        "base_date": base.strftime("%Y-%m-%d"),
        "result_date": result.strftime("%Y-%m-%d"),
        "operation": op,
        "days": days, "months": months, "years": years,
        "total_days_diff": (result - base).days,
    }, ensure_ascii=False)
