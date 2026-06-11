"""memory_query Skill — 查询用户的长期记忆。

返回当前用户的偏好、事实、习惯等已保存的记忆。
"""

import json


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
    """查询用户的长期记忆。

    Args:
        expression: 可选，按关键词筛选记忆
        action:     "list"（列出所有）或 "query"（按关键词搜索）
        **kwargs:
            key:  按 key 精确查询（可选）
            type: 按类型筛选: general / preference / fact / context
            user_id: 用户 ID（系统自动传入）

    Returns:
        JSON: {"success": true, "memories": [...], "count": N}
    """
    user_id = kwargs.get("user_id")
    q_key = kwargs.get("key", "").strip()
    q_type = kwargs.get("type", "").strip()
    search = expression.strip() or kwargs.get("query", "")

    if not user_id:
        return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

    ctx = _ensure_app_context()
    try:
        from app.extensions.init_sqlalchemy import db
        from app.models.memory import UserMemory

        query = UserMemory.query.filter_by(user_id=user_id)

        if q_key:
            query = query.filter(UserMemory.key == q_key)
        if q_type:
            query = query.filter(UserMemory.memory_type == q_type)

        memories = query.order_by(UserMemory.updated_at.desc()).all()

        # 关键词搜索（在 value 中匹配）
        if search:
            memories = [m for m in memories if search.lower() in (m.value or "").lower() or search.lower() in m.key.lower()]

        results = [
            {
                "key": m.key,
                "value": m.value,
                "type": m.memory_type,
                "updated": m.updated_at.strftime("%Y-%m-%d") if m.updated_at else "",
            }
            for m in memories
        ]

        return json.dumps({
            "success": True,
            "memories": results,
            "count": len(results),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"查询记忆失败: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)
