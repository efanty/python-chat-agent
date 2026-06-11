"""gen_image Skill — 使用智谱 GLM-Image / CogView 模型生成图片。

自动下载到沙箱 sandbox/<user_id>/ 目录，返回可访问的 URL 用于在对话中展示。

Requires:
  ZHIPU_API_KEY      — 智谱 API Key (https://open.bigmodel.cn)
  ZHIPU_IMAGE_MODEL  — 模型编码，默认 cogview-3-flash
"""

import os
import re
import uuid
import json
import requests
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SANDBOX_DIR = _PROJECT_ROOT / "sandbox"

# ── API 配置 ──────────────────────────────────────────────────────────────

API_URL = "https://open.bigmodel.cn/api/paas/v4/images/generations"

# 尺寸别名表
SUPPORTED_SIZES = {
    "square": "1024x1024",
    "portrait": "768x1344",
    "landscape": "1344x768",
    "medium_portrait": "864x1152",
    "medium_landscape": "1152x864",
    "widescreen": "1440x720",
    "vertical": "720x1440",
}


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """从 prompt 中提取安全的 ASCII 文件名片段。"""
    text = text.strip()[:max_len]
    # 去除非 ASCII 字符，仅保留字母数字和常见符号
    text = re.sub(r"[^a-zA-Z0-9\- _]", "", text)
    text = re.sub(r"\s+", "_", text).strip("_")
    return text if text else "image"


def _get_sandbox_dir(user_id=None) -> Path:
    """获取当前用户的沙箱目录，自动创建。"""
    d = _SANDBOX_DIR / str(user_id or "0")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_image(image_url: str, prompt: str, user_id=None):
    """下载图片到沙箱 sandbox/<user_id>/，返回 (web_url, local_abs_path)。

    Returns:
        tuple: (web_url, local_abs_path)
            web_url — Flask 可访问的 URL（/chat/sandbox/xxx.png）
            local_abs_path — 文件在磁盘上的绝对路径（用于附件等操作）
    """
    # 从 URL 推断扩展名
    ext = ".png"
    for known_ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if known_ext in image_url.lower():
            ext = known_ext
            break

    name_tag = _sanitize_filename(prompt)
    filename = f"gen_{uuid.uuid4().hex[:8]}_{name_tag}{ext}"
    sandbox_dir = _get_sandbox_dir(user_id)
    local_path = sandbox_dir / filename

    resp = requests.get(image_url, timeout=60)
    resp.raise_for_status()
    local_path.write_bytes(resp.content)

    # 返回 Flask 可访问 URL + 本地绝对路径
    # URL 中包含用户ID，确保 sandbox_file 路由能正确找到文件
    user_id_str = str(user_id) if user_id else "0"
    web_url = f"/chat/sandbox/{user_id_str}/{filename}"
    local_abs = str(local_path.resolve())
    return web_url, local_abs


# ── 入口函数 ──────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    根据文本描述生成图片，下载到本地，返回 Markdown 格式结果
    （包含图片标签，LLM 可直接在回复中使用）。

    Args:
        expression: 图片描述文字（prompt），支持中文
        action:     预留
        **kwargs:
            prompt:   图片描述（与 expression 二选一）
            size:     图片尺寸或别名（如 "1024x1024"、"square"）
            quality:  "hd" 或 "standard"（默认 standard）
            watermark: 是否加水印（默认 true）

    Returns:
        Markdown 文本（包含图片标签），LLM 可直接在回复中展示。
    """
    # ── 解析 prompt ─────────────────────────────────────────────────────
    prompt = kwargs.get("prompt", "") or expression or ""
    if not prompt:
        return "错误：请提供图片描述（prompt）"

    # ── 解析尺寸 ─────────────────────────────────────────────────────────
    size = kwargs.get("size", "1024x1024")
    if size in SUPPORTED_SIZES:
        size = SUPPORTED_SIZES[size]

    # ── 解析其他参数 ─────────────────────────────────────────────────────
    quality = kwargs.get("quality", "standard")
    watermark = kwargs.get("watermark", kwargs.get("watermark_enabled", True))
    if isinstance(watermark, str):
        watermark = watermark.lower() in ("true", "1", "yes")

    # ── 获取 API Key 和模型 ─────────────────────────────────────────────
    api_key = os.getenv("ZHIPU_API_KEY", "")
    if not api_key:
        return "错误：ZHIPU_API_KEY 未设置，请在环境变量中配置"

    model = os.getenv("ZHIPU_IMAGE_MODEL", "cogview-3-flash")

    # ── 调用智谱 API 生成图片 ──────────────────────────────────────────
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "watermark_enabled": watermark,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return "错误：请求智谱 API 超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        return f"错误：API 请求失败 — {e}"
    except json.JSONDecodeError:
        return "错误：API 返回格式异常"

    image_list = data.get("data", [])
    if not image_list:
        return "错误：API 未返回图片数据"

    image_url = image_list[0].get("url", "")
    if not image_url:
        return "错误：API 返回的图片 URL 为空"

    # ── 检查内容安全 ─────────────────────────────────────────────────────
    content_filter = data.get("content_filter", [])
    filter_warnings = []
    for f in content_filter:
        level = f.get("level", 0)
        if level <= 1:
            filter_warnings.append(f"内容安全提醒: {f.get('role', 'unknown')} (等级 {level})")

    # ── 下载到沙箱 ─────────────────────────────────────────────────────
    user_id = kwargs.get("_user_id")
    try:
        file_url, local_path = _download_image(image_url, prompt, user_id)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"图片下载失败: {e}",
            "remote_url": image_url,
        }, ensure_ascii=False)

    result = {
        "success": True,
        "file_url": file_url,
        "local_path": local_path,
        "model": model,
        "size": size,
    }
    if filter_warnings:
        result["warnings"] = filter_warnings

    return json.dumps(result, ensure_ascii=False)
