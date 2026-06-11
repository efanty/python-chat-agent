import os
import json
import re
import requests
from typing import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from .tools import ToolRegistry
from app.utils.llm_utils import resolve_api_key
from app.utils.settings import get_setting as _get_setting

# ── Module-level Flask app for thread-safe DB access from skills ──
_FLASK_APP_GLOBAL = None

# ── Constants ──────────────────────────────────────────────────────────────
_MEMORY_TYPE_LABELS = {
    "preference": "偏好", "fact": "事实", "habit": "习惯",
    "context": "上下文", "general": "通用",
}

_DEFAULT_SYSTEM_PROMPT = (
    "You are DeepAgent, a helpful AI assistant. "
    "Use available tools when helpful. "
    "Respond in the same language as the user. Be concise.\n\n"
    "## File handling\n"
    "When a user uploads a file, the file path is included in the message. "
    "Use the appropriate skill to read it:\n"
    "- PDF files → use skill__pdf_reader with file_path parameter\n"
    "- Image files (PNG/JPG/GIF/BMP) → use skill__ocr_reader with file_path parameter\n"
    "- Excel files (.xlsx) → use skill__xlsx with action='read' and file_path parameter\n"
    "- Word files (.docx) → use skill__docx with action='read' and file_path parameter\n"
    "- PowerPoint files (.pptx) → use skill__pptx with action='read' and file_path parameter\n"
    "- Text/code files → content is already included inline, read it directly\n\n"
    "## File creation and download\n"
    "When you create files using sandbox_write_file or sandbox_execute_python, "
    "you can provide the user with a download link using the following format:\n"
    "- Download link format: `/chat/sandbox/<文件名>` (注意完整路径包含 /chat/ 前缀)\n"
    '- Example Markdown: `[Download Report](/chat/sandbox/report.txt)`\n'
    "The sandbox is user-isolated, so only the current user can access their files.\n"
    "Script files (.py) cannot be downloaded, and all files are served as downloadable attachments.\n"
    "⚠️ 绝对禁止：不要启动任何 HTTP 服务器（http.server/Flask/uvicorn/等）。\n"
    "如果你需要提供文件下载，用 sandbox_write_file 创建文件后告知用户访问 /chat/sandbox/<文件名> 即可。\n"
    "系统中已有内置的文件下载路由，不需要也不允许自己启动服务器。"
)


def get_flask_app():
    """Return the Flask app instance set during AgentService.init_app()."""
    return _FLASK_APP_GLOBAL




def _sanitize_user_input(text: str) -> str:
    """Sanitize user-controlled strings before injecting into system prompt.
    
    Removes or replaces characters that could be used for prompt injection:
    - Strips leading/trailing whitespace
    - Replaces newlines with spaces to prevent breaking the prompt structure
    - Removes Markdown heading markers
    - Limits length
    """
    if not text:
        return ""
    # Remove leading/trailing whitespace
    text = text.strip()
    # Replace newlines with spaces
    text = text.replace("\n", " ").replace("\r", " ")
    # Remove markdown heading markers that could hijack prompt structure
    text = re.sub(r"#{1,6}\s+", "", text)
    # Remove code block markers
    text = text.replace("```", "")
    # Limit length
    return text[:200]


# Module-level cache for ChromaRAG clients (keyed by persist_dir)
_chroma_instances = {}


