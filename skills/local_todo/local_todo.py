"""
本地待办提醒 Skill
===================
功能：增、查、改、删待办事项，定时检查并弹出系统通知提醒
数据存储在本地 JSON 文件
"""

import json
import os
import datetime
import threading
import time
import ctypes
import ctypes.wintypes

# ========== 配置 ==========
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DATA_FILE = os.path.join(DATA_DIR, "todos.json")
os.makedirs(DATA_DIR, exist_ok=True)

# ========== Windows 原生通知 ==========

# Windows API 常量
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
NIF_INFO = 0x10
NIIF_INFO = 1
NIIF_USER = 4
NIIF_LARGE_ICON = 0x20
WM_DESTROY = 2
CW_USEDEFAULT = 8
WS_OVERLAPPED = 0x00000000
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 16
LR_DEFAULTSIZE = 0x0040
NOTIFYICON_VERSION_4 = 4

# GUID 结构
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_byte * 8),
    ]

# NOTIFYICONDATAW 结构
class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint),
        ("uFlags", ctypes.c_uint),
        ("uCallbackMessage", ctypes.c_uint),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_ulong),
        ("dwStateMask", ctypes.c_ulong),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.c_uint),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_ulong),
        ("guidItem", GUID),
        ("hBalloonIcon", ctypes.c_void_p),
    ]

# 加载 Windows API
_shell32 = ctypes.windll.shell32
_user32 = ctypes.windll.user32

# 替换原来的 _notify 函数
def _notify(title, message):
    """使用 plyer 弹出系统通知"""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="本地待办提醒",
            timeout=15
        )
        return True
    except ImportError:
        # 如果 plyer 未安装，尝试 win11toast
        try:
            from win11toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(title, message, duration=5, threaded=True)
            return True
        except ImportError:
            # 最后的备选方案：使用 MessageBox
            try:
                ctypes.windll.user32.MessageBoxW(0, message, title, 0)
                return True
            except:
                print(f"无法显示通知: {title} - {message}")
                return False
    except Exception as e:
        print(f"通知失败: {e}")
        return False
# ========== 数据层 ==========

def _load():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(todos):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=2, ensure_ascii=False)

def _next_id(todos):
    return max([t["id"] for t in todos], default=0) + 1

# ========== 业务层 ==========

def add(title, due_time=None, note="", **kwargs):
    """
    添加待办事项
    :param title: 标题（必填）
    :param due_time: 提醒时间，格式 "HH:MM" 或 "YYYY-MM-DD HH:MM"
    :param note: 备注
    :return: 添加后的待办对象
    """
    todos = _load()
    todo = {
        "id": _next_id(todos),
        "title": title,
        "due_time": due_time,
        "note": note,
        "done": False,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    todos.append(todo)
    _save(todos)
    return {"success": True, "todo": todo, "message": f"✅ 已添加: [{todo['id']}] {title}"}

def list_todos(show_done=False, keyword=None):
    """
    查询待办事项
    :param show_done: 是否显示已完成的
    :param keyword: 按标题关键词搜索
    :return: 待办列表
    """
    todos = _load()
    if not show_done:
        todos = [t for t in todos if not t["done"]]
    if keyword:
        todos = [t for t in todos if keyword.lower() in t["title"].lower()]
    
    todos.sort(key=lambda x: x["id"])
    
    return {
        "success": True,
        "count": len(todos),
        "todos": todos
    }

def update(todo_id, title=None, due_time=None, note=None, done=None):
    """
    更新待办事项
    :param todo_id: 待办 ID
    :param title: 新标题
    :param due_time: 新提醒时间
    :param note: 新备注
    :param done: 完成状态 True/False
    :return: 更新后的待办对象或错误信息
    """
    todos = _load()
    for t in todos:
        if t["id"] == todo_id:
            if title is not None:
                t["title"] = title
            if due_time is not None:
                t["due_time"] = due_time
            if note is not None:
                t["note"] = note
            if done is not None:
                t["done"] = done
            _save(todos)
            return {"success": True, "todo": t, "message": f"✅ 已更新 [{todo_id}]"}
    return {"success": False, "message": f"❌ 未找到 ID={todo_id}"}

def delete(todo_id):
    """
    删除待办事项
    :param todo_id: 待办 ID
    """
    todos = _load()
    new_todos = [t for t in todos if t["id"] != todo_id]
    if len(new_todos) == len(todos):
        return {"success": False, "message": f"❌ 未找到 ID={todo_id}"}
    _save(new_todos)
    return {"success": True, "message": f"🗑️ 已删除 [{todo_id}]"}

def check_and_notify():
    """
    检查是否有到期的待办并发送通知
    由定时器自动调用，也可手动触发
    
    匹配规则：
    - 格式 "HH:MM"：每天该时间点触发（精确到分钟）
    - 格式 "YYYY-MM-DD HH:MM"：在指定日期的该时间点触发（精确到分钟）
    - 已过期的待办（超过当前时间5分钟内）：也会触发一次提醒，然后标记为已通知
    """
    todos = _load()
    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")
    current_time = now.strftime("%H:%M")
    
    notified = []
    for t in todos:
        if t["done"]:
            continue
        due = t["due_time"]
        if not due:
            continue
        
        # 检查是否已经通知过（避免重复通知）
        if t.get("notified"):
            continue
        
        should_notify = False
        if " " in due:
            # 格式 "YYYY-MM-DD HH:MM" — 精确匹配或已过期
            should_notify = due <= now_str
        else:
            # 格式 "HH:MM" — 每天该时间点触发
            should_notify = due == current_time
        
        if should_notify:
            _notify("⏰ 待办提醒", f"{t['title']}\n{t['note'] if t['note'] else ''}")
            # 标记为已通知，避免重复提醒
            t["notified"] = True
            _save(todos)
            notified.append(t["title"])
    
    return {"success": True, "notified": notified}

# ========== 定时器 ==========

_scheduler_running = False

def start_scheduler(interval=30):
    """启动后台定时检查线程"""
    global _scheduler_running
    if _scheduler_running:
        return {"success": True, "message": "提醒服务已在运行中"}
    
    def _run():
        global _scheduler_running
        _scheduler_running = True
        while _scheduler_running:
            try:
                check_and_notify()
            except Exception:
                pass
            time.sleep(interval)
    
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"success": True, "message": f"🔄 提醒服务已启动（每{interval}秒检查一次）"}

