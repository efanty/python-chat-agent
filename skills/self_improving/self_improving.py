"""self_improving Skill — 在对话历史中反思学习并保存经验教训。"""

import json
import re


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
    """在对话历史中反思学习并保存经验教训。

    智能体在以下情况下调用此工具：
    - 在解决复杂问题后反思
    - 发现用户重复出现的需求模式
    - 学到了新的技能或知识
    - 需要记录最佳实践

    Args:
        expression: JSON 字符串，或纯文本内容
        action:
            "learn"    — 保存经验教训
            "reflect"  — 反思当前对话
            "list"     — 列出已保存的经验教训
        **kwargs:
            topic:         主题（learn/reflect 用）
            lesson:        经验教训内容（learn 用）
            user_id:       用户 ID（系统自动传入）

    Returns:
        JSON 字符串
    """
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = action or params.get("action") or kwargs.get("action", "learn")
    user_id = kwargs.get("user_id") or params.get("user_id")

    if not user_id:
        return json.dumps({"success": False, "error": "缺少 user_id"}, ensure_ascii=False)

    ctx = _ensure_app_context()
    try:
        from app.extensions.init_sqlalchemy import db
        from app.models.memory import UserMemory
        from app.utils.time_utils import beijing_now

        def _save_lesson(topic, lesson):
            key = f"self_improving_{topic.lower().replace(' ', '_')}"
            key = re.sub(r'[^a-zA-Z0-9_\-\u4e00-\u9fff]', '', key)

            existing = UserMemory.query.filter_by(user_id=user_id, key=key).first()
            if existing:
                existing.value = lesson
                existing.updated_at = beijing_now()
                db.session.commit()
                return {"success": True, "key": key, "action": "updated"}
            mem = UserMemory(user_id=user_id, key=key, value=lesson, memory_type="fact")
            db.session.add(mem)
            db.session.commit()
            return {"success": True, "key": key, "action": "saved"}

        if action == "learn":
            topic = params.get("topic") or kwargs.get("topic", "").strip()
            lesson = params.get("lesson") or kwargs.get("lesson", "") or expression or ""
            if not topic:
                return json.dumps({"success": False, "error": "缺少 topic"}, ensure_ascii=False)
            if not lesson:
                return json.dumps({"success": False, "error": "缺少 lesson"}, ensure_ascii=False)
            return json.dumps(_save_lesson(topic, lesson), ensure_ascii=False)

        elif action == "reflect":
            topic = params.get("topic") or kwargs.get("topic", "general_reflection")
            lesson = params.get("lesson") or kwargs.get("lesson", "") or expression or ""
            if not lesson:
                return json.dumps({"success": False, "error": "缺少 lesson 反思内容"}, ensure_ascii=False)
            return json.dumps(_save_lesson(topic, lesson), ensure_ascii=False)

        elif action == "list":
            memories = UserMemory.query.filter(
                UserMemory.user_id == user_id,
                UserMemory.key.like("self_improving_%"),
            ).order_by(UserMemory.updated_at.desc()).all()
            results = [{"key": m.key, "value": m.value, "updated": m.updated_at.strftime("%Y-%m-%d %H:%M") if m.updated_at else ""} for m in memories]
            return json.dumps({"success": True, "lessons": results, "count": len(results)}, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"未知 action: {action}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"self-improving error: {e}"}, ensure_ascii=False)
    finally:
        _cleanup_context(ctx)
