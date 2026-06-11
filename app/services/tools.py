"""
Tool registry and executors for agent tool calling.

Supports four tool types:
- skills  - load SKILL.md descriptions as functions + execute Python helpers
- mcp    - connect to MCP servers (stdio / SSE) and call their tools
- api    - call registered HTTP API endpoints
- sandbox - execute Python/shell code in a restricted directory
"""

import os
import json
import subprocess
import uuid
import importlib.util
import sys
import re
import ast
import yaml
import requests as _requests
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlunparse
from app.utils.settings import get_setting_int


# ── Shared SKILL.md utilities ──────────────────────────────────────────────

def _read_skill_md_content(skills_dir: str, skill_name: str) -> str:
    """Read SKILL.md content (without frontmatter)."""
    md_path = os.path.join(skills_dir, skill_name, "SKILL.md")
    if not os.path.exists(md_path):
        return ""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        return content
    except Exception:
        return ""


def _parse_skill_md(skills_dir: str, skill_name: str) -> dict:
    """Parse SKILL.md and return a dict with description, params, and body content.
    
    Returns {"description": str, "params": dict|None, "body": str}
    Caches results per (skills_dir, skill_name) to avoid repeated disk I/O.
    """
    cache_key = (skills_dir, skill_name)
    if cache_key in _skill_md_cache:
        return _skill_md_cache[cache_key]
    
    md_path = os.path.join(skills_dir, skill_name, "SKILL.md")
    result = {"description": "", "params": None, "body": ""}
    
    if not os.path.exists(md_path):
        _skill_md_cache[cache_key] = result
        return result
    
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        desc = ""
        params = None
        body = content
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                desc = fm.get("description", "")
                params = _parse_parameters_from_frontmatter(fm)
                body = parts[2].strip()
        
        result = {"description": desc, "params": params, "body": body}
        _skill_md_cache[cache_key] = result
        return result
    except Exception:
        _skill_md_cache[cache_key] = result
        return result


_skill_md_cache = {}  # (skills_dir, skill_name) -> parsed dict


def _parse_parameters_from_frontmatter(fm: dict) -> dict:
    """Parse OpenAI-compatible parameter definitions from YAML frontmatter."""
    raw_params = fm.get("parameters")
    if not raw_params or not isinstance(raw_params, list):
        return None
    
    type_map = {
        "string": "string", "integer": "integer",
        "number": "number", "boolean": "boolean",
    }
    props = {}
    required = []
    for p in raw_params:
        name = p.get("name")
        if not name:
            continue
        ptype = type_map.get(p.get("type", "string"), "string")
        prop = {"type": ptype}
        if p.get("description"):
            prop["description"] = p["description"]
        if p.get("enum"):
            prop["enum"] = p["enum"]
        props[name] = prop
        if p.get("required", False):
            required.append(name)
    return {"props": props, "required": required}


# --- Skill Executor -----------------------------------------------------------