class ChromaRAG:
    """ChromaDB-backed RAG retriever.

    Supports both local PersistentClient and remote HttpClient
    (configured via CHROMA_HOST / CHROMA_PORT env vars).

    Uses a module-level cache to avoid creating multiple clients
    for the same persist directory within a process.
    """

    def __new__(cls, persist_dir: str = None):
        key = persist_dir or "chroma_data"
        if key not in _chroma_instances:
            instance = super().__new__(cls)
            instance.persist_dir = key
            instance._client = None
            _chroma_instances[key] = instance
        return _chroma_instances[key]

    def __init__(self, persist_dir: str = None):
        # __init__ is called after __new__, but we only want to init once
        if not hasattr(self, '_initialized'):
            self.persist_dir = persist_dir or "chroma_data"
            self._client = None
            self._initialized = True

    @staticmethod
    def _create_client(persist_dir: str = None):
        """Create a ChromaDB client — local PersistentClient or remote HttpClient.

        Environment variables to configure remote ChromaDB:
          CHROMA_HOST        — remote host (e.g. "192.168.1.100")
          CHROMA_PORT        — remote port (default 8000)
          CHROMA_SSL         — "true" for HTTPS (default false)
          CHROMA_HEADERS     — optional JSON headers for auth
        If CHROMA_HOST is not set, falls back to local PersistentClient.
        """
        import chromadb
        host = os.getenv("CHROMA_HOST")
        if host:
            port = int(os.getenv("CHROMA_PORT", "8000"))
            ssl = os.getenv("CHROMA_SSL", "false").lower() in ("true", "1")
            headers_raw = os.getenv("CHROMA_HEADERS", "")
            headers = {}
            if headers_raw:
                try:
                    headers = json.loads(headers_raw)
                except json.JSONDecodeError:
                    pass
            return chromadb.HttpClient(
                host=host, port=port, ssl=ssl, headers=headers,
            )
        return chromadb.PersistentClient(path=persist_dir or "chroma_data")

    @property
    def client(self):
        if self._client is None:
            try:
                self._client = self._create_client(self.persist_dir)
            except ImportError:
                self._client = False
        return self._client

    def query(self, collection_name: str, query_text: str, n_results: int = 3) -> list:
        if not self.client:
            return []
        try:
            collection = self.client.get_or_create_collection(collection_name)
            results = collection.query(query_texts=[query_text], n_results=n_results)
            return results.get("documents", [[]])[0]
        except Exception:
            return []


# ── AgentService ─────────────────────────────────────────────────────────

