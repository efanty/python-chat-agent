"""Tavily Search Skill — 通过 Tavily API 执行网络搜索。

需要 TAVILY_API_KEY 环境变量。
"""

import os
import json
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

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


def run(expression: str = "", query: str = "", **kwargs) -> str:
    """执行 Tavily 网络搜索。

    Args:
        expression: 搜索关键词（兼容旧用法）
        query: 搜索关键词
        **kwargs:
            limit: 结果数量 (1-20)，默认 10
            depth: 搜索深度 "basic" 或 "advanced"，默认 "basic"
            topic: "general" 或 "news"，默认 "general"
            time_range: "day"/"week"/"month"/"year"，可选
            include_domains: 限定域名，逗号分隔
            exclude_domains: 排除域名，逗号分隔

    Returns:
        格式化搜索结果文本
    """
    search_query = expression or query or ""
    if not search_query:
        return "Error: 请提供搜索关键词"

    if not TAVILY_API_KEY:
        return "Error: 未设置 TAVILY_API_KEY。请从 https://tavily.com 获取并设置环境变量。"

    limit = int(kwargs.get("limit", 10))
    depth = kwargs.get("depth", "basic")
    topic = kwargs.get("topic", "general")
    time_range = kwargs.get("time_range", "")
    include_domains = kwargs.get("include_domains", "")
    exclude_domains = kwargs.get("exclude_domains", "")

    try:
        payload = {
            "api_key": TAVILY_API_KEY,
            "query": search_query,
            "max_results": min(max(limit, 1), 20),
            "search_depth": depth,
            "topic": topic,
            "include_answer": False,
            "include_raw_content": False,
        }
        if time_range:
            payload["time_range"] = time_range
        if include_domains:
            payload["include_domains"] = [d.strip() for d in include_domains.split(",") if d.strip()]
        if exclude_domains:
            payload["exclude_domains"] = [d.strip() for d in exclude_domains.split(",") if d.strip()]

        resp = requests.post(TAVILY_URL, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            return "未找到搜索结果。"

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            snippet = r.get("content", "")
            url = r.get("url", "")
            score = r.get("score", "")
            score_str = f" | 评分: {score:.2f}" if isinstance(score, (int, float)) else ""
            lines.append(f"[{i}] {title}\n   {snippet}\n   来源: {url}{score_str}")

        return "\n\n".join(lines)

    except requests.exceptions.Timeout:
        return "搜索超时，请重试。"
    except requests.exceptions.RequestException as e:
        return f"搜索请求失败: {e}"
    except Exception as e:
        return f"搜索出错: {e}"
