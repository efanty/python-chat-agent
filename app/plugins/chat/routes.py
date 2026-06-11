import json
import os
import uuid
from collections import OrderedDict
from app.utils.time_utils import beijing_now
from pathlib import Path
from flask import render_template, request, jsonify, current_app, send_from_directory, Response, stream_with_context, redirect, abort, url_for
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.models.user import User
from app.models.agent_config import AgentConfig
from app.models.llm_model import LLMModel
from app.models.conversation import Conversation, Message
from app.logger import log_action, log_error
from app.extensions.init_csrf import csrf_protect
from app.utils.settings import get_setting_int, get_setting
from app.utils.llm_utils import resolve_api_key, call_llm_chat
from sqlalchemy.orm import joinedload
from app.utils.plugin_utils import require_plugin
from app.services.agent_service import AgentService


# ── 文件格式白名单 ─────────────────────────────────────────────
def _get_allowed_extensions() -> set:
    """Read allowed extensions from admin settings; fallback to built-in list."""
    raw = get_setting("allowed_upload_extensions")
    if raw:
        return {e.strip().lower().lstrip(".") for e in raw.split(",") if e.strip()}
    # Default fallback
    return {
        "txt", "pdf", "png", "jpg", "jpeg", "gif", "webp",
        "csv", "json", "xml", "yaml", "yml",
        "py", "js", "ts", "html", "css", "md", "sql", "sh",
        "xlsx", "xlsm", "docx", "pptx",
    }

# 扩展名 → 期望的 MIME 类型（python-magic 检测用）
EXPECTED_MIME = {
    ".txt":  ("text/plain",),
    ".pdf":  ("application/pdf",),
    ".png":  ("image/png",),
    ".jpg":  ("image/jpeg",),
    ".jpeg": ("image/jpeg",),
    ".gif":  ("image/gif",),
    ".webp": ("image/webp",),
    ".csv":  ("text/csv", "text/plain"),
    ".json": ("application/json", "text/plain"),
    ".xml":  ("text/xml", "application/xml", "text/plain"),
    ".yaml": ("text/yaml", "text/plain"),
    ".yml":  ("text/yaml", "text/plain"),
    ".py":   ("text/x-python", "text/plain"),
    ".js":   ("text/javascript", "text/plain"),
    ".ts":   ("text/typescript", "text/plain"),
    ".html": ("text/html", "text/plain"),
    ".css":  ("text/css", "text/plain"),
    ".md":   ("text/markdown", "text/plain"),
    ".sql":  ("text/plain",),
    ".sh":   ("text/x-shellscript", "text/plain"),
    ".xlsx":  ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip"),
    ".xlsm":  ("application/vnd.ms-excel.sheet.macroEnabled.12", "application/zip"),
    ".docx":  ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"),
    ".pptx":  ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "application/zip"),
}


def _make_conv_title(content: str) -> str:
    """Generate a concise conversation title from user's first input."""
    if not content:
        return "新对话"
    text = content.strip()
    # Strip common file attachment prefixes
    prefixes = ("📎", "📷", "📄", "[file]", "附件:", "文件:")
    for p in prefixes:
        if text.startswith(p):
            text = text[len(p):].strip()
    max_len = 25
    if len(text) <= max_len:
        return text
    # Try to cut at Chinese/English punctuation boundary
    for sep in "。！？，；：.!?,;:\n":
        idx = text.find(sep)
        if 6 <= idx < max_len:
            return text[:idx].strip()
    return text[:max_len].rstrip() + "…"


