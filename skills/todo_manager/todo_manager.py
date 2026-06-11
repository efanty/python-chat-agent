"""todo_manager Skill — 待办事项管理。

支持对待办事项的增、查、改、删操作，基于 SQLAlchemy ORM。
每次操作自动记录日志到 logs/app.log。
"""

import json
import logging
import datetime

_logger = logging.getLogger("deepagent")

_ACTION_DESCRIPTION = "todo 管理"

# ── Flask app context 辅助 ────────────────────────────────────────────

def _ensure_app_context():
    """确保 Flask app 上下文存在。生产环境下已有，无需操作。"""
    from flask import current_app
    try:
        _ = current_app.name
        return None
    except RuntimeError:
        pass

    try:
        from app import create_app
        app = create_app()
        ctx = app.app_context()
        ctx.push()
        return ctx
    except (ImportError, ModuleNotFoundError):
        raise RuntimeError(
            "无法创建 Flask 应用上下文（缺少依赖模块），"
            "请在项目完整环境下使用此 Skill。"
        )


def _cleanup_context(ctx):
    """弹出手动创建的 app context。"""
    if ctx is not None:
        ctx.pop()


def _log(operation: str, detail: str, todo_id=None, success=True):
    """写操作日志。"""
    status = "✓" if success else "✗"
    id_part = f" | ID: {todo_id}" if todo_id is not None else ""
    msg = f"[{_ACTION_DESCRIPTION}] {status} {operation}{id_part} | {detail}"
    if success:
        _logger.info(msg)
    else:
        _logger.error(msg)


def _get_current_user_info(_user_id=None, _is_admin=False) -> dict:
    """获取当前登录用户的信息（id, is_admin）。

    优先使用传入的 _user_id/_is_admin（支持线程池调用），
    回退到 flask_login.current_user。
    """
    if _user_id is not None:
        return {
            "id": int(_user_id),
            "is_admin": bool(_is_admin),
            "username": "?",
        }
    from flask_login import current_user
    try:
        if current_user and current_user.is_authenticated:
            return {
                "id": current_user.id,
                "is_admin": getattr(current_user, "is_admin", False),
                "username": getattr(current_user, "username", "?"),
            }
    except (RuntimeError, AttributeError):
        pass
    raise RuntimeError("无法获取当前用户信息：未登录或无用户上下文。")


# ── 操作实现 ──────────────────────────────────────────────────────────

def _list_todos(user_id=None, done=None, keyword=None, limit=50) -> str:
    """查询待办事项列表。"""
    from app.extensions.init_sqlalchemy import db
    from app.models.todo import Todo
    from app.models.user import User

    query = Todo.query

    if user_id is not None:
        try:
            uid = int(user_id)
            query = query.filter_by(author_id=uid)
        except (ValueError, TypeError):
            pass

    if done is not None:
        if isinstance(done, str):
            done = done.lower() in ("1", "true", "yes", "是")
        query = query.filter_by(done=bool(done))

    if keyword:
        query = query.filter(Todo.body.contains(keyword))

    query = query.order_by(Todo.timestamp.desc()).limit(min(max(limit, 1), 200))
    todos = query.all()

    if not todos:
        return "暂无待办事项。"

    lines = [
        "ID | 内容 | 状态 | 分类 | 截止日期 | 创建者 | 时间",
        "-" * 80,
    ]
    for t in todos:
        author_name = t.author.nickname or t.author.username if t.author else "?"
        done_mark = "✓ 已完成" if t.done else "○ 待办"
        body_preview = (t.body or "")[:50].replace("\n", " ")
        mold = t.mold_number or "-"
        dd = t.due_date.strftime("%Y-%m-%d") if t.due_date else "-"
        ts = (t.timestamp.isoformat() if t.timestamp else "")[:19]
        lines.append(f"{t.id} | {body_preview} | {done_mark} | {mold} | {dd} | {author_name} | {ts}")

    count = len(todos)
    _log("SELECT", f"查询到 {count} 条待办", success=True)
    return "\n".join(lines)


def _add_todo(body: str, mold_number: str = "", author_id: int = None, due_date=None) -> str:
    """创建待办事项。"""
    if not body or not body.strip():
        raise ValueError("待办内容不能为空")

    from app.extensions.init_sqlalchemy import db
    from app.models.todo import Todo
    from app.utils.time_utils import beijing_now

    todo = Todo(
        body=body.strip(),
        mold_number=mold_number.strip() if mold_number else None,
        author_id=author_id,
        done=False,
        due_date=due_date,
        timestamp=beijing_now(),
    )
    db.session.add(todo)
    db.session.commit()

    _log("INSERT", f"创建待办: {body[:50]}", todo_id=todo.id, success=True)
    due_str = due_date.isoformat() if due_date else None
    return json.dumps({
        "success": True,
        "operation": "INSERT",
        "todo_id": todo.id,
        "body": body,
        "mold_number": mold_number or None,
        "due_date": due_str,
    }, ensure_ascii=False)


