"""
Unified search endpoint for admin modules.
Route: /admin/search/<module>?q=<query>
Returns JSON with matching results.
"""
from flask import request, jsonify
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.extensions.init_loginmanager import admin_required
from app.utils.plugin_utils import require_plugin
from app.models.skill import Skill
from app.models.llm_model import LLMModel
from app.models.agent_config import AgentConfig
from app.models.mcp_tool import MCPTool
from app.models.api_endpoint import APIEndpoint
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.models.memory import UserMemory


def _search_model(model_cls, search_cols, q, result_map, limit=50):
    """Generic search helper.

    Args:
        model_cls: SQLAlchemy model class.
        search_cols: list of column names to filter on (will be OR'd).
        q: search query string.
        result_map: callable(model) -> dict to shape the result.
        limit: max results.
    """
    if not q or not q.strip():
        return []

    q_clean = q.strip()
    filters = []
    for col_name in search_cols:
        col = getattr(model_cls, col_name, None)
        if col is not None:
            filters.append(col.ilike(f"%{q_clean}%"))

    if not filters:
        return []

    query = model_cls.query.filter(db.or_(*filters))
    query = query.order_by(model_cls.id.desc()).limit(limit)
    return [result_map(m) for m in query.all()]


EDIT_ID_MAP = {
    "skills": "#editSkillModal",
    "models": "#editModelModal",
    "agents": "#editAgentModal",
    "mcp-tools": "#editMcpModal",
    "api-endpoints": "#editApiModal",
    "knowledge-bases": "#editKbModal",
}


@bp.route("/search/<module>")
@admin_required
@require_plugin(blueprint_name)
def admin_search(module):
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"success": False, "error": "请输入搜索关键词", "results": []})

    results = []
    module = module.lower()
    edit_prefix = EDIT_ID_MAP.get(module)

    def with_edit(r):
        if edit_prefix:
            r["editModalId"] = edit_prefix + str(r["id"])
        return r

    if module == "skills":
        results = _search_model(
            Skill, ["name", "description", "folder_name"], q,
            lambda s: with_edit({
                "id": s.id,
                "name": s.name,
                "description": s.description or "",
                "badge": s.folder_name or "",
                "active": s.is_active,
            })
        )

    elif module == "models":
        results = _search_model(
            LLMModel, ["name", "provider", "model_type", "model_id", "description"], q,
            lambda m: with_edit({
                "id": m.id,
                "name": m.name,
                "description": f"{m.provider} / {m.model_id}",
                "badge": m.model_type or "",
                "active": m.is_active,
            })
        )

    elif module == "agents":
        results = _search_model(
            AgentConfig, ["name", "description", "system_prompt"], q,
            lambda a: with_edit({
                "id": a.id,
                "name": a.name,
                "description": (a.description or "")[:80],
                "badge": f"默认模型: {a.default_model.name if a.default_model else '无'}",
                "active": a.is_active,
            })
        )

    elif module == "mcp-tools":
        results = _search_model(
            MCPTool, ["name", "description"], q,
            lambda t: with_edit({
                "id": t.id,
                "name": t.name,
                "description": (t.description or "")[:80],
                "badge": t.tool_type or "",
                "active": t.is_active,
            })
        )

    elif module == "api-endpoints":
        results = _search_model(
            APIEndpoint, ["name", "description", "url"], q,
            lambda e: with_edit({
                "id": e.id,
                "name": e.name,
                "description": (e.description or "")[:60],
                "badge": f"{e.method} {e.url[:40]}" if e.url else e.method,
                "active": e.is_active,
            })
        )

    elif module == "knowledge-bases":
        results = _search_model(
            KnowledgeBase, ["name", "description", "collection_name"], q,
            lambda k: with_edit({
                "id": k.id,
                "name": k.name,
                "description": (k.description or "")[:60],
                "badge": k.collection_name or "",
                "active": k.is_active,
            })
        )

    elif module == "users":
        results = _search_model(
            User, ["username", "email"], q,
            lambda u: {
                "id": u.id,
                "name": u.username,
                "description": u.email or "",
                "badge": u.role or "",
                "active": u.is_active,
            }
        )

    elif module == "memories":
        results = _search_model(
            UserMemory, ["key", "value", "memory_type"], q,
            lambda m: {
                "id": m.id,
                "name": m.key[:50] if m.key else "",
                "description": (m.value or "")[:80],
                "badge": m.memory_type or "",
                "active": True,
            }
        )

    else:
        return jsonify({"success": False, "error": f"未知模块: {module}", "results": []})

    return jsonify({"success": True, "results": results, "total": len(results)})