def _generate_title_with_llm(content: str, conv) -> str:
    """Use LLM to generate a concise conversation title from user input.
    Returns None on failure so caller can fall back to _make_conv_title."""
    if not content or not conv:
        return None

    # Collect candidate models: first try conversation's model, then any active text model
    candidate_models = []
    if conv.model and conv.model.is_active:
        candidate_models.append(conv.model)
    # Also add all other active text models as fallback candidates
    for m in LLMModel.query.filter(
        LLMModel.is_active == True,
        LLMModel.model_type.in_(["text"])
    ).all():
        if m not in candidate_models:
            candidate_models.append(m)

    if not candidate_models:
        return None

    prompt = (
        "请为一段对话生成一个简洁的标题（不超过15个字），"
        "概括以下用户问题的核心主题。只返回标题本身，不要解释。\n\n"
        f"用户问题：{content}"
    )
    for model in candidate_models:
        api_key = resolve_api_key(model)
        if not api_key:
            continue
        try:
            title = call_llm_chat(
                api_key=api_key,
                model_id=model.model_id,
                messages=[{"role": "user", "content": prompt}],
                api_base=model.api_base,
                max_tokens=30,
                temperature=0.3,
                timeout=15,
            )
            if title:
                title = title.strip().strip('"\'「」『』【】')
                if len(title) > 30:
                    title = title[:28] + "…"
                return title
        except Exception:
            continue
    return None


def _prepare_agent_context(conv, current_user):
    """Extract agent/model/mcp/api context from a Conversation object.

    Returns a tuple of (user_info, model_info, agent_info, mcp_tools, api_endpoints, history).
    All data is extracted before entering a generator to avoid ORM access inside it.
    """
    _user_info = {
        "id": current_user.id, "username": current_user.username,
        "nickname": current_user.nickname,
        "role": current_user.role, "email": current_user.email,
        "email_verified": current_user.email_verified,
        "totp_enabled": current_user.totp_enabled,
        "created_at": current_user.created_at.strftime("%Y-%m-%d %H:%M") if current_user.created_at else "",
    }
    _model_info = None
    if conv.model:
        _model_info = {
            "model_id": conv.model.model_id, "provider": conv.model.provider,
            "api_key": conv.model.api_key, "api_base": conv.model.api_base,
            "max_tokens": conv.model.max_tokens, "is_active": conv.model.is_active,
            "input_price": conv.model.input_price or 0,
            "output_price": conv.model.output_price or 0,
        }
    _agent_info = {"system_prompt": None, "skill_names": [], "kb_collections": [],
                   "enable_sandbox": True}
    _mcp_tools = []
    _api_endpoints = []
    if conv.agent:
        _agent_info["system_prompt"] = conv.agent.system_prompt
        _agent_info["skill_names"] = [s.folder_name for s in conv.agent.skills if s.is_active]
        _agent_info["kb_collections"] = [kb.collection_name for kb in conv.agent.knowledge_bases if kb.is_active]
        _agent_info["enable_sandbox"] = conv.agent.enable_sandbox
        _mcp_tools = [{"id": t.id, "name": t.name, "description": t.description,
                       "command": t.command, "endpoint": t.endpoint,
                       "transport": t.transport or ("sse" if t.endpoint else "stdio"),
                       "args": t.args, "env_vars": t.env_vars}
                      for t in conv.agent.mcp_tools if t.is_active]
        _api_endpoints = [{"id": e.id, "name": e.name, "description": e.description,
                           "url": e.url, "method": e.method,
                           "headers": e.headers, "auth_type": e.auth_type,
                           "auth_value": e.auth_value}
                          for e in conv.agent.api_endpoints if e.is_active]
    _history = [{"role": m.role, "content": m.content or ""} for m in conv.messages.order_by("created_at").all()]
    return _user_info, _model_info, _agent_info, _mcp_tools, _api_endpoints, _history


def allowed_file(filename):
    exts = _get_allowed_extensions()
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def _validate_file_mime(filepath: str) -> bool:
    """使用 python-magic 校验文件的真实 MIME 类型是否与扩展名匹配。"""
    ext = Path(filepath).suffix.lower()
    if ext not in EXPECTED_MIME:
        # Extension is in the allowed list but has no MIME mapping — skip check
        return True
    try:
        import magic
        detected = magic.from_file(filepath, mime=True)
        return detected in EXPECTED_MIME[ext]
    except ImportError:
        # python-magic 未安装时跳过 MIME 校验（仅依赖扩展名）
        return True
    except Exception:
        return False


