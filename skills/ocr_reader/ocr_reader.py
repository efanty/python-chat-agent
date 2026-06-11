"""OCR reader skill — recognize text and content from images using Zhipu GLM-4V.

Uses the same API approach as test_ocr_standalone.py, wrapped in the
standard skill interface (run/ocr/describe) for SkillExecutor integration.

Requires: ZHIPU_API_KEY environment variable from https://open.bigmodel.cn
"""

import os
import json
import base64
import requests
from pathlib import Path
from app.utils.settings import get_setting_int


# Resolve project root (3 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

# Load .env manually if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)
except ImportError:
    pass

# ── Constants ────────────────────────────────────────────────────────────

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = os.getenv("ZHIPU_VISION_MODEL", "glm-4v-flash")
FALLBACK_MODELS = ["glm-4v-plus", "glm-5v-turbo"]
_OCR_MAX_CHARS = 30000  # fallback constant
def _get_ocr_max_chars():
    return get_setting_int("ocr_max_chars", _OCR_MAX_CHARS)
MAX_CHARS = _get_ocr_max_chars

# Aliases for test_skill.py compatibility
ZHIPU_CHAT_URL = API_URL

# Supported image extensions and their MIME types
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


# ── Core Logic ───────────────────────────────────────────────────────────

def _encode_image(img_path: Path) -> tuple[str, str]:
    """Read and base64-encode an image file.

    Returns:
        (mime_type, data_url)  — or raises on failure.
    """
    raw = img_path.read_bytes()
    ext = img_path.suffix.lower()
    mime = MIME_MAP.get(ext, "image/jpeg")
    b64 = base64.b64encode(raw).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"
    return mime, data_url


def _call_zhipu(data_url: str, prompt: str, model: str = DEFAULT_MODEL,
                api_key: str = "") -> tuple[bool, str, str]:
    """Call Zhipu GLM-4V vision API.  Tries the given model first,
    then falls back through FALLBACK_MODELS.

    Returns:
        (success, content_or_error, model_used)
    """
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    last_error = ""

    for attempt_model in models_to_try:
        payload = {
            "model": attempt_model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            resp = requests.post(API_URL, headers=headers,
                                 json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "")
                    _mc = _get_ocr_max_chars()
                    if len(text) > _mc:
                        text = text[: _mc] + "\n\n*（内容已截断）*"
                    return True, text, attempt_model
                last_error = "API 返回了空的 choices"
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.exceptions.Timeout:
            last_error = "请求超时"
        except requests.exceptions.RequestException as e:
            last_error = f"请求失败: {e}"
        except Exception as e:
            last_error = f"解析错误: {e}"

    return False, last_error, model


def _resolve_path(file_path: str, sandbox_dir: str = None) -> Path:
    """Resolve a possibly-relative file path against the project root or sandbox."""
    p = Path(file_path)
    if p.is_absolute():
        return p
    if sandbox_dir:
        return Path(sandbox_dir) / file_path
    # Relative to project root (three levels up from skills/<name>/<file>.py)
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / file_path


# ── Entry point called by SkillExecutor ──────────────────────────────────

def run(expression: str = "", action: str = "", file_path: str = "",
        path: str = "", prompt: str = "", model: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Accepts parameters in three styles:
      1. Keyword args:  run(file_path="/img.png", action="ocr")
      2. JSON string:   run('{"action":"ocr","file_path":"/img.png"}')
      3. Plain path:    run("/img.png")

    Args:
        expression: file path or JSON blob with params
        action:     "ocr" (default) — extract text
                    "describe" — describe the whole scene
        file_path:  path to the image file (absolute or project-relative)
        path:       alias for file_path
        prompt:     custom instruction sent to the vision model
        model:      GLM vision model name (default: glm-4v-flash)

    Returns:
        JSON string with keys: success, content/file_name/error, model_used
    """
    # ── Parse from JSON expression ──────────────────────────────────
    if expression and expression.strip().startswith("{"):
        try:
            args = json.loads(expression)
            action = args.get("action", action)
            file_path = args.get("file_path", args.get("path", file_path))
            prompt = args.get("prompt", prompt)
            model = args.get("model", model)
        except json.JSONDecodeError:
            if not file_path:
                file_path = expression

    # ── Resolve parameters ──────────────────────────────────────────
    file_path = file_path or path or kwargs.get("file_path", "") or expression
    action = action or "ocr"
    prompt = prompt or ""
    model = model or DEFAULT_MODEL
    sandbox_dir = kwargs.get("sandbox_dir")

    if not file_path or file_path.startswith("{"):
        return json.dumps({
            "success": False,
            "error": "请提供图片文件路径。用法: run(file_path='/path/to/image.jpg')",
        }, ensure_ascii=False)

    # ── Resolve and validate path ───────────────────────────────────
    img_path = _resolve_path(file_path, sandbox_dir)
    if not img_path.exists():
        return json.dumps({
            "success": False,
            "error": f"文件不存在: {file_path}",
        }, ensure_ascii=False)

    ext = img_path.suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return json.dumps({
            "success": False,
            "error": f"不支持的图片格式: {ext}，支持: {', '.join(sorted(IMAGE_EXTENSIONS))}",
        }, ensure_ascii=False)

    # ── Check API key ───────────────────────────────────────────────
    api_key = os.getenv("ZHIPU_API_KEY", "")
    if not api_key:
        return json.dumps({
            "success": False,
            "error": "ZHIPU_API_KEY 未设置。请从 https://open.bigmodel.cn 获取 API Key。",
        }, ensure_ascii=False)

    # ── Encode image ────────────────────────────────────────────────
    try:
        mime, data_url = _encode_image(img_path)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"图片读取失败: {e}",
        }, ensure_ascii=False)

    # ── Build prompt ────────────────────────────────────────────────
    if not prompt:
        if action == "describe":
            prompt = (
                "请详细描述这张图片的内容，包括布局、颜色、文字、图表、"
                "人物等。以 Markdown 格式输出。"
            )
        else:
            prompt = (
                "请识别此图片中的所有文字内容，以 Markdown 格式输出。"
                "如果包含表格，请用表格格式呈现；如果包含代码，请用代码块呈现。"
            )

    # ── Call Zhipu API (with fallback chain) ────────────────────────
    success, content_or_error, model_used = _call_zhipu(
        data_url, prompt, model, api_key
    )

    if not success:
        return json.dumps({
            "success": False,
            "error": f"识别失败: {content_or_error}",
        }, ensure_ascii=False)

    img_size = img_path.stat().st_size
    return json.dumps({
        "success": True,
        "file_name": img_path.name,
        "file_size": img_size,
        "mime": mime,
        "model_used": model_used,
        "content": content_or_error,
    }, ensure_ascii=False)


# ── Action aliases for SkillExecutor ─────────────────────────────────────
# The executor tries getattr(mod, action) before falling back to run().
ocr = run
describe = run
