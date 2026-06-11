import os
import time
import json
import subprocess
import requests as _requests
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from .main import bp, blueprint_name
from app.extensions.init_sqlalchemy import db
from app.logger import log_admin
from app.extensions.init_loginmanager import admin_required
from app.extensions.init_csrf import csrf_protected
from app.models.mcp_tool import MCPTool
from app.models.api_endpoint import APIEndpoint
from app.utils.plugin_utils import require_plugin
from app.utils.settings import get_setting_int


# ============ MCP Tool Management ============

@bp.route("/mcp-tools")
@admin_required
@require_plugin(blueprint_name)
def mcp_tools():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", get_setting_int("admin_per_page", 20), type=int)
    pagination = MCPTool.query.order_by(MCPTool.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    mcp_tools = pagination.items
    return render_template("admin/mcp_tools.html", mcp_tools=mcp_tools, pagination=pagination)


@bp.route("/mcp-tools/add", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def mcp_tool_add():
    data = request.form
    tool = MCPTool(
        name=data.get("name"),
        description=data.get("description"),
        tool_type=data.get("tool_type", "custom"),
        transport=data.get("transport", "stdio"),
        command=data.get("command"),
        args=data.get("args"),
        env_vars=data.get("env_vars"),
        endpoint=data.get("endpoint"),
        is_active=data.get("is_active") == "true",
    )
    db.session.add(tool)
    db.session.commit()
    log_admin("MCP工具已添加 — name=%s", tool.name)
    flash("MCP工具添加成功。", "success")
    return redirect(url_for("admin.mcp_tools"))


@bp.route("/mcp-tools/<int:tool_id>/edit", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def mcp_tool_edit(tool_id):
    tool = MCPTool.query.get_or_404(tool_id)
    data = request.form

    tool.name = data.get("name", tool.name)
    tool.description = data.get("description", tool.description)
    tool.tool_type = data.get("tool_type", tool.tool_type)
    tool.transport = data.get("transport", tool.transport)
    tool.command = data.get("command", tool.command)
    tool.args = data.get("args", tool.args)
    tool.env_vars = data.get("env_vars", tool.env_vars)
    tool.endpoint = data.get("endpoint", tool.endpoint)
    tool.is_active = data.get("is_active") == "true"

    db.session.commit()
    log_admin("MCP工具已编辑 — tool_id=%d, name=%s", tool.id, tool.name)
    flash("MCP工具更新成功。", "success")
    return redirect(url_for("admin.mcp_tools"))


@bp.route("/mcp-tools/<int:tool_id>/delete", methods=["POST"])
@admin_required
@csrf_protected
@require_plugin(blueprint_name)
def mcp_tool_delete(tool_id):
    log_admin("MCP工具已删除 — tool_id=%d", tool_id)
    tool = MCPTool.query.get_or_404(tool_id)
    db.session.delete(tool)
    db.session.commit()
    flash("MCP工具已删除。", "success")
    return redirect(url_for("admin.mcp_tools"))


@bp.route("/mcp-tools/<int:tool_id>/test")
@admin_required
@require_plugin(blueprint_name)
def mcp_tool_test(tool_id):
    """Test MCP tool connectivity (stdio, SSE, or Streamable HTTP)."""
    tool = MCPTool.query.get_or_404(tool_id)
    transport = tool.transport or ("sse" if tool.endpoint else "stdio")
    result = {"name": tool.name, "type": tool.tool_type, "transport": transport, "success": False, "detail": ""}
    start = time.time()
    if transport == "streamable_http" and tool.endpoint:
        try:
            from app.services.tools import MCPExecutor
            tools = MCPExecutor.list_tools_streamable_http(tool.endpoint)
            result["success"] = True
            result["detail"] = f"Streamable HTTP连接成功, 发现{len(tools)}个子工具"
            result["tools"] = [t["name"] for t in tools]
        except Exception as e:
            result["detail"] = f"Streamable HTTP连接失败: {e}"
    elif tool.endpoint:
        try:
            from app.services.tools import MCPExecutor
            tools = MCPExecutor.list_tools_sse(tool.endpoint)
            result["success"] = True
            result["detail"] = f"SSE连接成功, 发现{len(tools)}个子工具"
            result["tools"] = [t["name"] for t in tools]
        except Exception as e:
            result["detail"] = f"SSE连接失败: {e}"
    elif tool.command:
        try:
            cmd_list = tool.command.split()
            env = os.environ.copy()
            if tool.env_vars:
                try: env.update(json.loads(tool.env_vars))
                except: pass
            NL = chr(10)
            req = json.dumps({"jsonrpc":"2.0","method":"tools/list","id":1}) + NL
            proc = subprocess.run(cmd_list, input=req, capture_output=True, text=True, timeout=10, env=env)
            if proc.returncode == 0:
                try:
                    data = json.loads(proc.stdout.strip().split(NL)[-1])
                    tools = data.get("result", {}).get("tools", [])
                    result["success"] = True
                    result["detail"] = f"进程启动成功, 发现{len(tools)}个子工具"
                    result["tools"] = [t.get("name","?") for t in tools]
                except json.JSONDecodeError:
                    result["detail"] = f"进程启动但返回非JSON: {proc.stdout[:200]}"
            else:
                result["detail"] = f"进程退出(code={proc.returncode}): {proc.stderr[:200]}"
        except FileNotFoundError:
            result["detail"] = f"命令未找到: {tool.command}"
        except subprocess.TimeoutExpired:
            result["detail"] = "命令超时(10秒)"
        except Exception as e:
            result["detail"] = f"测试失败: {e}"
    else:
        result["detail"] = "未配置命令或端点"
    result["latency_ms"] = round((time.time() - start) * 1000)
    return jsonify(result)


@bp.route("/api-endpoints/<int:ep_id>/test")
@admin_required
@require_plugin(blueprint_name)
def api_endpoint_test(ep_id):
    """Test API endpoint connectivity."""
    ep = APIEndpoint.query.get_or_404(ep_id)
    result = {"name": ep.name, "url": ep.url, "method": ep.method, "success": False, "status_code": 0, "detail": ""}
    start = time.time()
    try:
        headers = {}
        if ep.headers:
            try: headers.update(json.loads(ep.headers))
            except: pass
        if ep.auth_type == "bearer" and ep.auth_value:
            headers["Authorization"] = f"Bearer {ep.auth_value}"
        elif ep.auth_type == "api_key" and ep.auth_value:
            headers["X-API-Key"] = ep.auth_value
        meth = ep.method.upper()
        timeout = 10
        if meth == "GET": resp = _requests.get(ep.url, headers=headers, timeout=timeout)
        elif meth == "POST": resp = _requests.post(ep.url, headers=headers, timeout=timeout)
        elif meth == "PUT": resp = _requests.put(ep.url, headers=headers, timeout=timeout)
        elif meth == "DELETE": resp = _requests.delete(ep.url, headers=headers, timeout=timeout)
        else: result["detail"] = f"不支持的方法: {meth}"; return jsonify(result)
        latency = round((time.time() - start) * 1000)
        result["latency_ms"] = latency
        result["status_code"] = resp.status_code
        result["success"] = 200 <= resp.status_code < 500
        if 200 <= resp.status_code < 300:
            result["detail"] = f"连接成功 - HTTP {resp.status_code}, {latency}ms"
        elif resp.status_code < 500:
            result["detail"] = f"请求异常 - HTTP {resp.status_code}, {latency}ms"
        else:
            result["detail"] = f"服务端错误 - HTTP {resp.status_code}, {latency}ms"
    except _requests.exceptions.ConnectionError:
        result["detail"] = "连接被拒绝 - 目标服务器不可达"
    except _requests.exceptions.Timeout:
        result["detail"] = "连接超时(10秒)"
    except Exception as e:
        result["detail"] = f"测试失败: {e}"
    return jsonify(result)


