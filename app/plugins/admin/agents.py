from flask import render_template, redirect, url_for, flash, request, jsonify
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.models.agent_config import AgentConfig
from app.models.llm_model import LLMModel
from app.models.mcp_tool import MCPTool
from app.models.api_endpoint import APIEndpoint
from app.models.skill import Skill
from app.models.knowledge_base import KnowledgeBase
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int
from app.utils.llm_utils import call_llm_chat, resolve_api_key



@bp.route("/agents/generate-prompt", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def agent_generate_prompt():
    """Use an LLM to generate a system prompt based on agent name and description."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    try:
        model_id = int(data.get("model_id")) if data.get("model_id") else None
    except (ValueError, TypeError):
        model_id = None

    if not name:
        return jsonify({"success": False, "error": "请填写智能体名称"})
    if not model_id:
        return jsonify({"success": False, "error": "请选择用于生成的 LLM 模型"})

    model = LLMModel.query.get(model_id)
    if not model or not model.is_active:
        return jsonify({"success": False, "error": "模型不存在或已禁用"})

    api_key = resolve_api_key(model)
    if not api_key:
        return jsonify({"success": False, "error": "该模型未配置 API Key"})

    system_msg = (
        "你是一个专业的 AI 智能体系统提示词生成器。"
        "根据用户提供的智能体名称和描述，生成一份高质量的 system prompt。"
        "要求：1. 明确智能体的身份和角色 2. 指定行为准则和约束 "
        "3. 语言简洁、清晰、有条理 4. 使用中文输出 "
        "5. 只输出提示词正文，不要额外说明。"
    )
    user_msg = f"智能体名称：{name}\n智能体描述：{description or '无'}"

    try:
        prompt = call_llm_chat(
            api_key=api_key,
            model_id=model.model_id,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            api_base=model.api_base,
            max_tokens=1024,
            temperature=0.7,
            timeout=30,
        )
        if prompt:
            return jsonify({"success": True, "prompt": prompt})
        return jsonify({"success": False, "error": "LLM 调用返回空结果"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@bp.route("/agents/optimize-prompt", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def agent_optimize_prompt():
    """Use an LLM to optimize an existing system prompt."""
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    system_prompt = (data.get("system_prompt") or "").strip()
    try:
        model_id = int(data.get("model_id")) if data.get("model_id") else None
    except (ValueError, TypeError):
        model_id = None

    if not system_prompt:
        return jsonify({"success": False, "error": "请提供需要优化的系统提示词"})
    if not model_id:
        return jsonify({"success": False, "error": "请选择用于优化的 LLM 模型"})

    model = LLMModel.query.get(model_id)
    if not model or not model.is_active:
        return jsonify({"success": False, "error": "模型不存在或已禁用"})

    api_key = resolve_api_key(model)
    if not api_key:
        return jsonify({"success": False, "error": "该模型未配置 API Key"})

    system_msg = (
        "你是一个专业的 AI 智能体系统提示词优化专家。"
        "你的任务是对用户现有的 system prompt 进行优化和增强。\n\n"
        "要求：\n"
        "1. 保留原有提示词的核心意图和功能\n"
        "2. 优化表达，使其更清晰、简洁、有条理\n"
        "3. 补充可能缺失的关键要素（角色身份、行为准则、约束条件、输出格式等）\n"
        "4. 使用中文输出\n"
        "5. 只输出优化后的提示词正文，不要额外说明，不要用代码块包裹\n"
        "6. 如果提供了智能体名称和描述，可据此丰富提示词内容"
    )

    user_msg_parts = []
    if name:
        user_msg_parts.append(f"智能体名称：{name}")
    if description:
        user_msg_parts.append(f"智能体描述：{description}")
    user_msg_parts.append(f"\n现有的系统提示词：\n{system_prompt}")
    user_msg_parts.append("\n请对以上系统提示词进行优化，输出优化后的版本：")
    user_msg = "\n".join(user_msg_parts)

    try:
        prompt = call_llm_chat(
            api_key=api_key,
            model_id=model.model_id,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            api_base=model.api_base,
            max_tokens=2048,
            temperature=0.7,
            timeout=60,
        )
        if prompt:
            return jsonify({"success": True, "prompt": prompt})
        return jsonify({"success": False, "error": "LLM 调用返回空结果"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============ Agent Management ============

@bp.route("/agents")
@admin_required
@require_plugin(blueprint_name)
def agents():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    pagination = AgentConfig.query.order_by(AgentConfig.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    agents = pagination.items
    models = LLMModel.query.filter_by(is_active=True, model_type="text").all()
    mcp_tools = MCPTool.query.filter_by(is_active=True).all()
    api_endpoints = APIEndpoint.query.filter_by(is_active=True).all()
    skills = Skill.query.filter_by(is_active=True).all()
    knowledge_bases = KnowledgeBase.query.filter_by(is_active=True).all()
    return render_template(
        "admin/agents.html",
        agents=agents,
        pagination=pagination,
        models=models,
        mcp_tools=mcp_tools,
        api_endpoints=api_endpoints,
        skills=skills,
        knowledge_bases=knowledge_bases,
    )


@bp.route("/agents/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def agent_add():
    data = request.form
    agent = AgentConfig(
        name=data.get("name"),
        description=data.get("description"),
        system_prompt=data.get("system_prompt"),
        is_active=data.get("is_active") == "true",
        allowed_roles=data.get("allowed_roles", "all"),
        default_model_id=data.get("default_model_id", type=int) or None,
        max_iterations=data.get("max_iterations", 10, type=int),
        temperature=data.get("temperature", 0.7, type=float),
        enable_sandbox=data.get("enable_sandbox") == "true",
        enable_file_upload=data.get("enable_file_upload") == "true",
        enable_web_search=data.get("enable_web_search", "false") == "true",
    )
    db.session.add(agent)

    # Associate MCP tools
    mcp_ids = request.form.getlist("mcp_tool_ids")
    if mcp_ids:
        for mid in mcp_ids:
            tool = MCPTool.query.get(int(mid))
            if tool:
                agent.mcp_tools.append(tool)

    # Associate API endpoints
    api_ids = request.form.getlist("api_endpoint_ids")
    if api_ids:
        for aid in api_ids:
            ep = APIEndpoint.query.get(int(aid))
            if ep:
                agent.api_endpoints.append(ep)

    # Associate skills
    skill_ids = request.form.getlist("skill_ids")
    if skill_ids:
        for sid in skill_ids:
            skill = Skill.query.get(int(sid))
            if skill:
                agent.skills.append(skill)

    # Associate knowledge bases
    kb_ids = request.form.getlist("knowledge_base_ids")
    if kb_ids:
        for kid in kb_ids:
            kb = KnowledgeBase.query.get(int(kid))
            if kb:
                agent.knowledge_bases.append(kb)

    db.session.commit()
    log_admin("\u667a\u80fd\u4f53\u5df2\u6dfb\u52a0 \u2014 name=%s", agent.name)
    flash("\u667a\u80fd\u4f53\u6dfb\u52a0\u6210\u529f\u3002", "success")
    return redirect(url_for("admin.agents"))


@bp.route("/agents/<int:agent_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def agent_edit(agent_id):
    agent = AgentConfig.query.get_or_404(agent_id)
    data = request.form

    agent.name = data.get("name", agent.name)
    agent.description = data.get("description", agent.description)
    agent.system_prompt = data.get("system_prompt", agent.system_prompt)
    agent.is_active = data.get("is_active") == "true"
    agent.allowed_roles = data.get("allowed_roles", agent.allowed_roles)
    agent.default_model_id = data.get("default_model_id", type=int) or None
    agent.max_iterations = data.get("max_iterations", agent.max_iterations, type=int)
    agent.temperature = data.get("temperature", agent.temperature, type=float)
    agent.enable_sandbox = data.get("enable_sandbox") == "true"
    agent.enable_file_upload = data.get("enable_file_upload") == "true"
    agent.enable_web_search = data.get("enable_web_search", "false") == "true"

    # Update associations
    agent.mcp_tools = []
    mcp_ids = request.form.getlist("mcp_tool_ids")
    for mid in mcp_ids:
        tool = MCPTool.query.get(int(mid))
        if tool:
            agent.mcp_tools.append(tool)

    agent.api_endpoints = []
    api_ids = request.form.getlist("api_endpoint_ids")
    for aid in api_ids:
        ep = APIEndpoint.query.get(int(aid))
        if ep:
            agent.api_endpoints.append(ep)

    agent.skills = []
    skill_ids = request.form.getlist("skill_ids")
    for sid in skill_ids:
        skill = Skill.query.get(int(sid))
        if skill:
            agent.skills.append(skill)

    agent.knowledge_bases = []
    kb_ids = request.form.getlist("knowledge_base_ids")
    for kid in kb_ids:
        kb = KnowledgeBase.query.get(int(kid))
        if kb:
            agent.knowledge_bases.append(kb)

    db.session.commit()
    log_admin("\u667a\u80fd\u4f53\u5df2\u7f16\u8f91 \u2014 agent_id=%d, name=%s", agent.id, agent.name)
    flash("\u667a\u80fd\u4f53\u66f4\u65b0\u6210\u529f\u3002", "success")
    return redirect(url_for("admin.agents"))


@bp.route("/agents/<int:agent_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def agent_delete(agent_id):
    agent = AgentConfig.query.get_or_404(agent_id)
    log_admin("\u667a\u80fd\u4f53\u5df2\u5220\u9664 \u2014 agent_id=%d", agent_id)
    db.session.delete(agent)
    db.session.commit()
    flash("\u667a\u80fd\u4f53\u5df2\u5220\u9664\u3002", "success")
    return redirect(url_for("admin.agents"))