def _handle_file_upload(file_storage, user_id=None) -> tuple:
    """处理单个文件上传：校验扩展名 + MIME 类型，返回 (file_path, file_name) 或 (None, None)。

    如果提供了 user_id（来自聊天界面），文件将保存到 sandbox/<user_id>/ 目录下，
    以便智能体在沙箱环境中可以访问。否则保存到默认的 uploads 目录。
    """
    if not file_storage or not file_storage.filename:
        return None, None
    if not allowed_file(file_storage.filename):
        return None, None

    filename = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"

    if user_id:
        # 聊天界面上传 → 保存到沙箱目录下以用户ID为名的子文件夹，方便智能体访问
        sandbox_dir = current_app.config.get("SANDBOX_DIR", "sandbox")
        upload_dir = os.path.join(sandbox_dir, str(user_id))
    else:
        # 其它方式上传 → 保持原有行为，保存到 uploads 目录
        upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, unique_name)

    # 文件大小校验（后台可配）— 先校验再保存
    max_mb = get_setting_int("max_upload_size_mb", 16)
    max_bytes = max_mb * 1024 * 1024
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > max_bytes:
        return None, None

    file_storage.save(full_path)

    # MIME 类型二次校验（保存后检测 magic bytes）
    if not _validate_file_mime(full_path):
        os.remove(full_path)
        return None, None

    # 使用正斜杠路径，避免 JSON 字符串中的反斜杠转义问题
    return full_path.replace("\\", "/"), filename


def _handle_files_upload(file_storages, user_id=None) -> list:
    """处理多个文件上传，返回 [(file_path, file_name), ...] 列表。

    遍历所有上传的文件，逐个校验并保存。
    """
    results = []
    for f in file_storages:
        result = _handle_file_upload(f, user_id=user_id)
        if result[0] is not None:
            results.append(result)
    return results


@bp.route("/")
@login_required
@require_plugin(blueprint_name)
def index():
    """Main chat interface."""
    conversations = Conversation.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(Conversation.updated_at.desc()).all()

    # Get available agents for this user
    agents = AgentConfig.query.filter_by(is_active=True).all()
    agents = [a for a in agents if current_user.can_use_agent(a)]

    # Get available models for this user
    models = LLMModel.query.filter(LLMModel.is_active == True, LLMModel.model_type.in_(["text"])).all()
    models = [m for m in models if current_user.can_use_model(m)]

    current_conv_id = request.args.get("conversation_id", type=int)
    current_conv = None
    if current_conv_id:
        current_conv = Conversation.query.filter_by(
            id=current_conv_id, user_id=current_user.id
        ).first()

    return render_template(
        "chat/index.html",
        conversations=conversations,
        agents=agents,
        models=models,
        current_conv=current_conv,
    )


