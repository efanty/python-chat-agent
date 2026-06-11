"""save_note Skill — 保存内容到笔记系统。

工作流程：
1. 将智能体生成或获取的内容，或用户提供的内容（标题 + 正文）通过 POST 发送到笔记系统API进行保存
2. 获取笔记系统API返回的内容，抓取笔记页面并展示 Markdown 内容
"""

import os
import json
import importlib.util
import sys
import requests
from pathlib import Path


# Resolve project root (3 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

# Load .env manually if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

# ── 入口函数 ────────────────────────────────────────────────────

def run(expression: str = "", title: str = "", content: str = "", **kwargs) -> str:
    """发送内容到笔记系统保存为笔记。

    保存自定义内容：
        run(title="我的笔记", content="这是笔记正文")
        → 发送自定义标题和正文

    Args:
        expression: 兼容参数，可留空
        title: 笔记标题（必须）
        content: 笔记正文（必须）
        **kwargs: 其他参数，可留空

    Returns:
        执行结果描述
    """
    # ── 解析参数 ─────────────────────────────────────────────

    note_title = title or kwargs.get("title", "")
    note_content = content or kwargs.get("content", "")


    # ── 发送到笔记系统 Webhook ──────────────────────────────
    note_api_url = os.environ.get("NOTE_API_URL", "")
    note_api_key = os.environ.get("NOTE_API_KEY", "")

    if not note_api_url:
        return "❌ 配置错误：未设置 NOTE_API_URL。请在 .env 文件中配置。"
    if not note_api_key:
        return "❌ 配置错误：未设置 NOTE_API_KEY。请在 .env 文件中配置。"
    if note_api_key == "your-api-key-here":
        return "❌ 配置错误：NOTE_API_KEY 使用默认占位值，请在 .env 文件中填入实际的 API Key。"

    payload = {
        "title": note_title,
        "content": note_content,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": note_api_key,
    }

    try:
        resp = requests.post(note_api_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return "⏰ 请求超时：笔记系统API超过 30 秒未响应"
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        try:
            err_body = e.response.json()
            err_detail = json.dumps(err_body, ensure_ascii=False)
        except Exception:
            err_detail = e.response.text[:500]
        return f"❌ 发送失败（HTTP {status}）：{err_detail}"
    except requests.exceptions.ConnectionError:
        return f"🔌 连接失败：无法连接到笔记系统（{note_api_url}）"
    except Exception as e:
        return f"❌ 发送异常：{e}"

    # ── 解析 笔记系统 响应 ───────────────────────────────────
    note_url = ""
    try:
        resp_data = resp.json()
        resp_items = resp_data.get("response", [])
        if resp_items and isinstance(resp_items, list) and len(resp_items) > 0:
            note_url = resp_items[0].get("url", "")
        resp_summary = json.dumps(resp_data, ensure_ascii=False, indent=2)
    except Exception:
        resp_summary = resp.text[:2000] if resp.text else "(无响应内容)"


    parts = [
        "✅ **笔记已保存成功！**",
        f"📄 **标题**: {note_title}",
    ]

    if note_url:
        parts.append(f"📎 **笔记链接**: [{note_url}]({note_url})")

    parts.append(f"\n📥 **笔记系统API响应**:\n{resp_summary}")
    return "\n".join(parts)
