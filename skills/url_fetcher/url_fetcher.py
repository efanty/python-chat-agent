"""url_fetcher Skill — 获取 URL 内容并转换为 Markdown 格式。

使用 requests 获取网页，BeautifulSoup 解析 HTML 并转换为 Markdown。
适用于 LLM 读取网页内容进行分析的场景。
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from urllib.parse import urljoin
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


# ── 默认请求头（可被 run() 参数覆盖）──
_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ── 默认 Cookie（从环境变量 BAIDU_COOKIE 读取，也可在 run() 中传参覆盖）──
_DEFAULT_COOKIE = os.environ.get("BAIDU_COOKIE", "")


def run(expression: str = "", url: str = "", **kwargs) -> str:
    """获取网址内容并以 Markdown 格式返回。

    Args:
        expression: 网址（兼容用法）
        url: 要获取的网址
        max_chars: 最大返回字符数，默认 50000
        cookie: 自定义 Cookie（覆盖默认值），用于反爬严格的站点
        headers: 自定义请求头 dict（合并到默认 headers）
        **kwargs: 其他参数

    Returns:
        Markdown 格式的页面内容
    """
    target_url = url or expression.strip() or kwargs.get("url", "")
    max_chars = int(kwargs.get("max_chars", 50000))
    custom_cookie = kwargs.get("cookie", None)

    if not target_url:
        return "❌ 错误：请提供要获取的网址。用法：run(url=\"https://example.com\")"

    # 自动补全协议
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    start = time.time()

    try:
        # 构建请求头
        headers = dict(_DEFAULT_HEADERS)
        # 合并用户自定义 headers
        custom_headers = kwargs.get("headers", {})
        if isinstance(custom_headers, dict):
            headers.update(custom_headers)

        # 处理 Cookie — 优先级：参数 > 环境变量 > 空
        cookie = custom_cookie if custom_cookie is not None else _DEFAULT_COOKIE
        if cookie:
            headers["Cookie"] = cookie

        # 百家号需要 Referer
        if "baijiahao.baidu.com" in target_url or "baidu.com" in target_url:
            headers.setdefault("Referer", "https://www.baidu.com/link?url=baijiahao")

        resp = requests.get(target_url, headers=headers, timeout=30, allow_redirects=True)
        resp.raise_for_status()

        # 自动检测编码
        if resp.encoding and resp.encoding.lower() != "utf-8":
            try:
                resp.encoding = resp.apparent_encoding or resp.encoding
            except Exception:
                pass

        html = resp.text
        elapsed = time.time() - start

        # 解析 HTML → Markdown
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # 移除无用元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                         "noscript", "iframe", "form", "svg", "canvas",
                         "select", "option", "button"]):
            tag.decompose()
        # 也移除 class 或 id 中包含 nav/sidebar/side/footer 的 div
        for tag in soup.find_all(["div", "section"],
                                 class_=re.compile(r"nav|sidebar|side|footer|comment", re.I)):
            tag.decompose()
        for tag in soup.find_all(["div", "section"],
                                 id=re.compile(r"nav|sidebar|side|footer|comment", re.I)):
            tag.decompose()

        # 尝试定位正文区域 — 按优先级从高到低
        article = None

        # 1. 语义标签
        article = soup.find("article") or soup.find("main")
        if not article:
            # 2. 通用语义 / 微数据 / ARIA
            article = (
                soup.find(attrs={"itemprop": "articleBody"})
                or soup.find(attrs={"role": "main"})
                or soup.find("div", id="main")
                or soup.find("div", id="content")
            )
        if not article:
            # 3. 中文新闻站常见正文容器 (按特异性从高到低)
            article = (
                soup.find("div", class_="post_body")
                or soup.find("div", class_="post_content")
                or soup.find("div", class_="article-body")
                or soup.find("div", class_="article-content")
                or soup.find("div", class_="article_detail")
                or soup.find("div", class_="main-content")
                or soup.find("div", class_="news-content")
                or soup.find("div", class_="detail-content")
                or soup.find("div", class_="content-detail")
                or soup.find("div", class_="p_mainnew")
                or soup.find("div", class_="entry-content")
                or soup.find("div", class_="post-content")
            )
        if not article:
            # 4. id 包含 content/article/post 的 div（排除导航类）
            for candidate in soup.find_all("div", id=re.compile(r"content|article|post", re.I)):
                c = (candidate.get("class") or [])
                c_str = " ".join(c) if isinstance(c, list) else str(c)
                # 跳过明显不是正文的元素
                if any(x in c_str.lower() for x in ["nav", "side", "foot", "menu", "comment"]):
                    continue
                article = candidate
                break
        if not article:
            # 5. class 包含 content/article/post 的 div（排除导航类）
            for candidate in soup.find_all("div", class_=re.compile(r"content|article|post", re.I)):
                c = (candidate.get("class") or [])
                c_str = " ".join(c) if isinstance(c, list) else str(c)
                if any(x in c_str.lower() for x in ["nav", "side", "foot", "menu", "comment"]):
                    continue
                article = candidate
                break
        if not article:
            # 6. 回退：找文本最多的 div（至少 300 字）
            best = None
            best_len = 0
            for candidate in soup.find_all("div"):
                text = candidate.get_text(strip=True)
                if len(text) > best_len:
                    best_len = len(text)
                    best = candidate
            if best and best_len > 300:
                article = best
        if not article:
            article = soup.body or soup

        # 转换为 Markdown
        md_body = _element_to_markdown(article)

        # 清理多余空行和干扰文本
        md_body = re.sub(r"\n{3,}", "\n\n", md_body)
        md_body = re.sub(r"StartFragment|EndFragment", "", md_body)
        md_body = md_body.strip()

        # 截断
        total_chars = len(md_body)
        if len(md_body) > max_chars:
            md_body = md_body[:max_chars] + "\n\n... [内容截断]"

        # 组装返回
        parts = []
        if title:
            parts.append(f"📄 **页面标题**: {title}")
        parts.append(f"🔗 **来源**: {target_url}")
        parts.append(f"📝 **内容**:\n")
        parts.append(md_body)
        parts.append("")
        parts.append("---")
        parts.append(f"⌛ 页面共 {total_chars} 字符，返回 {len(md_body)} 字符 | 耗时 {elapsed:.1f} 秒")

        return "\n".join(parts)

    except requests.exceptions.Timeout:
        return f"⏰ 请求超时：{target_url} 超过 30 秒未响应"
    except requests.exceptions.HTTPError as e:
        return f"🔌 HTTP 错误 {e.response.status_code}：{target_url}"
    except requests.exceptions.ConnectionError:
        return f"🔌 连接失败：无法访问 {target_url}"
    except requests.exceptions.TooManyRedirects:
        return f"🔁 重定向过多：{target_url}"
    except Exception as e:
        return f"❌ 获取失败：{e}"


def _element_to_markdown(el, indent=0) -> str:
    """将 BeautifulSoup 元素递归转换为 Markdown 字符串。"""
    parts = []
    for child in el.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                parts.append(_escape_markdown(text))
        elif isinstance(child, Tag):
            tag = child.name.lower()
            handler = _TAG_HANDLERS.get(tag)
            if handler:
                result = handler(child, indent)
                if result:
                    parts.append(result)
            else:
                # 未知标签，递归处理子元素
                inner = _element_to_markdown(child, indent)
                if inner:
                    parts.append(inner)
    return "".join(parts)


def _escape_markdown(text: str) -> str:
    """转义 Markdown 特殊字符，但保留代码块内格式。"""
    # 只转义可能影响结构的字符
    text = text.replace("\\", "\\\\")
    text = text.replace("`", "\\`")
    text = text.replace("*", "\\*")
    text = text.replace("_", "\\_")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    text = text.replace("(", "\\(")
    text = text.replace(")", "\\)")
    text = text.replace("#", "\\#")
    text = text.replace("+", "\\+")
    text = text.replace("-", "\\-")
    text = text.replace(".", "\\.")
    text = text.replace("!", "\\!")
    return text


def _get_text_content(el) -> str:
    """获取元素内的纯文本，规范化空白。"""
    texts = []
    for child in el.children:
        if isinstance(child, NavigableString):
            t = str(child).strip()
            if t:
                texts.append(t)
        elif isinstance(child, Tag):
            if child.name in ("script", "style"):
                continue
            if child.name == "br":
                texts.append("\n")
            else:
                t = _get_text_content(child)
                if t:
                    texts.append(t)
    return " ".join(texts)


def _get_attr(el, attr):
    """安全获取属性值。"""
    val = el.get(attr)
    if val:
        return val.strip()
    return ""


# ── 标签处理器 ──────────────────────────────────────────────────

def _handle_heading(el, indent):
    level = min(int(el.name[1]), 6)
    prefix = "#" * level + " "
    text = _get_text_content(el)
    if text:
        return f"\n\n{prefix}{text}\n\n"
    return ""


def _handle_paragraph(el, indent):
    text = _get_text_content(el)
    if text:
        return f"\n\n{text}\n\n"
    return ""


def _handle_link(el, indent):
    text = _get_text_content(el) or el.get("title", "")
    href = _get_attr(el, "href")
    if href and not href.startswith(("http://", "https://", "mailto:", "#")):
        # 相对路径，尝试补全
        pass
    if text and href and not href.startswith("#"):
        return f"[{text}]({href})"
    elif href:
        return href
    return text


def _handle_bold(el, indent):
    text = _get_text_content(el)
    if text:
        return f"**{text}**"
    return ""


def _handle_italic(el, indent):
    text = _get_text_content(el)
    if text:
        return f"*{text}*"
    return ""


def _handle_code(el, indent):
    text = _get_text_content(el)
    if text:
        return f"`{text}`"
    return ""


def _handle_pre(el, indent):
    code = el.find("code")
    if code:
        text = code.get_text()
    else:
        text = el.get_text()
    # 尝试检测语言
    lang = ""
    if code and code.get("class"):
        classes = code.get("class", [])
        for cls in classes:
            if cls.startswith("language-"):
                lang = cls[9:]
                break
    text = text.strip()
    if text:
        return f"\n\n```{lang}\n{text}\n```\n\n"
    return ""


def _handle_list(el, indent):
    tag = el.name
    items = []
    for li in el.find_all("li", recursive=False):
        text = _get_text_content(li)
        if text:
            prefix = "- " if tag == "ul" else "1. "
            items.append(f"{'  ' * indent}{prefix}{text}")
    if items:
        return "\n" + "\n".join(items) + "\n"
    return ""


def _handle_table(el, indent):
    rows = []
    for tr in el.find_all("tr"):
        cells = []
        for cell in tr.find_all(["th", "td"]):
            text = _get_text_content(cell)
            cells.append(text)
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    if rows:
        # 表头下加分隔行
        result = "\n\n" + rows[0] + "\n"
        result += "| " + " | ".join(["---"] * len(cells)) + " |\n"
        for row in rows[1:]:
            result += row + "\n"
        result += "\n"
        return result
    return ""


def _handle_blockquote(el, indent):
    text = _get_text_content(el)
    if text:
        lines = text.split("\n")
        quoted = "\n".join(f"> {line}" for line in lines if line.strip())
        return f"\n\n{quoted}\n\n"
    return ""


def _handle_hr(el, indent):
    return "\n\n---\n\n"


def _handle_image(el, indent):
    src = _get_attr(el, "src")
    alt = _get_attr(el, "alt") or ""
    if src:
        return f"![{alt}]({src})"
    return ""


def _handle_div(el, indent):
    return _element_to_markdown(el, indent)


def _handle_span(el, indent):
    return _element_to_markdown(el, indent)


def _handle_section(el, indent):
    return _element_to_markdown(el, indent)


# 标签处理器映射
_TAG_HANDLERS = {
    "h1": _handle_heading, "h2": _handle_heading, "h3": _handle_heading,
    "h4": _handle_heading, "h5": _handle_heading, "h6": _handle_heading,
    "p": _handle_paragraph,
    "a": _handle_link,
    "strong": _handle_bold, "b": _handle_bold,
    "em": _handle_italic, "i": _handle_italic,
    "code": _handle_code,
    "pre": _handle_pre,
    "ul": _handle_list, "ol": _handle_list,
    "table": _handle_table,
    "blockquote": _handle_blockquote,
    "hr": _handle_hr,
    "img": _handle_image,
    "div": _handle_div,
    "span": _handle_span,
    "section": _handle_section,
    "article": _handle_section,
    "main": _handle_section,
}