class SkillExecutor:
    """Execute a skill's Python helper.

    Modules are cached in-process after first load (keyed by mtime) to
    avoid redundant disk I/O and recompilation on repeated calls.
    """

    _module_cache = {}
    _docs_shown = set()  # Track which skills have had SKILL.md shown before first execution

    def __init__(self, skills_dir: str):
        self.skills_dir = skills_dir

    def _read_skill_md(self, skill_name: str) -> str:
        """Read SKILL.md content (without frontmatter)."""
        return _read_skill_md_content(self.skills_dir, skill_name)

    def _load_skill_module(self, skill_name: str):
        """Load (or reload from cache) a skill's Python module."""
        folder = os.path.join(self.skills_dir, skill_name)
        py_file = None
        for f in os.listdir(folder):
            if f.endswith(".py") and f != "__init__.py":
                py_file = os.path.join(folder, f)
                break
        if not py_file:
            raise FileNotFoundError(f"no Python helper found in skill '{skill_name}'")
        current_mtime = os.path.getmtime(py_file)
        cached = self._module_cache.get(skill_name)
        if cached and cached[1] == current_mtime:
            return cached[0]
        mod_name = f"_cached_{skill_name.replace('-', '_')}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        spec = importlib.util.spec_from_file_location(mod_name, py_file)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        self._module_cache[skill_name] = (mod, current_mtime)
        return mod

    def execute(self, skill_name: str, action: str = "run", sandbox_dir: str = None, **kwargs) -> str:
        # Security: block path traversal in skill arguments
        for _key, _val in kwargs.items():
            if isinstance(_val, str) and _key in ('file_path', 'expression', 'filename', 'path'):
                if '..' in _val or _val.startswith('/') or (_val[1:3] if len(_val) > 2 else '') == ':\\':
                    return f"安全策略限制：参数 '{_key}' 包含路径遍历或绝对路径，已拒绝。"
        folder = os.path.join(self.skills_dir, skill_name)
        if not os.path.isdir(folder):
            return f"Error: skill '{skill_name}' not found"

        # action="help" - return full SKILL.md content
        if action == "help":
            content = self._read_skill_md(skill_name)
            if content:
                return f"# Skill: {skill_name}\n\n{content}"
            return f"Error: SKILL.md not found for skill '{skill_name}'"

        # First call: return SKILL.md documentation without executing
        if skill_name not in self._docs_shown:
            self._docs_shown.add(skill_name)
            doc = self._read_skill_md(skill_name)
            if doc:
                return (f"# Skill: {skill_name}\n\n{doc}\n\n"
                        "---\n"
                        "This is the documentation for this skill. "
                        "Read it carefully to learn how to use this skill, "
                        "then call this skill again with the appropriate parameters to execute it.")

        # Load (or reuse cached) module
        try:
            mod = self._load_skill_module(skill_name)
            # Inject sandbox_dir into kwargs so skills can save files to sandbox
            if sandbox_dir:
                kwargs["sandbox_dir"] = sandbox_dir
            if hasattr(mod, action):
                func = getattr(mod, action)
                result = func(**kwargs)
            elif hasattr(mod, "run"):
                func = getattr(mod, "run")
                result = func(action=action, **kwargs)
            else:
                return f"Error: action '{action}' not found in skill '{skill_name}'"
            return str(result)
        except FileNotFoundError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Skill execution error: {e}"

    @staticmethod
    def _read_skill_md_static(skills_dir: str, skill_name: str) -> str:
        """Static version of _read_skill_md for use in ToolRegistry.build_definitions."""
        return _read_skill_md_content(skills_dir, skill_name)

    @staticmethod
    def read_skill_description(skills_dir: str, skill_name: str) -> str:
        """Read a rich description from SKILL.md (frontmatter + capability summary)."""
        parsed = _parse_skill_md(skills_dir, skill_name)
        desc = parsed.get("description", "")
        body = parsed.get("body", "")
        if not body:
            return desc or ""

        lines = body.split("\n")
        caps = []
        examples = []

        in_caps = False
        in_example = False
        example_block = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") and ("能力" in stripped or "Capabilit" in stripped):
                in_caps = True
                continue
            elif stripped.startswith("## ") and ("示例" in stripped or "Example" in stripped or "使用方式" in stripped or "Usage" in stripped):
                in_caps = False
                in_example = True
                continue
            elif stripped.startswith("## "):
                in_caps = False
                in_example = False
                continue

            if in_caps and stripped.startswith("- "):
                cap = stripped.lstrip("- ").split(":")[0].split("：")[0].strip()
                if cap and len(cap) < 60:
                    caps.append(cap)

            if in_example and stripped:
                example_block += stripped + " "

        parts = [desc] if desc else []
        if caps:
            parts.append("能力: " + ", ".join(caps[:5]))
        if example_block and len(parts) < 3:
            ex = example_block.strip()[:80]
            if ex:
                parts.append("示例: " + ex)

        result = " | ".join(parts) if len(" ".join(parts)) < 120 else " - ".join(parts[:2])
        return result[:120]

    @staticmethod
    def read_skill_parameters(skills_dir: str, skill_name: str) -> dict:
        """Read structured parameter definitions from SKILL.md frontmatter.

        Returns {"props": {...}, "required": [...]} or None if not defined.
        """
        parsed = _parse_skill_md(skills_dir, skill_name)
        return parsed.get("params")


# --- MCP Tool Executor -------------------------------------------------------

