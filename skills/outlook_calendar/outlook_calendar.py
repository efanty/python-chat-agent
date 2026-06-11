"""Outlook Calendar skill — add/list appointments in Windows 11 Outlook."""

import json
import datetime


def _try_import_win32():
    """Try to import win32com.client; return None if unavailable."""
    try:
        import win32com.client
        return win32com.client
    except ImportError:
        return None


def run(**kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Args (passed as keyword arguments):
        action: "add" or "list"
        subject: 日程标题
        start_time: 开始时间 "YYYY-MM-DD HH:MM"
        end_time: 结束时间 "YYYY-MM-DD HH:MM"
        body: 备注
        location: 地点
        reminder_minutes: 提前提醒分钟数
        category: 分类标签
    """
    action = kwargs.get("action", "add")

    if action == "list":
        return _list_today()
    elif action == "add":
        return _add_appointment(**kwargs)
    else:
        return json.dumps(
            {"success": False, "error": f"未知操作: {action}，支持 add / list"},
            ensure_ascii=False,
        )


def _add_appointment(**kwargs) -> str:
    """添加一条日程到 Outlook 日历。"""
    win32 = _try_import_win32()
    if win32 is None:
        return json.dumps(
            {"success": False,
             "error": "缺少依赖: pywin32 未安装。请在终端执行: pip install pywin32"},
            ensure_ascii=False,
        )

    subject = kwargs.get("subject", "").strip()
    if not subject:
        return json.dumps(
            {"success": False, "error": "缺少必需参数: subject（日程标题）"},
            ensure_ascii=False,
        )

    start_time_str = kwargs.get("start_time", "").strip()
    if not start_time_str:
        return json.dumps(
            {"success": False, "error": "缺少必需参数: start_time（开始时间，格式 YYYY-MM-DD HH:MM）"},
            ensure_ascii=False,
        )

    # 解析时间
    try:
        start_dt = datetime.datetime.strptime(start_time_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return json.dumps(
            {"success": False,
             "error": f"开始时间格式错误: {start_time_str}，正确格式: YYYY-MM-DD HH:MM"},
            ensure_ascii=False,
        )

    end_time_str = kwargs.get("end_time", "").strip()
    if end_time_str:
        try:
            end_dt = datetime.datetime.strptime(end_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            return json.dumps(
                {"success": False,
                 "error": f"结束时间格式错误: {end_time_str}，正确格式: YYYY-MM-DD HH:MM"},
                ensure_ascii=False,
            )
    else:
        # 默认 1 小时
        end_dt = start_dt + datetime.timedelta(hours=1)

    if end_dt <= start_dt:
        return json.dumps(
            {"success": False, "error": "结束时间必须晚于开始时间"},
            ensure_ascii=False,
        )

    body = kwargs.get("body", "").strip()
    location = kwargs.get("location", "").strip()
    reminder_minutes = kwargs.get("reminder_minutes")
    if reminder_minutes is not None:
        try:
            reminder_minutes = int(reminder_minutes)
        except (ValueError, TypeError):
            reminder_minutes = 15
    else:
        reminder_minutes = 15
    category = kwargs.get("category", "").strip()

    try:
        outlook = win32.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        calendar = namespace.GetDefaultFolder(9)  # olFolderCalendar = 9

        appointment = outlook.CreateItem(1)  # olAppointmentItem = 1
        appointment.Subject = subject
        appointment.Start = start_dt.strftime("%Y-%m-%d %H:%M")
        appointment.End = end_dt.strftime("%Y-%m-%d %H:%M")
        if body:
            appointment.Body = body
        if location:
            appointment.Location = location
        if reminder_minutes > 0:
            appointment.ReminderSet = True
            appointment.ReminderMinutesBeforeStart = reminder_minutes
        else:
            appointment.ReminderSet = False

        # 分类（Categories 是逗号分隔的字符串）
        if category:
            appointment.Categories = category

        appointment.Save()

        result = {
            "success": True,
            "message": f"日程已添加到 Outlook 日历: {subject}",
            "appointment": {
                "subject": subject,
                "start": start_time_str,
                "end": end_dt.strftime("%Y-%m-%d %H:%M"),
                "location": location or None,
            },
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        err_msg = str(e)
        err_code = getattr(e, 'hresult', None) or getattr(e, 'hr', None)
        is_com_class_error = (
            "CLSID" in err_msg
            or "class not registered" in err_msg.lower()
            or "无效的类字符串" in err_msg
            or err_code == -2147221005
        )
        if is_com_class_error:
            return json.dumps(
                {"success": False,
                 "error": "无法连接到 Outlook。请确认:\n"
                          "1. 本机已安装 Microsoft Outlook\n"
                          "2. Python 位数与 Office 位数一致（都是 32 位或都是 64 位）\n"
                          "3. 当前 Windows 用户已登录 Outlook"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"success": False, "error": f"Outlook 操作失败: {e}"},
            ensure_ascii=False,
        )


def _list_today() -> str:
    """列出今天 Outlook 日历中的日程。"""
    win32 = _try_import_win32()
    if win32 is None:
        return json.dumps(
            {"success": False,
             "error": "缺少依赖: pywin32 未安装。请在终端执行: pip install pywin32"},
            ensure_ascii=False,
        )

    try:
        outlook = win32.Dispatch("Outlook.Application")
        namespace = outlook.GetNamespace("MAPI")
        calendar = namespace.GetDefaultFolder(9)

        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)

        # 使用限制过滤器（Jet SQL 语法）
        restrict_filter = (
            f"[Start] >= '{today.strftime('%Y-%m-%d')}' "
            f"AND [Start] < '{tomorrow.strftime('%Y-%m-%d')}'"
        )
        items = calendar.Items
        items.Sort("[Start]")
        items.IncludeRecurrences = True

        restricted = items.Restrict(restrict_filter)

        appointments = []
        for item in restricted:
            try:
                if item.Class == 1:  # olAppointment
                    appointments.append({
                        "subject": item.Subject,
                        "start": item.Start.strftime("%Y-%m-%d %H:%M"),
                        "end": item.End.strftime("%Y-%m-%d %H:%M"),
                        "location": item.Location or "",
                    })
            except Exception:
                continue

        return json.dumps(
            {
                "success": True,
                "date": today.strftime("%Y-%m-%d"),
                "count": len(appointments),
                "appointments": appointments,
            },
            ensure_ascii=False,
        )

    except Exception as e:
        err_msg = str(e)
        err_code = getattr(e, 'hresult', None) or getattr(e, 'hr', None)
        is_com_class_error = (
            "CLSID" in err_msg
            or "class not registered" in err_msg.lower()
            or "无效的类字符串" in err_msg
            or err_code == -2147221005
        )
        if is_com_class_error:
            return json.dumps(
                {"success": False,
                 "error": "无法连接到 Outlook。请确认:\n"
                          "1. 本机已安装 Microsoft Outlook\n"
                          "2. Python 位数与 Office 位数一致（都是 32 位或都是 64 位）\n"
                          "3. 当前 Windows 用户已登录 Outlook"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"success": False, "error": f"Outlook 查询失败: {e}"},
            ensure_ascii=False,
        )
