"""Web search skill — Serper.dev Google Search API wrapper.

Requires: SERPER_API_KEY environment variable from https://serper.dev
"""

import os
import json
import requests

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
SERPER_URL = os.getenv("SERPER_URL", "https://google.serper.dev/search")


def run(expression: str = "", query: str = "", **kwargs) -> str:
    """Top-level entry point called by SkillExecutor.

    Args:
        expression: search query (from generic skill function call)
        query: alternative parameter name
    """
    search_query = expression or query or ""
    if not search_query:
        return "Error: no search query provided. Usage: run(query='your search terms')"

    if not SERPER_API_KEY:
        return (
            "Error: SERPER_API_KEY not set. "
            "Get a free API key from https://serper.dev and set the environment variable."
        )

    try:
        headers = {"Content-Type": "application/json", "X-API-KEY": SERPER_API_KEY}
        payload = {"q": search_query}
        resp = requests.post(SERPER_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("organic", [])
        if not results:
            return "No search results found."

        lines = []
        for i, doc in enumerate(results, 1):
            title = doc.get("title", "")
            snippet = doc.get("snippet", "")
            date_str = doc.get("date", "")
            lines.append(f"[{i}] {title}\n   {snippet}\n   {date_str}")

        return "\n\n".join(lines)
    except requests.exceptions.Timeout:
        return "Search timed out."
    except requests.exceptions.RequestException as e:
        return f"Search error: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"