def stop_scheduler():
    """停止定时检查线程"""
    global _scheduler_running
    _scheduler_running = False
    return {"success": True, "message": "⏹️ 提醒服务已停止"}

# ========== 主入口（供智能体调用）==========

def run(expression, action, **kwargs):
    """
    Skill 主入口
    
    参数（通过 expression 或 kwargs 传入）:
    - action: add / list / update / delete / check / start / stop
    - title: 标题（add 用）
    - due_time: 提醒时间（add/update 用）
    - note: 备注（add/update 用）
    - todo_id: 待办 ID（update/delete 用）
    - done: 完成状态（update 用）
    - show_done: 是否显示已完成（list 用）
    - keyword: 关键词搜索（list 用）
    """
    action = kwargs.get("action", action or "list")
    
    if action == "add":
        title = kwargs.get("title", "")
        if not title:
            return json.dumps({"success": False, "message": "❌ 标题不能为空"}, ensure_ascii=False)
        due_time = kwargs.get("due_time")
        note = kwargs.get("note", "")
        return json.dumps(add(title, due_time, note), ensure_ascii=False)
    
    elif action == "list":
        show_done = kwargs.get("show_done", False)
        keyword = kwargs.get("keyword")
        return json.dumps(list_todos(show_done, keyword), ensure_ascii=False)
    
    elif action == "update":
        todo_id = int(kwargs.get("todo_id", 0))
        if not todo_id:
            return json.dumps({"success": False, "message": "❌ 请提供 todo_id"}, ensure_ascii=False)
        title = kwargs.get("title")
        due_time = kwargs.get("due_time")
        note = kwargs.get("note")
        done = kwargs.get("done")
        if done is not None:
            done = str(done).lower() in ("true", "1", "yes")
        return json.dumps(update(todo_id, title, due_time, note, done), ensure_ascii=False)
    
    elif action == "delete":
        todo_id = int(kwargs.get("todo_id", 0))
        if not todo_id:
            return json.dumps({"success": False, "message": "❌ 请提供 todo_id"}, ensure_ascii=False)
        return json.dumps(delete(todo_id), ensure_ascii=False)
    
    elif action == "check":
        return json.dumps(check_and_notify(), ensure_ascii=False)
    
    elif action == "start":
        interval = int(kwargs.get("interval", 30))
        return json.dumps(start_scheduler(interval), ensure_ascii=False)
    
    elif action == "stop":
        return json.dumps(stop_scheduler(), ensure_ascii=False)
    
    else:
        return json.dumps({
            "success": False,
            "message": f"❌ 不支持的操作: {action}，可用: add / list / update / delete / check / start / stop"
        }, ensure_ascii=False)