class MCPExecutor:
    """Connect to MCP servers and call tools.

    Supports stdio (subprocess), SSE (HTTP), and Streamable HTTP transports.
    """

    @staticmethod
    def call_stdio_tool(command: str, args: str = None, env_vars: str = None,
                        tool_name: str = "", tool_args: dict = None) -> str:
        """Call a tool via a stdio MCP server using the JSON-RPC protocol."""
        try:
            cmd_list = command.split()
            env = os.environ.copy()
            if env_vars:
                try:
                    env.update(json.loads(env_vars))
                except json.JSONDecodeError:
                    pass

            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": tool_args or {},
                },
                "id": 1,
            }
            proc = subprocess.run(
                cmd_list,
                input=json.dumps(request) + "\n",
                capture_output=True,
                text=True,
                timeout=get_setting_int("mcp_tool_timeout", 30),
                env=env,
            )
            if proc.returncode != 0:
                return f"MCP error (exit {proc.returncode}): {proc.stderr[:500]}"
            try:
                result = json.loads(proc.stdout.strip().split("\n")[-1])
                return json.dumps(result.get("result", result))
            except json.JSONDecodeError:
                return proc.stdout[:2000]
        except subprocess.TimeoutExpired:
            return "MCP tool timed out"
        except FileNotFoundError:
            return f"MCP command not found: {command}"
        except Exception as e:
            return f"MCP error: {e}"

    @staticmethod
    def list_tools_sse(endpoint: str) -> list:
        """Connect to an MCP SSE server and discover available tools.
        Returns list of dicts: [{name, description, inputSchema}, ...]"""
        import anyio

        async def _run():
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            parsed = urlparse(endpoint)
            query_params = parse_qs(parsed.query)
            auth_token = query_params.get("Authorization", [None])[0]
            headers = {"Accept": "text/event-stream"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            async with sse_client(url=endpoint, headers=headers, sse_read_timeout=get_setting_int("mcp_sse_discovery_timeout", 30)) as streams:
                read, write = streams
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools = []
                    for t in result.tools:
                        schema = dict(t.inputSchema) if t.inputSchema else {}
                        if "required" not in schema:
                            schema["required"] = []
                        tools.append({
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": schema,
                        })
                    return tools

        try:
            return anyio.run(_run)
        except Exception as e:
            raise RuntimeError(f"MCP list_tools error: {e}")

    @staticmethod
    def call_sse_tool(endpoint: str, tool_name: str = "",
                      tool_args: dict = None) -> str:
        """Call a tool via an SSE MCP server using the official mcp library."""
        import traceback
        import anyio

        async def _run():
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            parsed = urlparse(endpoint)
            query_params = parse_qs(parsed.query)
            auth_token = query_params.get("Authorization", [None])[0]
            headers = {"Accept": "text/event-stream"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            try:
                async with sse_client(
                    url=endpoint, headers=headers, sse_read_timeout=get_setting_int("mcp_sse_call_timeout", 120)
                ) as streams:
                    read, write = streams
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, tool_args or {})
                        parts = []
                        for content in result.content:
                            parts.append(content.text if hasattr(content, "text") else str(content))
                        if parts:
                            return "\n".join(parts)
                        if result.isError:
                            return f"MCP tool error: {result.content}"
                        return "execute error"
            except TimeoutError:
                return "MCP SSE error: tool call timed out (120s)"
            except Exception as e:
                tb = traceback.format_exc()
                return f"MCP SSE error: {e}\n{tb[:1000]}"

        try:
            return anyio.run(_run)
        except Exception as e:
            tb = traceback.format_exc()
            return f"MCP SSE error: {e}\n{tb[:1000]}"

    @staticmethod
    def list_tools_streamable_http(endpoint: str) -> list:
        """Connect to a Streamable HTTP MCP server and discover available tools.
        Returns list of dicts: [{name, description, inputSchema}, ...]"""
        import anyio

        async def _run():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            parsed = urlparse(endpoint)
            query_params = parse_qs(parsed.query)
            auth_token = query_params.get("Authorization", [None])[0]
            headers = {"Accept": "application/json"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            async with streamablehttp_client(url=endpoint, headers=headers) as streams:
                read, write, get_session_id = streams
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools = []
                    for t in result.tools:
                        schema = dict(t.inputSchema) if t.inputSchema else {}
                        if "required" not in schema:
                            schema["required"] = []
                        tools.append({
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": schema,
                        })
                    return tools

        try:
            return anyio.run(_run)
        except Exception as e:
            raise RuntimeError(f"MCP Streamable HTTP list_tools error: {e}")

    @staticmethod
    def call_streamable_http_tool(endpoint: str, tool_name: str = "",
                                   tool_args: dict = None) -> str:
        """Call a tool via a Streamable HTTP MCP server using the official mcp library."""
        import traceback
        import anyio

        async def _run():
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client

            parsed = urlparse(endpoint)
            query_params = parse_qs(parsed.query)
            auth_token = query_params.get("Authorization", [None])[0]
            headers = {"Accept": "application/json"}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            try:
                async with streamablehttp_client(url=endpoint, headers=headers) as streams:
                    read, write, get_session_id = streams
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, tool_args or {})
                        parts = []
                        for content in result.content:
                            parts.append(content.text if hasattr(content, "text") else str(content))
                        if parts:
                            return "\n".join(parts)
                        if result.isError:
                            return f"MCP tool error: {result.content}"
                        return "execute error"
            except TimeoutError:
                return "MCP Streamable HTTP error: tool call timed out"
            except Exception as e:
                tb = traceback.format_exc()
                return f"MCP Streamable HTTP error: {e}\n{tb[:1000]}"

        try:
            return anyio.run(_run)
        except Exception as e:
            tb = traceback.format_exc()
            return f"MCP Streamable HTTP error: {e}\n{tb[:1000]}"


# --- API Executor ------------------------------------------------------------

class APIExecutor:
    """Call registered HTTP API endpoints."""

    @staticmethod
    def call(endpoint: dict, params: dict = None) -> str:
        """Execute an API endpoint call.

        endpoint dict keys: url, method, headers (JSON str), auth_type, auth_value
        """
        method = (endpoint.get("method") or "GET").upper()
        url = endpoint["url"]
        headers = {}
        if endpoint.get("headers"):
            try:
                headers = json.loads(endpoint["headers"])
            except json.JSONDecodeError:
                pass

        auth_type = endpoint.get("auth_type", "none")
        auth_value = endpoint.get("auth_value", "")
        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "api_key":
            headers["X-API-Key"] = auth_value
        elif auth_type == "basic" and auth_value:
            import base64
            headers["Authorization"] = f"Basic {base64.b64encode(auth_value.encode()).decode()}"

        try:
            _to = get_setting_int("api_endpoint_timeout", 15)
            if method == "GET":
                resp = _requests.get(url, headers=headers, params=params or {}, timeout=_to)
            elif method == "POST":
                resp = _requests.post(url, headers=headers, json=params or {}, timeout=_to)
            elif method == "PUT":
                resp = _requests.put(url, headers=headers, json=params or {}, timeout=_to)
            elif method == "DELETE":
                resp = _requests.delete(url, headers=headers, timeout=_to)
            else:
                return f"Unsupported method: {method}"

            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return json.dumps(resp.json(), ensure_ascii=False)
            max_out = get_setting_int("api_output_max_chars", 3000)
            return resp.text[:max_out]
        except Exception as e:
            return f"API call error: {e}"


# --- Sandbox Executor --------------------------------------------------------

class SandboxExecutor:
    """Execute code in a restricted local directory with security controls."""

    _SENSITIVE_ENV_KEYS = [
        "API_KEY", "SECRET", "PASSWORD", "TOKEN", "AUTH",
        "PRIVATE_KEY", "ACCESS_KEY", "SECRET_KEY",
    ]

    _DANGEROUS_PATTERNS = {
        "HTTP_server": [
            "http.server", "HTTPServer", "SimpleHTTPRequestHandler",
            "socketserver.TCPServer", "socketserver.UDPServer",
            "flask.run", "uvicorn.run",
            "BaseHTTPRequestHandler", "make_server", "WSGIServer",
        ],
        "system_command": [
            "os.system(", "os.popen(", "subprocess.run(",
            "subprocess.Popen(", "subprocess.call(",
            "subprocess.check_output(", "commands.getoutput(",
            "subprocess.getoutput(", "ctypes.windll",
        ],
        "filesystem_access": [
            'open("C:\\', "open('/etc/", "open('/var/", "open('/usr/",
            "open('/bin/", "open('/boot/", "open('/dev/",
            "open('/proc/", "open('/sys/",
            'open(r"C:\\', "open(r'/etc/", "open(r'/var/",
            'os.listdir("C:\\', 'os.listdir("/etc"', 'os.listdir("/var"',
            'os.listdir("/"', "os.listdir('C:",
            'os.walk("C:\\', 'os.walk("/etc"', 'os.walk("/var"',
            "os.walk('.", 'os.walk("..',
            "os.scandir(", "os.mkdir(", "os.makedirs(",
            "shutil.copy", "shutil.move", "shutil.rmtree",
            "os.remove(", "os.unlink(", "os.rename(", "os.chdir(",
            'open("..', "open('..",
            'Path("..', "Path('..",
            "Path.open(", "Path.read_text", "Path.write_text",
            "Path.read_bytes", "Path.write_bytes",
            "Path.iterdir", "Path.glob", "Path.rglob",
        ],
        "env_access": [
            "os.environ[", "os.environ.get(", "os.getenv(",
            "os.environ.__getitem__",
        ],
        "dangerous_import": [
            "import subprocess", "import socket", "import http.client",
            "import smtplib", "import ftplib", "import telnetlib",
            "import ctypes", "import winreg", "import win32api",
            "from subprocess", "from ctypes", "from winreg",
        ],
        "system_info": [
            "platform.uname", "platform.processor", "platform.node",
            "os.uname(", "os.cpu_count(", "psutil.",
            "wmi.", "win32com.",
        ],
    }

    _SHELL_BLOCKLIST = [
        "http.server", "flask run", "uvicorn", "gunicorn",
        "python -m http", "node server", "npm start", "serve ",
        "netcat -l", "nc -l", "socat",
        "systeminfo", "whoami", "net user", "ipconfig", "ifconfig",
        "tasklist", "wmic", "reg query", "type ",
        "powershell",
    ]

    def __init__(self, sandbox_dir: str):
        self.sandbox_dir = Path(sandbox_dir).resolve()
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def _user_dir(self, user_id=None) -> Path:
        try:
            os.makedirs(self.sandbox_dir, exist_ok=True)
            if user_id:
                d = self.sandbox_dir / str(user_id)
                os.makedirs(d, exist_ok=True)
                return d
            return self.sandbox_dir
        except PermissionError as e:
            raise PermissionError(
                f"沙箱目录权限不足: {e}\n"
                f"请检查目录 '{self.sandbox_dir}' 的写入权限，"
                f"或尝试以管理员身份运行。"
            ) from e

    def _ensure_in_sandbox(self, rel_path: str, user_id=None) -> Path:
        base = self._user_dir(user_id)
        target = (base / rel_path).resolve()
        if not str(target).startswith(str(base)):
            raise ValueError(f"Path outside sandbox: {rel_path}")
        return target

    @staticmethod
    def _sanitize_env() -> dict:
        """Create a clean environment with sensitive variables stripped."""
        env = os.environ.copy()
        keys_to_remove = []
        for key in env:
            upper = key.upper()
            for sensitive in SandboxExecutor._SENSITIVE_ENV_KEYS:
                if sensitive in upper:
                    keys_to_remove.append(key)
                    break
        for k in keys_to_remove:
            del env[k]
        return env

    @staticmethod
    def _detect_dangerous_code(code: str) -> str:
        """Scan code for dangerous patterns using AST parsing (primary) + string matching (fallback).
        
        AST-based detection is more accurate and harder to bypass than simple string matching.
        Returns error message or None.
        """
        
        # ── AST-based detection (primary) ──────────────────────────────
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                # Detect calls to dangerous functions
                if isinstance(node, ast.Call):
                    func = node.func
                    # os.system(...), os.popen(...), subprocess.*(...)
                    if isinstance(func, ast.Attribute):
                        if isinstance(func.value, ast.Name):
                            if func.value.id == "os" and func.attr in ("system", "popen"):
                                return (
                                    f"安全策略限制：检测到危险操作 'os.{func.attr}'（类别: system_command）。\n"
                                    f"沙箱不允许执行系统命令。\n"
                                    f"如果你需要操作文件，请使用 sandbox_read_file / sandbox_write_file 工具。"
                                )
                            if func.value.id == "subprocess" and func.attr in ("run", "Popen", "call", "check_output", "getoutput"):
                                return (
                                    f"安全策略限制：检测到危险操作 'subprocess.{func.attr}'（类别: system_command）。\n"
                                    f"沙箱不允许执行系统命令。\n"
                                    f"如果你需要操作文件，请使用 sandbox_read_file / sandbox_write_file 工具。"
                                )
                            if func.value.id == "ctypes" and func.attr == "windll":
                                return (
                                    f"安全策略限制：检测到危险操作 'ctypes.windll'（类别: system_command）。\n"
                                    f"沙箱不允许加载系统库。"
                                )
                            if func.value.id == "os" and func.attr in ("getenv",):
                                return (
                                    f"安全策略限制：检测到危险操作 'os.{func.attr}'（类别: env_access）。\n"
                                    f"沙箱不允许读取环境变量。"
                                )
                            if func.value.id == "platform" and func.attr in ("uname", "processor", "node"):
                                return (
                                    f"安全策略限制：检测到危险操作 'platform.{func.attr}'（类别: system_info）。\n"
                                    f"沙箱不允许收集系统信息。"
                                )
                        # open("/etc/..."), open("C:\\...") — detect absolute path arguments
                        if isinstance(func, ast.Name) and func.id == "open":
                            if node.args:
                                arg = node.args[0]
                                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                    _path_val = arg.value
                                    if _path_val.startswith(("/", "C:\\", "c:\\")):
                                        return (
                                            f"安全策略限制：检测到危险操作 'open({_path_val})'（类别: filesystem_access）。\n"
                                            f"沙箱不允许访问系统绝对路径。\n"
                                            f"如果你需要操作文件，请使用 sandbox_read_file / sandbox_write_file 工具。"
                                        )
                
                # Detect dangerous imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in ("subprocess", "socket", "http.client", "smtplib", "ftplib", "telnetlib", "ctypes", "winreg", "win32api"):
                            return (
                                f"安全策略限制：检测到危险导入 '{alias.name}'（类别: dangerous_import）。\n"
                                f"沙箱不允许加载危险模块。"
                            )
                if isinstance(node, ast.ImportFrom):
                    if node.module in ("subprocess", "ctypes", "winreg"):
                        return (
                            f"安全策略限制：检测到危险导入 '{node.module}'（类别: dangerous_import）。\n"
                            f"沙箱不允许加载危险模块。"
                        )
                
                # Detect os.environ access
                if isinstance(node, ast.Subscript):
                    if isinstance(node.value, ast.Attribute):
                        if isinstance(node.value.value, ast.Name) and node.value.value.id == "os" and node.value.attr == "environ":
                            return (
                                f"安全策略限制：检测到危险操作 'os.environ'（类别: env_access）。\n"
                                f"沙箱不允许读取环境变量。"
                            )
        except SyntaxError:
            # If code can't be parsed, fall through to string matching
            pass
        
        # ── String-based fallback (for obfuscated or non-Python code) ──
        for category, patterns in SandboxExecutor._DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if pattern in code:
                    return (
                        f"安全策略限制：检测到危险操作模式 '{pattern}'（类别: {category}）。\n"
                        f"沙箱不允许执行系统命令、访问系统文件、读取环境变量或加载危险模块。\n"
                        f"如果你需要操作文件，请使用 sandbox_read_file / sandbox_write_file 工具。"
                    )
        return None

    @staticmethod
    def _filter_sensitive_output(text: str) -> str:
        """Filter potentially sensitive data from output."""
        text = re.sub(r'(?i)(api[_-]?key["\s:=]+)[\w\-]{8,}', r'\1***REDACTED***', text)
        text = re.sub(r'(?i)(secret["\s:=]+)[\w\-]{8,}', r'\1***REDACTED***', text)
        text = re.sub(r'(?i)(password["\s:=]+)[\w\-]{4,}', r'\1***REDACTED***', text)
        text = re.sub(r'(?i)(token["\s:=]+)[\w\-]{8,}', r'\1***REDACTED***', text)
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            if len(line) > 500:
                line = line[:500] + "... [truncated]"
            cleaned.append(line)
        return "\n".join(cleaned)

    def execute_python(self, code: str, timeout: int = 30, user_id=None) -> str:
        err = self._detect_dangerous_code(code)
        if err:
            return err

        script = self._user_dir(user_id) / f"script_{uuid.uuid4().hex}.py"
        proc = None
        try:
            script.write_text(code, encoding="utf-8")
            clean_env = self._sanitize_env()
            proc = subprocess.Popen(
                ["python", str(script)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=str(self._user_dir(user_id)),
                env=clean_env,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                out = stdout or ""
                if stderr:
                    out += "\n[stderr]\n" + stderr
                max_out = get_setting_int("sandbox_output_max_chars", 5000)
                result = out[:max_out] or "(no output)"
                return self._filter_sensitive_output(result)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                return "Execution timed out"
        except Exception as e:
            return f"Sandbox error: {e}"
        finally:
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass
            if script.exists():
                script.unlink()

    def execute_shell(self, command: str, timeout: int = 30, user_id=None) -> str:
        cmd_lower = command.lower()
        for pattern in self._SHELL_BLOCKLIST:
            if pattern in cmd_lower:
                return (
                    f"安全策略限制：检测到危险命令模式 '{pattern}'。\n"
                    f"沙箱不允许执行系统信息收集、网络请求、密码读取等命令。\n"
                    f"请使用 sandbox_write_file / sandbox_read_file 工具操作文件。"
                )
        try:
            clean_env = self._sanitize_env()
            result = subprocess.run(
                command, shell=True,
                capture_output=True, text=True, timeout=timeout,
                cwd=str(self._user_dir(user_id)),
                env=clean_env,
            )
            out = result.stdout
            if result.stderr:
                out += "\n[stderr]\n" + result.stderr
            max_out = get_setting_int("sandbox_output_max_chars", 5000)
            raw = out[:max_out] or "(no output)"
            return self._filter_sensitive_output(raw)
        except subprocess.TimeoutExpired:
            return "Execution timed out"

    def read_file(self, filename: str, user_id=None) -> str:
        try:
            path = self._ensure_in_sandbox(filename, user_id=user_id)
            return path.read_text(encoding="utf-8", errors="replace")[:5000]
        except Exception as e:
            return f"Error: {e}"

    def write_file(self, filename: str, content: str, user_id=None) -> str:
        try:
            if not filename or filename.strip() in (".", "..", "/", "\\"):
                # Auto-generate a filename from content preview
                ext = ".txt"
                preview = (content or "").strip()[:20].replace("\n", " ").strip()
                if preview:
                    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in preview).strip()
                    filename = safe_name + ext
                else:
                    filename = f"output_{uuid.uuid4().hex[:8]}{ext}"
            path = self._ensure_in_sandbox(filename, user_id=user_id)
            if path.is_dir():
                # Try appending a default filename
                path = path / f"output_{uuid.uuid4().hex[:8]}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Written: {filename}"
        except Exception as e:
            return f"Error: {e}"

    def list_files(self, subdir: str = ".", user_id=None) -> str:
        try:
            target = self._ensure_in_sandbox(subdir, user_id=user_id)
            items = []
            for p in sorted(target.iterdir()):
                prefix = "[DIR] " if p.is_dir() else "[FILE]"
                items.append(f"{prefix} {p.name}")
            return "\n".join(items) or "(empty)"
        except Exception as e:
            return f"Error: {e}"


class ToolRegistry:
    """Collects tool definitions and routes execution to the right executor."""

    def __init__(self, skills_dir: str, sandbox_dir: str):
        self.skills_dir = skills_dir
        self.sandbox_dir = sandbox_dir
        self.skill_exec = SkillExecutor(skills_dir)
        self.sandbox_exec = SandboxExecutor(sandbox_dir)

    def build_definitions(self, *, skill_names: list, mcp_tools: list,
                          api_endpoints: list, enable_sandbox: bool = True,
                          kb_collections: list = None) -> list:
        """Build OpenAI function-calling tool definitions."""
        tools = []

        # Skills — use cached _parse_skill_md to read SKILL.md only once per skill
        for name in skill_names:
            _parsed = _parse_skill_md(self.skills_dir, name)
            _desc = _parsed.get("description", "")
            _body = _parsed.get("body", "")
            _params = _parsed.get("params")
            
            desc = _desc or f"Execute the {name} skill"
            props = {
                "action": {"type": "string", "description": "操作: run=执行(默认), help=获取完整使用文档(SKILL.md)"},
            }
            required = []
            if _params:
                props.update(_params["props"])
                required = list(_params["required"])
            _needs_expression = "expression" in _body.lower() or not _params
            if _needs_expression:
                props["expression"] = {"type": "string", "description": "Main input"}
            if name == "kb_query" and kb_collections:
                props["collection_name"] = {
                    "type": "string",
                    "description": "知识库名称，可用选项: " + ", ".join(kb_collections),
                    "enum": kb_collections,
                }
            tools.append({
                "type": "function",
                "function": {
                    "name": f"skill__{name}",
                    "description": f"{desc}",
                    "parameters": {
                        "type": "object",
                        "properties": props,
                    },
                },
            })

        # MCP tools
        for mt in mcp_tools:
            if mt.get("endpoint"):
                transport = mt.get("transport", "sse")
                try:
                    if transport == "streamable_http":
                        sub_tools = MCPExecutor.list_tools_streamable_http(mt["endpoint"])
                    else:
                        sub_tools = MCPExecutor.list_tools_sse(mt["endpoint"])
                except Exception:
                    sub_tools = []
                if sub_tools:
                    for st in sub_tools:
                        schema = st.get("inputSchema", {"type": "object", "properties": {}, "required": []})
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": f"mcp__{mt['id']}__{st['name']}",
                                "description": f"[MCP: {mt['name']}] {st['description'][:200]}",
                                "parameters": schema,
                            },
                        })
                else:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": f"mcp__{mt['id']}",
                            "description": f"[MCP: {mt['name']}] {mt.get('description') or 'Call MCP tool ' + mt['name']}",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "tool_name": {"type": "string", "description": "Name of the MCP tool to call"},
                                    "arguments": {"type": "object", "description": "Arguments for the MCP tool"},
                                },
                                "required": ["tool_name"],
                            },
                        },
                    })
            elif mt.get("command"):
                tools.append({
                    "type": "function",
                    "function": {
                        "name": f"mcp__{mt['id']}",
                        "description": f"[MCP: {mt['name']}] {mt.get('description') or 'Call MCP tool ' + mt['name']}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "tool_name": {"type": "string", "description": "Name of the MCP tool to call"},
                                "arguments": {"type": "object", "description": "Arguments for the MCP tool"},
                            },
                            "required": ["tool_name"],
                        },
                    },
                })

        # API endpoints
        for ep in api_endpoints:
            tools.append({
                "type": "function",
                "function": {
                    "name": f"api__{ep['id']}",
                    "description": f"[API: {ep['name']}] Call {ep['method']} {ep['url'][:80]}. {ep.get('description') or ''}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "params": {"type": "object", "description": "Query or body parameters for the API call"},
                        },
                    },
                },
            })

        # Sandbox tools
        if enable_sandbox:
            tools.append({
                "type": "function",
                "function": {
                    "name": "sandbox_execute_python",
                    "description": "Execute Python code in a secure sandbox. Use for calculations, data processing, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python source code to execute"},
                        },
                        "required": ["code"],
                    },
                },
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "sandbox_read_file",
                    "description": "Read a file from the sandbox directory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Filename relative to sandbox root"},
                        },
                        "required": ["filename"],
                    },
                },
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "sandbox_write_file",
                    "description": "Write content to a file in the sandbox. Generate a descriptive filename based on the content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Descriptive filename based on content, e.g. 'meeting_notes.txt', 'report.md'. Include a relevant extension."},
                            "content": {"type": "string", "description": "File content to write"},
                        },
                        "required": ["filename", "content"],
                    },
                },
            })
            tools.append({
                "type": "function",
                "function": {
                    "name": "sandbox_list_files",
                    "description": "List files and directories in the sandbox.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subdir": {"type": "string", "description": "Subdirectory to list (default: root)"},
                        },
                    },
                },
            })

        return tools

    def execute(self, tool_name: str, arguments: dict,
                mcp_tools: list = None, api_endpoints: list = None,
                kb_collections: list = None,
                user_info: dict = None) -> str:
        """Route a tool call to the correct executor.

        Tool name convention:
          skill__<name>   -> SkillExecutor
          mcp__<id>       -> MCPExecutor
          api__<id>       -> APIExecutor
          sandbox_*       -> SandboxExecutor
        """
        args = arguments or {}
        mcp_tools = mcp_tools or []
        api_endpoints = api_endpoints or []

        # Skills
        if tool_name.startswith("skill__"):
            skill_name = tool_name[len("skill__"):]
            action = args.get("action", "run")
            skill_args = {k: v for k, v in args.items() if k != "action"}
            if skill_name == "kb_query" and kb_collections:
                skill_args["_allowed_collections"] = kb_collections
            if user_info:
                skill_args["_user_id"] = user_info.get("id")
                skill_args["_is_admin"] = user_info.get("is_admin", False)
                _flask_app = getattr(self, '_flask_app', None) or getattr(ToolRegistry, '_flask_app', None)
                if _flask_app:
                    skill_args['_flask_app'] = _flask_app
                if skill_name in ("memory_save", "memory_query"):
                    skill_args["user_id"] = user_info.get("id")
            # Pass user-specific sandbox directory so skills save files to sandbox/<user_id>/
            sandbox_dir = self.sandbox_dir
            if user_info and user_info.get("id"):
                sandbox_dir = os.path.join(self.sandbox_dir, str(user_info["id"]))
            return self.skill_exec.execute(skill_name, action, sandbox_dir=sandbox_dir, **skill_args)

        # MCP
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__", 2)
            mcp_id = int(parts[1])
            sub_tool_name = parts[2] if len(parts) > 2 else args.get("tool_name", "")
            cfg = next((t for t in mcp_tools if t["id"] == mcp_id), None)
            if not cfg:
                return f"Error: MCP tool id={mcp_id} not found"
            tool_args = args.get("arguments", {}) if sub_tool_name != parts[2] else args
            if cfg.get("endpoint"):
                transport = cfg.get("transport", "sse")
                if transport == "streamable_http":
                    return MCPExecutor.call_streamable_http_tool(
                        cfg["endpoint"],
                        tool_name=sub_tool_name,
                        tool_args=tool_args,
                    )
                return MCPExecutor.call_sse_tool(
                    cfg["endpoint"],
                    tool_name=sub_tool_name,
                    tool_args=tool_args,
                )
            elif cfg.get("command"):
                return MCPExecutor.call_stdio_tool(
                    cfg["command"],
                    args=cfg.get("args"),
                    env_vars=cfg.get("env_vars"),
                    tool_name=sub_tool_name,
                    tool_args=tool_args,
                )
            return "Error: MCP tool has no command or endpoint configured"

        # API
        if tool_name.startswith("api__"):
            api_id = int(tool_name[len("api__"):])
            cfg = next((e for e in api_endpoints if e["id"] == api_id), None)
            if not cfg:
                return f"Error: API endpoint id={api_id} not found"
            return APIExecutor.call(cfg, params=args.get("params"))

        # Sandbox
        uid = (user_info or {}).get("id")
        if tool_name == "sandbox_execute_python":
            return self.sandbox_exec.execute_python(args.get("code", ""), user_id=uid)
        if tool_name == "sandbox_execute_shell":
            return self.sandbox_exec.execute_shell(args.get("command", ""), user_id=uid)
        if tool_name == "sandbox_read_file":
            return self.sandbox_exec.read_file(args.get("filename", ""), user_id=uid)
        if tool_name == "sandbox_write_file":
            return self.sandbox_exec.write_file(
                args.get("filename", ""), args.get("content", ""), user_id=uid)
        if tool_name == "sandbox_list_files":
            return self.sandbox_exec.list_files(args.get("subdir", "."), user_id=uid)

        return f"Unknown tool: {tool_name}"