def _update_todo(todo_id: int, body: str = None, done: bool = None,
                 mold_number: str = None, due_date=None,
                 user_id: int = None, is_admin: bool = False) -> str:
    """更新待办事项。"""
    from app.extensions.init_sqlalchemy import db
    from app.models.todo import Todo

    todo = db.session.get(Todo, todo_id)
    if not todo:
        raise ValueError(f"待办事项不存在: ID={todo_id}")

    # 权限检查：非管理员只能更新自己的待办
    if not is_admin and todo.author_id != user_id:
        raise ValueError("权限不足：你只能修改自己的待办事项。")

    changes = []
    if body is not None:
        todo.body = body.strip()
        changes.append("body")
    if done is not None:
        todo.done = bool(done)
        changes.append(f"done={bool(done)}")
    if mold_number is not None:
        todo.mold_number = mold_number.strip() if mold_number.strip() else None
        changes.append("mold_number")
    if due_date is not None:
        todo.due_date = due_date
        changes.append("due_date")

    if not changes:
        return json.dumps({"success": True, "message": "无需更新"}, ensure_ascii=False)

    db.session.commit()
    _log("UPDATE", f"更新字段: {', '.join(changes)}", todo_id=todo_id, success=True)
    return json.dumps({
        "success": True,
        "operation": "UPDATE",
        "todo_id": todo_id,
        "updated_fields": changes,
    }, ensure_ascii=False)


def _delete_todo(todo_id: int, user_id: int = None, is_admin: bool = False) -> str:
    """删除待办事项。"""
    from app.extensions.init_sqlalchemy import db
    from app.models.todo import Todo

    todo = db.session.get(Todo, todo_id)
    if not todo:
        raise ValueError(f"待办事项不存在: ID={todo_id}")

    # 权限检查：非管理员只能删除自己的待办
    if not is_admin and todo.author_id != user_id:
        raise ValueError("权限不足：你只能删除自己的待办事项。")

    body_preview = (todo.body or "")[:50]
    db.session.delete(todo)
    db.session.commit()

    _log("DELETE", f"删除待办: {body_preview}", todo_id=todo_id, success=True)
    return json.dumps({
        "success": True,
        "operation": "DELETE",
        "todo_id": todo_id,
    }, ensure_ascii=False)


