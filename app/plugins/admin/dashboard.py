from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.models.user import User
from app.models.agent_config import AgentConfig
from app.models.llm_model import LLMModel
from app.models.mcp_tool import MCPTool
from app.models.api_endpoint import APIEndpoint
from app.models.skill import Skill
from app.models.knowledge_base import KnowledgeBase
from app.models.conversation import Conversation, Message
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.utils.time_utils import beijing_now
from sqlalchemy import func
from app.utils.plugin_utils import require_plugin


# ============ Dashboard ============

@bp.route("/")
@admin_required
@require_plugin(blueprint_name)
def dashboard():
    stats = {
        "user_count": User.query.count(),
        "agent_count": AgentConfig.query.count(),
        "model_count": LLMModel.query.count(),
        "mcp_count": MCPTool.query.count(),
        "api_count": APIEndpoint.query.count(),
        "skill_count": Skill.query.count(),
        "kb_count": KnowledgeBase.query.count(),
        "conversation_count": Conversation.query.count(),
        "message_count": Message.query.count(),
    }
    # Token stats (graceful if columns don't exist yet — old DB)
    try:
        token_stats = db.session.query(
            func.coalesce(func.sum(Message.input_tokens), 0),
            func.coalesce(func.sum(Message.output_tokens), 0),
            func.coalesce(func.sum(Message.token_count), 0),
            func.coalesce(func.sum(Message.cost), 0.0),
        ).first()
        stats["total_input_tokens"] = token_stats[0]
        stats["total_output_tokens"] = token_stats[1]
        stats["total_tokens"] = token_stats[2]
        stats["total_cost"] = round(float(token_stats[3]), 4)
    except Exception:
        stats["total_input_tokens"] = 0
        stats["total_output_tokens"] = 0
        stats["total_tokens"] = 0
        stats["total_cost"] = 0.0
    return render_template("admin/dashboard.html", stats=stats)