class AgentService:
    """Service layer — prompt building, tool calling, LLM streaming.

    Yields dict events from chat_stream:
      {"type": "chunk", "content": "..."}
      {"type": "tool_call", "name": "...", "args": {...}}
      {"type": "tool_result", "name": "...", "result": "..."}
      {"type": "done"}
    """

    MAX_TOOL_ROUNDS = 25  # default fallback
    _system_prompt_cache = {}  # cache_key -> system_prompt string
    _SYSTEM_PROMPT_CACHE_MAX = 256  # max entries to prevent memory leak

    def __init__(self, app=None):
        self.sandbox_dir = "sandbox"
        self.skills_dir = "skills"
        self.chroma_dir = "chroma_data"
        self._registry = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.sandbox_dir = app.config.get("SANDBOX_DIR", "sandbox")
        self.skills_dir = app.config.get("SKILLS_DIR", "skills")
        self.chroma_dir = app.config.get("CHROMA_PERSIST_DIR", "chroma_data")
        self._registry = ToolRegistry(self.skills_dir, self.sandbox_dir)
        self._registry._flask_app = app
        ToolRegistry._flask_app = app
        global _FLASK_APP_GLOBAL
        _FLASK_APP_GLOBAL = app

    def _get_setting(self, key: str, default=None):
        """Read a runtime setting; fallback if DB unavailable."""
        return _get_setting(key, default)

    def _get_max_tool_rounds(self) -> int:
        """Read max_tool_rounds from admin settings live (no restart needed)."""
        try:
            from app.models.settings import Setting
            val = Setting.get("max_tool_rounds")
            if val:
                return int(val)
        except Exception:
            pass
        return self.MAX_TOOL_ROUNDS

    @property
    def registry(self):
        if self._registry is None:
            self._registry = ToolRegistry(self.skills_dir, self.sandbox_dir)
        return self._registry

    # ── public API ────────────────────────────────────────────────────

    def chat_stream(self, *, user_info: dict, model_info: dict, agent_info: dict,
                    history: list, message: str, file_path: str = None,
                    file_paths: list = None,
                    mcp_tools: list = None, api_endpoints: list = None) -> Generator:
        """Main entry point — yields event dicts for SSE streaming."""
        system_prompt = self._build_system_prompt(user_info, agent_info, message)
        messages = self._build_messages(system_prompt, history, message, file_path, file_paths)
        tools = self._build_tools(agent_info, mcp_tools or [], api_endpoints or [])

        kb_collections = agent_info.get("kb_collections", [])
        yield from self._agent_loop(
            model_info=model_info,
            messages=messages,
            tools=tools,
            mcp_tools=mcp_tools or [],
            api_endpoints=api_endpoints or [],
            kb_collections=kb_collections,
            user_info=user_info,
        )

    # ── prompt / messages ──────────────────────────────────────────────

    def _get_user_memories(self, user_info: dict) -> str:
        """查询用户的长期记忆，返回格式化的记忆文本。"""
        if not user_info or not user_info.get("id"):
            return ""
        try:
            from app.models.memory import UserMemory
            mem_limit = int(self._get_setting("user_memory_limit", 30))
            memories = UserMemory.query.filter_by(user_id=user_info["id"]).order_by(
                UserMemory.updated_at.desc()).limit(mem_limit).all()
            if not memories:
                return ""
            lines = []
            for m in memories:
                lines.append(f"  [{_MEMORY_TYPE_LABELS.get(m.memory_type, '通用')}] {m.key}: {m.value}")
            return "## User Memories\n" + "\n".join(lines)
        except Exception:
            return ""

    def _build_system_prompt(self, user_info: dict, agent_info: dict, message: str) -> str:
        # Cache hit: same user + same agent + same KBs -> reuse
        uid = str(user_info.get("id", ""))
        agent_sp = agent_info.get("system_prompt", "") or ""
        kbs = str(sorted(agent_info.get("kb_collections", [])))
        skills = str(sorted(agent_info.get("skill_names", [])))
        cache_key = uid + "|" + agent_sp + "|" + kbs + "|" + skills
        cached = self._system_prompt_cache.get(cache_key)
        if cached is not None:
            return cached
        parts = []
        prompt = agent_info.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT
        parts.append(prompt)

        # RAG context — inform LLM about available KBs, query on demand via kb_query skill
        kb_collections = agent_info.get("kb_collections", [])
        if kb_collections:
            kbs_str = ", ".join(kb_collections)
            parts.append(
                f"\n\n## Available Knowledge Bases\n"
                f"You have access to the following knowledge bases: {kbs_str}.\n"
                f"Use the `kb_query` skill with the appropriate `collection_name` "
                f"when you need to look up information from these knowledge bases. "
                f"Do not guess the content — query it explicitly."
            )

        # User memories
        memories_text = self._get_user_memories(user_info)
        if memories_text:
            parts.append("\n\n" + memories_text)

        # User context (sanitize all user-controlled fields against prompt injection)
        _sanitize = _sanitize_user_input
        nickname = _sanitize(user_info.get('nickname')) or _sanitize(user_info.get('username')) or '?'
        username = _sanitize(user_info.get('username')) or '?'
        email = _sanitize(user_info.get('email')) or '?'
        parts.append(
            f"\n\n## Current User\n"
            f"Nickname: {nickname}, "
            f"Username: {username}, "
            f"Role: {_sanitize(user_info.get('role', 'user'))}, "
            f"Email: {email}, "
            f"Email verified: {user_info.get('email_verified', False)}, "
            f"TOTP enabled: {user_info.get('totp_enabled', False)}, "
            f"Registered at: {_sanitize(str(user_info.get('created_at', '?')))}, "
            f"ID: {_sanitize(str(user_info.get('id', '?')))}"
        )
        result = "\n".join(parts)
        # LRU eviction: remove oldest entry if cache exceeds max size
        if len(self._system_prompt_cache) >= self._SYSTEM_PROMPT_CACHE_MAX:
            try:
                # Remove the first (oldest) inserted key
                self._system_prompt_cache.pop(next(iter(self._system_prompt_cache)))
            except (StopIteration, KeyError):
                pass
        self._system_prompt_cache[cache_key] = result
        return result

    # ── File type → skill mapping for _build_messages ──────────────
    _FILE_SKILL_MAP = {
        # (extensions): (skill_name, action, file_type_label)
        ".pdf":   ("pdf_reader", "extract", "PDF"),
        ".png":   ("ocr_reader", "ocr", "图片"),
        ".jpg":   ("ocr_reader", "ocr", "图片"),
        ".jpeg":  ("ocr_reader", "ocr", "图片"),
        ".gif":   ("ocr_reader", "ocr", "图片"),
        ".webp":  ("ocr_reader", "ocr", "图片"),
        ".bmp":   ("ocr_reader", "ocr", "图片"),
        ".xlsx":  ("xlsx", "read", "Excel"),
        ".xlsm":  ("xlsx", "read", "Excel"),
        ".docx":  ("docx", "read", "Word"),
        ".pptx":  ("pptx", "read", "PowerPoint"),
    }

    _TEXT_EXTENSIONS = frozenset({
        ".txt", ".py", ".js", ".json", ".csv", ".md", ".html",
        ".css", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".log",
        ".sh", ".bat", ".sql",
    })

    def _build_messages(self, system_prompt: str, history: list,
                        message: str, file_path: str = None,
                        file_paths: list = None) -> list:
        msgs = [{"role": "system", "content": system_prompt}]
        limit = int(self._get_setting("history_message_limit", 20))
        for h in history[-limit:]:
            msgs.append({"role": h["role"], "content": h.get("content", "")})

        content = message

        # 收集所有需要处理的文件路径
        all_file_paths = []
        if file_paths:
            all_file_paths = file_paths
        elif file_path:
            all_file_paths = [file_path]

        if all_file_paths:
            file_parts = []
            for fp in all_file_paths:
                # 将相对路径转为绝对路径，确保文件存在性检查在任何工作目录下都能正常工作
                abs_fp = os.path.abspath(fp)
                if not os.path.exists(abs_fp):
                    continue

                ext = os.path.splitext(abs_fp)[1].lower()
                basename = os.path.basename(abs_fp)
                # 将路径中的反斜杠替换为正斜杠，避免 JSON 字符串中的转义问题
                safe_fp = fp.replace("\\", "/") if fp else fp

                # Text files — embed content inline
                if ext in self._TEXT_EXTENSIONS:
                    try:
                        with open(abs_fp, "r", encoding="utf-8", errors="replace") as f:
                            max_chars = int(self._get_setting("file_inline_max_chars", 5000))
                            fc = f.read()[:max_chars]
                        file_parts.append(
                            f"[用户上传了文件: {basename}]\n"
                            f"```\n{fc}\n```"
                        )
                    except Exception:
                        file_parts.append(
                            f"[用户上传了文件: {basename}，"
                            f"文件路径: {safe_fp}，但无法读取文本内容]"
                        )
                # Known binary file types — use skill mapping
                elif ext in self._FILE_SKILL_MAP:
                    skill_name, action, label = self._FILE_SKILL_MAP[ext]
                    file_parts.append(
                        f"[用户上传了 {label} 文件: {basename}]\n"
                        f"文件路径: {safe_fp}\n\n"
                        f"请使用 {skill_name} skill 读取此 {label} 文件的内容。\n"
                        f"调用方式: skill__{skill_name}，参数: {{\"action\": \"{action}\", \"file_path\": \"{safe_fp}\"}}"
                    )
                # Other binary files
                else:
                    file_parts.append(
                        f"[用户上传了文件: {basename}]\n"
                        f"文件路径: {safe_fp}，文件类型: {ext}"
                    )

            if file_parts:
                content = "\n\n".join(file_parts) + f"\n\n用户消息: {message}"

        msgs.append({"role": "user", "content": content})
        return msgs

    def _build_tools(self, agent_info: dict, mcp_tools: list,
                     api_endpoints: list) -> list:
        skill_names = agent_info.get("skill_names", [])
        enable_sandbox = agent_info.get("enable_sandbox", True)
        kb_collections = agent_info.get("kb_collections", [])
        return self.registry.build_definitions(
            skill_names=skill_names,
            mcp_tools=mcp_tools,
            api_endpoints=api_endpoints,
            enable_sandbox=enable_sandbox,
            kb_collections=kb_collections,
        )

    # ── agent loop ─────────────────────────────────────────────────────

    def _agent_loop(self, *, model_info, messages, tools, mcp_tools, api_endpoints,
                    _round: int = 0, _total_usage: dict = None,
                    kb_collections: list = None,
                    user_info: dict = None) -> Generator:
        if _total_usage is None:
            _total_usage = {"input_tokens": 0, "output_tokens": 0}
        # Read settings once per round to reduce DB queries
        _tool_result_max_chars = int(self._get_setting("tool_result_max_chars", 2000))
        if _round >= self._get_max_tool_rounds():
            yield {"type": "chunk", "content": "\n\n[已达到最大工具调用轮次]"}
            yield {"type": "done", "usage": _total_usage, "model_id": model_info.get("model_id", "") if model_info else ""}
            return

        if not model_info or not model_info.get("is_active"):
            yield from self._fallback_stream(messages[-1]["content"] if messages else "")
            yield {"type": "done", "usage": _total_usage, "model_id": model_info.get("model_id", "") if model_info else ""}
            return

        api_key = resolve_api_key(model_info)
        if not api_key:
            yield from self._fallback_stream(messages[-1]["content"] if messages else "")
            yield {"type": "done", "usage": _total_usage, "model_id": model_info.get("model_id", "") if model_info else ""}
            return

        # Call LLM — accumulate full response + detect tool calls
        content_chunks = []
        tool_calls = {}  # index → {name, arguments}
        round_usage = {"input_tokens": 0, "output_tokens": 0}

        try:
            for event in self._call_llm_with_tools(model_info, messages, tools, api_key):
                if event["type"] == "chunk":
                    content_chunks.append(event["content"])
                    yield event
                elif event["type"] == "tool_call":
                    idx = event["index"]
                    if idx not in tool_calls:
                        tool_calls[idx] = {"name": "", "arguments": ""}
                    if event.get("name"):
                        tool_calls[idx]["name"] += event["name"]
                    if event.get("arguments"):
                        tool_calls[idx]["arguments"] += event["arguments"]
                elif event["type"] == "usage":
                    round_usage = event
                    _total_usage["input_tokens"] += event.get("input_tokens", 0)
                    _total_usage["output_tokens"] += event.get("output_tokens", 0)
                elif event["type"] == "done":
                    pass
        except Exception as e:
            yield {"type": "chunk", "content": f"\n\n[LLM调用错误: {e}]"}
            yield {"type": "done", "usage": _total_usage, "model_id": model_info.get("model_id", "") if model_info else ""}
            return

        if tool_calls:
            tc_list = []
            tool_results = {}
            # Phase 1: yield all tool_call events immediately
            for idx in sorted(tool_calls.keys()):
                tc = tool_calls[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"].strip() else {}
                except json.JSONDecodeError:
                    args = {}
                tc_id = f"call_{_round}_{idx}"
                tc_list.append({
                    "id": tc_id,
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": json.dumps(args)},
                })
                yield {"type": "tool_call", "name": tc["name"], "args": args}

            # Phase 2: execute independent tool calls in parallel
            with ThreadPoolExecutor(max_workers=min(len(tc_list), 5)) as pool:
                fut_map = {}
                for tc_entry in tc_list:
                    name = tc_entry["function"]["name"]
                    tc_args = json.loads(tc_entry["function"]["arguments"])
                    fut = pool.submit(
                        self.registry.execute, name, tc_args,
                        mcp_tools=mcp_tools, api_endpoints=api_endpoints,
                        kb_collections=kb_collections, user_info=user_info,
                    )
                    fut_map[fut] = (tc_entry["id"], name)
                for fut in as_completed(fut_map):
                    tc_id, name = fut_map[fut]
                    try:
                        tool_results[tc_id] = fut.result()
                    except Exception as e:
                        tool_results[tc_id] = f"Tool error: {e}"

            # Phase 3: yield tool_result events in original call order
            for tc_entry in tc_list:
                tc_id = tc_entry["id"]
                name = tc_entry["function"]["name"]
                result = tool_results.get(tc_id, "(no result)")
                yield {"type": "tool_result", "name": name, "result": result[:_tool_result_max_chars]}

            full_content = "".join(content_chunks)
            assistant_msg = {"role": "assistant", "content": full_content or None}
            if tc_list:
                assistant_msg["tool_calls"] = tc_list
            messages.append(assistant_msg)

            for tc in tc_list:
                result_text = tool_results[tc["id"]]
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text[:_tool_result_max_chars],
                })

            yield from self._agent_loop(
                model_info=model_info,
                messages=messages,
                tools=tools,
                mcp_tools=mcp_tools,
                api_endpoints=api_endpoints,
                _round=_round + 1,
                _total_usage=_total_usage,
                kb_collections=kb_collections,
                user_info=user_info,
            )
        else:
            yield {"type": "done", "usage": _total_usage, "model_id": model_info.get("model_id", "") if model_info else ""}

    # ── LLM calling with tool support ──────────────────────────────────

    def _call_llm_with_tools(self, model_info: dict, messages: list,
                             tools: list, api_key: str) -> Generator:
        """Call LLM with streaming + function calling support."""
        try:
            yield from self._openai_tool_stream(model_info, messages, tools, api_key)
        except Exception:
            try:
                yield from self._requests_tool_stream(model_info, messages, tools, api_key)
            except Exception as e:
                yield {"type": "chunk", "content": f"\n\n[调用错误: {e}]"}
                yield {"type": "done"}

    def _openai_tool_stream(self, model_info, messages, tools, api_key) -> Generator:
        client = OpenAI(api_key=api_key, base_url=model_info.get("api_base") or None)

        _max_tokens = int(self._get_setting("llm_max_tokens", 4096))
        _temperature = float(self._get_setting("llm_temperature", 0.7))
        kwargs = {
            "model": model_info["model_id"],
            "messages": messages,
            "max_tokens": min(model_info.get("max_tokens", _max_tokens), 4096),
            "temperature": _temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = client.chat.completions.create(**kwargs)

        tool_call_buffers = {}
        usage_info = None

        for chunk in stream:
            # Capture usage from final chunk (choices empty, usage populated)
            if chunk.usage:
                usage_info = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                }
                continue

            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                yield {"type": "chunk", "content": delta.content}

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"name": "", "arguments": ""}
                    if tc.function:
                        if tc.function.name:
                            tool_call_buffers[idx]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_call_buffers[idx]["arguments"] += tc.function.arguments

            if chunk.choices[0].finish_reason:
                break

        if tool_call_buffers:
            for idx, buf in tool_call_buffers.items():
                yield {
                    "type": "tool_call",
                    "index": idx,
                    "name": buf["name"],
                    "arguments": buf["arguments"],
                }

        if usage_info:
            yield {"type": "usage", **usage_info}
        yield {"type": "done"}

    def _requests_tool_stream(self, model_info, messages, tools, api_key) -> Generator:
        base = model_info.get("api_base") or "https://api.openai.com/v1"
        url = f"{base.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        _max_tokens = int(self._get_setting("llm_max_tokens", 4096))
        _temperature = float(self._get_setting("llm_temperature", 0.7))
        body = {
            "model": model_info["model_id"],
            "messages": messages,
            "max_tokens": min(model_info.get("max_tokens", _max_tokens), 4096),
            "temperature": _temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        response = requests.post(url, headers=headers, json=body, stream=True, timeout=120)
        response.raise_for_status()

        tool_call_buffers = {}

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                data = json.loads(line[6:])
                delta = data.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    yield {"type": "chunk", "content": delta["content"]}
                if delta.get("tool_calls"):
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {"name": "", "arguments": ""}
                        func = tc.get("function", {})
                        if func.get("name"):
                            tool_call_buffers[idx]["name"] += func["name"]
                        if func.get("arguments"):
                            tool_call_buffers[idx]["arguments"] += func["arguments"]
                if data.get("choices", [{}])[0].get("finish_reason"):
                    break
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

        if tool_call_buffers:
            for idx, buf in tool_call_buffers.items():
                yield {
                    "type": "tool_call",
                    "index": idx,
                    "name": buf["name"],
                    "arguments": buf["arguments"],
                }

        yield {"type": "done"}

    # ── helpers ───────────────────────────────────────────────────────

    def _fallback_stream(self, user_msg: str) -> Generator:
        preview_chars = int(self._get_setting("fallback_msg_preview_chars", 100))
        response = (
            f"收到您的消息：「{user_msg[:preview_chars]}」\n\n"
            "⚠️ 当前 AI 服务未配置。请管理员在后台添加 LLM 模型配置。"
        )
        for i in range(0, len(response), 3):
            yield {"type": "chunk", "content": response[i:i + 3]}
