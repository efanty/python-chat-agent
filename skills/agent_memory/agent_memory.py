"""agent-memory Skill — 智能体记忆系统。

提供统一的记忆管理接口，实际上路由到已有的 memory_save / memory_query 工具。
"""

import json


# ── Flask app context 辅助（线程安全） ────────────────────────────────

def _ensure_app_context():
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
        raise RuntimeError("无法创建 Flask 应用上下文")

def _cleanup_context(ctx):
    if ctx is not None:
        ctx.pop()


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """智能体记忆管理 — 保存或查询记忆。

    Args:
        expression: 如果是 JSON 字符串，则从中解析 key/value/type
        action:
            "save"    — 保存记忆
            "query"   — 查询记忆
            "track"   — 追踪实体（自动构造 entity_ 前缀的 key）
            "learn"   — 记录经验（自动构造 lesson_ 前缀的 key）
        **kwargs:
            key, value, type, user_id — 保存参数
            或 key, type, query, user_id — 查询参数

    Returns:
        JSON 字符串
    """
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = action or params.get("action") or kwargs.get("action", "save")
    user_id = kwargs.get("user_id") or params.get("user_id")

    if not user_id:
        return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

    ctx = _ensure_app_context()
    try:
        from app.extensions.init_sqlalchemy import db
        from app.models.memory import UserMemory
        from app.utils.time_utils import beijing_now

        def _save(key, value, mem_type="general"):
            existing = UserMemory.query.filter_by(user_id=user_id, key=key).first()
            if existing:
                existing.value = value
                existing.memory_type = mem_type
                existing.updated_at = beijing_now()
                db.session.commit()
                return {"success": True, "key": key, "type": mem_type, "action": "updated"}
            mem = UserMemory(user_id=user_id, key=key, value=value, memory_type=mem_type)
            db.session.add(mem)
            db.session.commit()
            return {"success": True, "key": key, "type": mem_type, "action": "saved"}

        def _query(key="", mem_type="", search=""):
            q = UserMemory.query.filter_by(user_id=user_id)
            if key:
                q = q.filter(UserMemory.key == key)
            if mem_type:
                q = q.filter(UserMemory.memory_type == mem_type)
            memories = q.order_by(UserMemory.updated_at.desc()).all()
            if search:
                memories = [m for m in memories
                            if search.lower() in (m.value or "").lower()
                            or search.lower() in m.key.lower()]
            results = [{"key": m.key, "value": m.value, "type": m.memory_type,
                        "updated": m.updated_at.strftime("%Y-%m-%d %H:%M") if m.updated_at else ""}
                       for m in memories]
            return {"success": True, "memories": results, "count": len(results)}

        if action == "save" or action == "run":
            key = params.get("key") or kwargs.get("key", "").strip()
            value = params.get("value") or kwargs.get("value", "") or expression or ""
            mem_type = params.get("type") or kwargs.get("type", "general")
            if not key:
                return json.dumps({"success": False, "error": "缺少 key"}, ensure_ascii=False)
            return json.dumps(_save(key, value, mem_type), ensure_ascii=False)

        elif action == "track":
            entity_name = params.get("entity") or kwargs.get("entity", "").strip()
            entity_type = params.get("entity_type") or kwargs.get("entity_type", "person")
            entity_info = params.get("info") or kwargs.get("info", "")
            if not entity_name:
                return json.dumps({"success": False, "error": "缺少 entity 名称"}, ensure_ascii=False)
            key = f"entity_{entity_type}_{entity_name.lower().replace(' ', '_')}"
            return json.dumps(_save(key, str(entity_info), "context"), ensure_ascii=False)

        elif action == "learn":
            topic = params.get("topic") or kwargs.get("topic", "").strip()
            lesson = params.get("lesson") or kwargs.get("lesson", "") or expression or ""
            if not topic or not lesson:
                return json.dumps({"success": False, "error": "缺少 topic 或 lesson"}, ensure_ascii=False)
            key = f"lesson_{topic.lower().replace(' ', '_')}"
            return json.dumps(_save(key, lesson, "fact"), ensure_ascii=False)

        elif action in ("query", "list"):
            q_key = params.get("key") or kwargs.get("key", "")
            q_type = params.get("type") or kwargs.get("type", "")
            search = params.get("query") or kwargs.get("query", "")
            return json.dumps(_query(q_key, q_type, search), ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"未知 action: {action}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"memory error: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)