@bp.route("/conversation/new", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def new_conversation():
    """Create a new conversation."""
    data = request.get_json() or {}
    conv = Conversation(
        title=data.get("title", "新对话"),
        user_id=current_user.id,
        agent_id=data.get("agent_id"),
        model_id=data.get("model_id"),
    )
    db.session.add(conv)
    db.session.commit()
    log_action("对话已创建 — conv_id=%d", conv.id)
    return jsonify(conv.to_dict())


@bp.route("/conversation/<int:conv_id>")
@login_required
@require_plugin(blueprint_name)
def get_conversation(conv_id):
    """Get conversation details with messages."""
    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    messages = [m.to_dict() for m in conv.messages.all()]
    return jsonify({
        "conversation": conv.to_dict(),
        "messages": messages,
    })


@bp.route("/conversation/<int:conv_id>/delete", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def delete_conversation(conv_id):
    """Delete a conversation."""
    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    log_action("对话已删除 — conv_id=%d", conv_id)
    db.session.delete(conv)
    db.session.commit()
    return jsonify({"status": "ok"})


@bp.route("/conversation/<int:conv_id>/rename", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def rename_conversation(conv_id):
    """Rename a conversation."""
    conv = Conversation.query.filter_by(id=conv_id, user_id=current_user.id).first_or_404()
    data = request.get_json() or {}
    conv.title = data.get("title", conv.title)
    db.session.commit()
    log_action("对话已重命名 — conv_id=%d", conv_id)
    return jsonify({"status": "ok", "title": conv.title})


@bp.route("/conversation/search", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def search_conversations():
    """Search messages across the user's conversations."""
    data = request.get_json() or {}
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify({"results": [], "query": q})

    # Search messages by content (both user and assistant)
    messages = (
        Message.query
        .join(Conversation)
        .filter(
            Conversation.user_id == current_user.id,
            Conversation.is_active == True,
            Message.content.ilike(f"%{q}%"),
        )
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )

    # Group by conversation
    grouped = OrderedDict()
    for msg in messages:
        conv = msg.conversation
        if conv.id not in grouped:
            grouped[conv.id] = {
                "conversation": {
                    "id": conv.id,
                    "title": conv.title,
                    "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                },
                "matches": [],
            }
        grouped[conv.id]["matches"].append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content[:200] if msg.content else "",
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    return jsonify({"results": list(grouped.values()), "query": q})


@bp.route("/send", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def send_message():
    """Send a message and get AI response (deprecated — use /stream instead)."""
    return stream_message()


@bp.route("/stream", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def stream_message():
    """Stream AI response via Server-Sent Events."""
    data = request.form
    conv_id = data.get("conversation_id", type=int)
    content = data.get("content", "").strip()
    agent_id = data.get("agent_id", type=int)
    model_id = data.get("model_id", type=int)

    if not content and "file" not in request.files:
        return jsonify({"error": "消息内容不能为空"}), 400

    # ── 检查系统是否已配置 LLM 和智能体 ──────────────────────────
    has_models = LLMModel.query.filter(
        LLMModel.is_active == True,
        LLMModel.model_type.in_(["text"])
    ).count() > 0
    has_agents = AgentConfig.query.filter_by(is_active=True).count() > 0
    if not has_models or not has_agents:
        missing = []
        if not has_models:
            missing.append("LLM 模型")
        if not has_agents:
            missing.append("智能体")
        msg = f"系统尚未配置{'和'.join(missing)}，请先到<a href='{url_for('admin.dashboard')}' class='alert-link'>管理后台</a>添加后再开始对话。"
        return jsonify({"error": msg}), 400


    # Get or create conversation (eager-load relations for generator safety)
    if conv_id:
        conv = (Conversation.query
                .options(joinedload(Conversation.agent), joinedload(Conversation.model))
                .filter_by(id=conv_id, user_id=current_user.id)
                .first())
        if not conv:
            return jsonify({"error": "对话不存在"}), 404
    else:
        conv = Conversation(
            title="新对话",
            user_id=current_user.id,
            agent_id=agent_id,
            model_id=model_id,
        )
        db.session.add(conv)
        db.session.commit()

    if agent_id:
        conv.agent_id = agent_id
    if model_id:
        conv.model_id = model_id

    # Handle file upload — 聊天界面上传的文件保存到 sandbox/<user_id>/ 目录下
    file_path = None
    file_name = None
    file_paths = []  # 支持多个文件
    file_names = []
    if "file" in request.files:
        # 检查是否上传了多个文件（前端使用 multiple 属性）
        uploaded_files = request.files.getlist("file")
        if len(uploaded_files) > 1:
            # 多个文件
            file_results = _handle_files_upload(uploaded_files, user_id=current_user.id)
            file_paths = [r[0] for r in file_results]
            file_names = [r[1] for r in file_results]
            file_path = file_paths[0] if file_paths else None
            file_name = file_names[0] if file_names else None
        elif len(uploaded_files) == 1:
            # 单个文件（兼容旧行为）
            file_path, file_name = _handle_file_upload(uploaded_files[0], user_id=current_user.id)
            if file_path:
                file_paths = [file_path]
                file_names = [file_name]

    # 注意：不再自动继承历史消息中的文件路径。
    # 历史消息中的文件信息已包含在对话历史中，LLM 可以通过历史记录获取。
    # 如果用户需要继续处理之前的文件，LLM 可以从对话历史中找到文件路径。
    # 这样可以避免每次发送消息时都重新处理之前上传的文件。
    # Save user message
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=content,
        content_type="file" if file_path else "text",
        file_path=file_path,
        file_name=file_name,
    )
    db.session.add(user_msg)
    db.session.commit()

    # Update conversation title
    if not conv.title or conv.title == "新对话":
        if content:
            llm_title = _generate_title_with_llm(content, conv)
            conv.title = llm_title if llm_title else _make_conv_title(content)
    conv.updated_at = beijing_now()
    db.session.commit()

    agent_service = AgentService(current_app)

    # ── Extract ALL data before the generator (no ORM access inside) ───
    _conv_id = conv.id
    _conv_title = conv.title
    _user_info, _model_info, _agent_info, _mcp_tools, _api_endpoints, _history = _prepare_agent_context(conv, current_user)
    def generate():
        full_response = []
        _usage = {"input_tokens": 0, "output_tokens": 0}
        _model_id_str = ""
        _cost_val = 0.0
        try:
            for event in agent_service.chat_stream(
                user_info=_user_info,
                model_info=_model_info,
                agent_info=_agent_info,
                history=_history,
                message=content,
                file_path=file_path,
                file_paths=file_paths if file_paths else None,
                mcp_tools=_mcp_tools,
                api_endpoints=_api_endpoints,
            ):
                if event.get("type") == "chunk":
                    full_response.append(event["content"])
                    yield f"data: {json.dumps({'chunk': event['content'], 'conv_id': _conv_id, 'title': _conv_title})}\n\n"
                elif event.get("type") == "tool_call":
                    yield f"data: {json.dumps({'tool_call': event['name'], 'tool_args': event.get('args', {}), 'conv_id': _conv_id})}\n\n"
                elif event.get("type") == "tool_result":
                    yield f"data: {json.dumps({'tool_result': {'name': event['name'], 'result': event['result']}, 'conv_id': _conv_id})}\n\n"
                elif event.get("type") == "done":
                    _done_data = {"done": True, "conv_id": _conv_id, "title": _conv_title}
                    if event.get("usage"):
                        _usage = event["usage"]
                        _model_id_str = event.get("model_id", "")
                        _done_data["usage"] = _usage
                        _done_data["model_id"] = _model_id_str
                        # Calculate cost from model pricing (CNY per 1M tokens)
                        _cost_val = 0.0
                        if _model_info:
                            _in_price = _model_info.get("input_price", 0)
                            _out_price = _model_info.get("output_price", 0)
                            _cost_val = (_usage["input_tokens"] / 1_000_000) * _in_price + (_usage["output_tokens"] / 1_000_000) * _out_price
                            _done_data["cost"] = round(_cost_val, 6)
                    yield f"data: {json.dumps(_done_data)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Save assistant message with token usage
        response_text = "".join(full_response)
        conv_fresh = Conversation.query.get(_conv_id)
        total_tokens = _usage["input_tokens"] + _usage["output_tokens"]
        assistant_msg = Message(
            conversation_id=_conv_id,
            role="assistant",
            content=response_text,
            token_count=total_tokens,
            input_tokens=_usage["input_tokens"],
            output_tokens=_usage["output_tokens"],
            cost=_cost_val if _usage.get("input_tokens", 0) + _usage.get("output_tokens", 0) > 0 else 0.0,
            model_id_str=_model_id_str,
        )
        db.session.add(assistant_msg)
        if conv_fresh:
            conv_fresh.updated_at = beijing_now()
        db.session.commit()

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )



@bp.route("/user/settings", methods=["GET", "POST"])
@login_required
@require_plugin(blueprint_name)
def user_settings():
    """Update user chat preferences."""
    if request.method == "POST":
        data = request.get_json() or {}
        if "preferred_agent_id" in data:
            current_user.preferred_agent_id = data["preferred_agent_id"]
        if "preferred_model_id" in data:
            current_user.preferred_model_id = data["preferred_model_id"]
        db.session.commit()
        return jsonify({"status": "ok"})

    return jsonify({
        "preferred_agent_id": current_user.preferred_agent_id,
        "preferred_model_id": current_user.preferred_model_id,
    })




@bp.route("/uploads/<path:filename>")
@login_required
@require_plugin(blueprint_name)
def uploaded_file(filename):
    """Serve uploaded files with path traversal protection."""
    upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
    resolved = os.path.realpath(os.path.join(upload_dir, filename))
    if not resolved.startswith(os.path.realpath(upload_dir)):
        abort(403)
    response = send_from_directory(upload_dir, filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/sandbox/<path:filename>")
@login_required
@require_plugin(blueprint_name)
def sandbox_file(filename):
    """Serve agent-created sandbox files with user isolation and security.

    Security measures:
    - User isolation
    - Path traversal protection via os.path.realpath
    - Script files blocked
    - File size limit
    - Forces download
    """
    sandbox_dir = current_app.config.get("SANDBOX_DIR", "sandbox")
    user_dir = os.path.join(sandbox_dir, str(current_user.id))

    # Path traversal protection
    resolved_path = os.path.realpath(os.path.join(user_dir, filename))
    if not resolved_path.startswith(os.path.realpath(user_dir)):
        abort(403)

    # Reject .py files
    if filename.lower().endswith(".py"):
        abort(403)

    # File size limit
    if os.path.exists(resolved_path) and os.path.getsize(resolved_path) > 10 * 1024 * 1024:
        abort(413)

    response = send_from_directory(user_dir, filename)
    # 使用 RFC 5987 编码支持中文文件名（避免 latin-1 编码错误）
    safe_filename = os.path.basename(filename)
    try:
        # 尝试用 latin-1 编码，如果成功则用普通方式
        safe_filename.encode("latin-1")
        disposition = f'attachment; filename="{safe_filename}"'
    except UnicodeEncodeError:
        # 包含非 latin-1 字符（如中文），使用 RFC 5987 编码
        import urllib.parse
        encoded_name = urllib.parse.quote(safe_filename, encoding="utf-8")
        disposition = f"attachment; filename*=UTF-8''{encoded_name}"
    response.headers["Content-Disposition"] = disposition
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/sandbox_read_file")
@login_required
@require_plugin(blueprint_name)
def sandbox_file_compat():
    """Compatibility route for agent-generated URLs."""
    filename = request.args.get("filename", "")
    if not filename:
        abort(404)
    return redirect(url_for("chat.sandbox_file", filename=filename))


@bp.route("/speech_to_text", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def speech_to_text():
    """接收前端录音音频，使用 FunASR 离线语音识别转文字"""
    if "audio" not in request.files:
        return {"error": "未找到音频文件"}, 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return {"error": "音频文件为空"}, 400

    try:
        from app.services.voice_service import speech_to_text as funasr_stt
        audio_data = audio_file.read()
        audio_format = audio_file.content_type or "audio/webm"
        text = funasr_stt(audio_data, audio_format)
        if text:
            return {"text": text}
        else:
            return {"error": "语音识别未能识别出文字，请重试"}, 400
    except ImportError:
        return {"error": "FunASR 未安装，请执行: pip install funasr"}, 500
    except Exception as e:
        current_app.logger.error(f"FunASR 语音识别失败: {str(e)}")
        return {"error": f"语音识别失败: {str(e)}"}, 500


@bp.route("/text_to_speech", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def text_to_speech_route():
    """文本转语音，使用 Edge TTS 合成语音返回音频"""
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return {"error": "文本内容不能为空"}, 400

    voice = data.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = data.get("rate", "+0%")
    pitch = data.get("pitch", "+0Hz")
    style = data.get("style", "general")

    try:
        from app.services.voice_service import text_to_speech as edge_tts
        audio_data = edge_tts(text, voice=voice, rate=rate, pitch=pitch, style=style)
        return Response(audio_data, mimetype="audio/mpeg", headers={
            "Content-Disposition": "inline; filename=speech.mp3",
            "Content-Length": str(len(audio_data)),
        })
    except ImportError:
        return {"error": "Edge TTS 未安装，请执行: pip install edge-tts"}, 500
    except Exception as e:
        current_app.logger.error(f"Edge TTS 合成失败: {str(e)}")
        return {"error": f"语音合成失败: {str(e)}"}, 500


@bp.route("/text_to_speech_stream", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def text_to_speech_stream_route():
    """文本转语音 SSE 流式输出。

    使用 Edge TTS 逐 chunk 合成音频，通过 SSE 事件流式发送 base64 编码的音频数据。
    前端可以用 MediaSource API 逐段拼接播放，实现边合成边播放。
    """
    data = request.get_json() or {}
    text = (data.get("text") or "").strip()
    if not text:
        return {"error": "文本内容不能为空"}, 400

    voice = data.get("voice", "zh-CN-XiaoxiaoNeural")
    rate = data.get("rate", "+0%")
    pitch = data.get("pitch", "+0Hz")
    style = data.get("style", "general")

    def generate():
        try:
            from app.services.voice_service import text_to_speech_stream
            import base64

            chunk_count = 0
            for chunk in text_to_speech_stream(text, voice=voice, rate=rate, pitch=pitch, style=style):
                if chunk:
                    chunk_count += 1
                    b64_data = base64.b64encode(chunk).decode("utf-8")
                    yield f"data: {json.dumps({'type': 'audio_chunk', 'data': b64_data, 'index': chunk_count})}\n\n"

            # 发送完成事件
            yield f"data: {json.dumps({'type': 'done', 'chunks': chunk_count})}\n\n"

        except ImportError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Edge TTS 未安装，请执行: pip install edge-tts'})}\n\n"
        except Exception as e:
            current_app.logger.error(f"Edge TTS 流式合成失败: {str(e)}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'语音合成失败: {str(e)}'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@bp.route("/tts_voices", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def tts_voices():
    """获取可用的 TTS 语音列表"""
    try:
        from app.services.voice_service import get_available_voices
        return {"voices": get_available_voices()}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route("/tts_styles", methods=["GET"])
@login_required
@require_plugin(blueprint_name)
def tts_styles():
    """获取可用的 TTS 说话风格列表"""
    try:
        from app.services.voice_service import get_voice_styles
        return {"styles": get_voice_styles()}
    except Exception as e:
        return {"error": str(e)}, 500


@bp.route("/vad_detect", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def vad_detect_route():
    """服务端 VAD 检测：判断音频中是否包含语音"""
    if "audio" not in request.files:
        return {"error": "未找到音频文件"}, 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return {"error": "音频文件为空"}, 400

    try:
        from app.services.voice_service import vad_detect
        audio_data = audio_file.read()
        audio_format = audio_file.content_type or "audio/webm"
        result = vad_detect(audio_data, audio_format)
        return result
    except Exception as e:
        current_app.logger.error(f"VAD 检测失败: {str(e)}")
        return {"has_speech": False, "segments": [], "speech_duration_ms": 0}


@bp.route("/audio_duration", methods=["POST"])
@login_required
@require_plugin(blueprint_name)
def audio_duration_route():
    """获取音频时长"""
    if "audio" not in request.files:
        return {"error": "未找到音频文件"}, 400

    audio_file = request.files["audio"]
    if not audio_file.filename:
        return {"error": "音频文件为空"}, 400

    try:
        from app.services.voice_service import get_audio_duration
        audio_data = audio_file.read()
        audio_format = audio_file.content_type or "audio/webm"
        duration = get_audio_duration(audio_data, audio_format)
        return {"duration": duration}
    except Exception as e:
        current_app.logger.error(f"获取音频时长失败: {str(e)}")
        return {"duration": 0}
