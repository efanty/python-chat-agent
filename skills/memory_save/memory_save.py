"""memory_save Skill — 保存用户记忆（偏好、事实、习惯等）。

智能体在对话中发现用户的个人信息、偏好、习惯等时，
使用此工具将这些信息保存为长期记忆。
"""

import json

from app.utils.time_utils import beijing_now


# ── Flask app context 辅助（移植自 todo_manager，线程安全） ────────────

def _ensure_app_context():
    """确保 Flask app 上下文存在。
    
    已在 app context 中时返回 None（无需清理）；
    在 ThreadPool 线程中时创建并 push 一个新的 app context。
    """
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
    except Exception:
        raise RuntimeError(
            "无法创建 Flask 应用上下文，请在项目完整环境下使用此 Skill。"
        )


def _cleanup_context(ctx):
    """弹出手动创建的 app context。"""
    if ctx is not None:
        ctx.pop()


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """保存一条用户记忆。

    用于在对话过程中记录用户的偏好、事实、习惯等信息，以便后续对话中调用。

    Args:
        expression: JSON 字符串或纯文本
        action:     "save"（默认）
        **kwargs:
            key:    记忆标识，如 "preferred_language", "hobby_reading"
            value:  记忆内容，如 "喜欢阅读科幻小说"
            type:   记忆类型: general（通用）, preference（偏好）, fact（事实）, context（上下文）
            user_id: 用户 ID（系统自动传入）

    Returns:
        JSON: {"success": true, "key": "...", "action": "saved/updated"}
    """
    # 解析参数
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    key = params.get("key") or kwargs.get("key", "").strip()
    value = params.get("value") or kwargs.get("value", "") or expression or ""
    mem_type = params.get("type") or kwargs.get("type", "general")
    user_id = kwargs.get("user_id") or params.get("user_id")

    if not key:
        return json.dumps({
            "success": False,
            "error": "缺少 key（记忆标识）",
            "usage": 'run(key="hobby_reading", value="喜欢科幻小说", type="preference")',
        }, ensure_ascii=False)

    if not value:
        return json.dumps({"success": False, "error": "缺少 value（记忆内容）"}, ensure_ascii=False)

    if not user_id:
        return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

    ctx = _ensure_app_context()
    try:
        from app.extensions.init_sqlalchemy import db
        from app.models.memory import UserMemory

        existing = UserMemory.query.filter_by(user_id=user_id, key=key).first()
        if existing:
            existing.value = value
            existing.memory_type = mem_type
            existing.updated_at = beijing_now()
            db.session.commit()
            action_msg = "updated"
        else:
            mem = UserMemory(
                user_id=user_id,
                key=key,
                value=value,
                memory_type=mem_type,
            )
            db.session.add(mem)
            db.session.commit()
            action_msg = "saved"

        return json.dumps({
            "success": True,
            "key": key,
            "type": mem_type,
            "action": action_msg,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"保存记忆失败: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)