# ── 入口 ────────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """待办事项管理入口。

    Actions:
      list     — 查询待办事项列表
      add      — 创建新的待办事项
      update   — 更新待办事项
      delete   — 删除待办事项

    Args:
        action:      操作类型（list / add / update / delete）
        expression:  可选的 JSON 字符串，包含所有参数
        body:        待办内容（add 必需，update 可选）
        todo_id:     待办 ID（update/delete 必需）
        done:        完成状态（list 筛选用：true/false；update 设值用）
        mold_number: 分类编号（可选）
        due_date:    截止日期，格式 YYYY-MM-DD（可选，add/update 用）
        author_id:   创建者用户 ID（可选，默认不限制）
        keyword:     关键词搜索（list 用）
        limit:       最大返回行数（list 用，默认 50）

    Returns:
        JSON 字符串或格式化文本
    """
    # ── 解析参数 ──────────────────────────────────────────────────
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = params.get("action") or action or ""
    body = params.get("body") or kwargs.get("body", "")
    mold_number = params.get("mold_number") or kwargs.get("mold_number", "")
    todo_id = params.get("todo_id") or kwargs.get("todo_id")
    due_date = params.get("due_date") or kwargs.get("due_date", "")
    # 转换 due_date 字符串为 date 对象
    dd_val = None
    if due_date:
        try:
            dd_val = datetime.datetime.strptime(str(due_date)[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    done = params.get("done") or kwargs.get("done")
    author_id = params.get("author_id") or kwargs.get("author_id")
    keyword = params.get("keyword") or kwargs.get("keyword", "")
    try:
        limit = int(params.get("limit") or kwargs.get("limit", 50))
    except (ValueError, TypeError):
        limit = 50

    # ── 确保 Flask 上下文 + 获取当前用户 ─────────────────────────
    ctx = _ensure_app_context()
    try:
        # 支持从 kwargs 传入用户上下文（线程池并行调用时使用）
        _uid_from_kw = kwargs.get("_user_id")
        _admin_from_kw = kwargs.get("_is_admin", False)
        user_info = _get_current_user_info(_user_id=_uid_from_kw, _is_admin=_admin_from_kw)
        uid = user_info["id"]
        is_admin = user_info["is_admin"]

        if action == "list" or action == "query":
            # 普通用户只能看自己的；管理员可指定 author_id 或看全部
            effective_uid = uid if not is_admin else (author_id or None)
            return _list_todos(
                user_id=effective_uid,
                done=done,
                keyword=keyword,
                limit=limit,
            )

        if action == "add" or action == "create":
            if not body:
                return json.dumps({
                    "success": False,
                    "error": "缺少必需参数: body（待办内容）",
                }, ensure_ascii=False)
            # 始终用当前登录用户作为作者
            return _add_todo(body, mold_number=mold_number, author_id=uid, due_date=dd_val)

        if action == "update" or action == "edit":
            if todo_id is None:
                return json.dumps({
                    "success": False,
                    "error": "缺少必需参数: todo_id（待办 ID）",
                }, ensure_ascii=False)
            try:
                tid = int(todo_id)
            except (ValueError, TypeError):
                return json.dumps({
                    "success": False,
                    "error": f"无效的 todo_id: {todo_id}",
                }, ensure_ascii=False)

            # done 参数支持多种格式
            done_val = None
            if done is not None:
                if isinstance(done, bool):
                    done_val = done
                elif isinstance(done, str):
                    done_val = done.lower() in ("1", "true", "yes", "是")
                elif isinstance(done, (int, float)):
                    done_val = bool(done)

            return _update_todo(
                tid,
                body=body if body else None,
                done=done_val,
                mold_number=mold_number if mold_number else None,
                due_date=dd_val,
                user_id=uid,
                is_admin=is_admin,
            )

        if action == "delete" or action == "remove":
            if todo_id is None:
                return json.dumps({
                    "success": False,
                    "error": "缺少必需参数: todo_id（待办 ID）",
                }, ensure_ascii=False)
            try:
                tid = int(todo_id)
            except (ValueError, TypeError):
                return json.dumps({
                    "success": False,
                    "error": f"无效的 todo_id: {todo_id}",
                }, ensure_ascii=False)
            return _delete_todo(tid, user_id=uid, is_admin=is_admin)

        # 默认返回帮助
        return (
            "待办事项管理工具 (todo_manager)\n"
            "用法: run(action='操作类型', ...)\n\n"
            "支持的操作:\n"
            "  list      — 查询待办事项列表\n"
            "             可选: done(1/0), keyword, limit\n"
            "             普通用户只能看到自己的待办\n"
            "  add       — 创建待办事项（需 body，可选 mold_number/due_date）\n"
            "             author_id 自动设为当前登录用户\n"
            "  update    — 更新待办事项（需 todo_id，可选 body/done/mold_number/due_date）\n"
            "  delete    — 删除待办事项（需 todo_id）\n\n"
            "权限说明:\n"
            "  普通用户：只能查看/修改/删除自己的待办\n"
            "  管理员：可查看/修改/删除所有用户的待办\n\n"
            "示例:\n"
            "  run(action='add', body='买牛奶', mold_number='shopping', due_date='2026-06-01')\n"
            "  run(action='list', done='0', limit=20)\n"
            "  run(action='update', todo_id=1, done='1')\n"
            "  run(action='delete', todo_id=1)"
        )

    except ValueError as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        _logger.error(f"[{_ACTION_DESCRIPTION}] ✗ 错误: {e}")
        return json.dumps({"success": False, "error": f"操作失败: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)


# ── 动作别名 ────────────────────────────────────────────────────────────
add = lambda expression="", **kwargs: run(action="add", expression=expression, **kwargs)
create = lambda expression="", **kwargs: run(action="add", expression=expression, **kwargs)
list_todos = lambda expression="", **kwargs: run(action="list", expression=expression, **kwargs)
update = lambda expression="", **kwargs: run(action="update", expression=expression, **kwargs)
edit = lambda expression="", **kwargs: run(action="update", expression=expression, **kwargs)
delete = lambda expression="", **kwargs: run(action="delete", expression=expression, **kwargs)
remove = lambda expression="", **kwargs: run(action="delete", expression=expression, **kwargs)
