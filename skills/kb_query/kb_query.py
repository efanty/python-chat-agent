"""kb_query Skill — 查询 RAG 知识库（ChromaDB）。

根据用户的问题语义检索知识库中的相关文档片段。

Requires:
  ChromaDB 数据在 chroma_data/ 目录下（或由 CHROMA_HOST 指向远程服务）
"""

import os
import json
from pathlib import Path


# ── Embedding 函数（与上传时使用同一模型） ──────────────────────────────

def _get_embedding_function():
    """创建与上传文档时相同的 embedding 函数。

    通过环境变量配置：
      QUERY_EMBEDDING_MODEL    — 模型名（如 text-embedding-ada-002）
      QUERY_EMBEDDING_API_KEY  — API Key
      QUERY_EMBEDDING_API_BASE — API Base URL（默认 https://api.openai.com/v1）
    """
    model = os.getenv("QUERY_EMBEDDING_MODEL")
    if not model:
        return None  # 使用 ChromaDB 默认 embedding
    api_key = os.getenv("QUERY_EMBEDDING_API_KEY") or os.getenv("CHROMA_OPENAI_API_KEY", "")
    api_base = os.getenv("QUERY_EMBEDDING_API_BASE", "https://api.openai.com/v1")
    if not api_key:
        return None
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    return OpenAIEmbeddingFunction(
        api_key=api_key,
        api_base=api_base.rstrip("/"),
        model_name=model,
    )


# ── ChromaDB 客户端（与 agent_service 保持一致）────────────────────────

def _get_chroma_client():
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
        return chromadb.HttpClient(host=host, port=port, ssl=ssl, headers=headers)
    project_root = Path(__file__).resolve().parent.parent.parent
    chroma_dir = project_root / "chroma_data"
    return chromadb.PersistentClient(path=str(chroma_dir))


# ── 列出所有可用的知识库（Collection） ─────────────────────────────────

def _list_collections() -> list:
    """列出所有 ChromaDB Collection 名称。"""
    try:
        client = _get_chroma_client()
        return [c.name for c in client.list_collections()]
    except Exception:
        return []


# ── 入口函数 ──────────────────────────────────────────────────────────────

def run(expression: str = "", action: str = "", **kwargs) -> str:
    """查询 RAG 知识库。

    根据语义搜索关联的文档片段，返回最相关的结果。

    Args:
        expression: 搜索查询文本
        action:     "query"（默认）或 "list"（列出可用知识库）
        **kwargs:
            query:           搜索查询（与 expression 二选一）
            collection_name: 指定知识库名称（可选，默认搜索所有）
            n_results:       返回结果数量（默认 3，最大 10）

    Returns:
        JSON: {"success": true, "results": [...], "collections_searched": [...]}
    """
    query = kwargs.get("query", "") or expression or ""
    action = action or kwargs.get("action", "query")
    n_results = min(int(kwargs.get("n_results", 3)), 10)

    try:
        client = _get_chroma_client()
    except ImportError:
        return json.dumps({"success": False, "error": "ChromaDB 未安装"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"连接知识库失败: {e}"}, ensure_ascii=False)

    # ── 列出所有知识库 ───────────────────────────────────────────────
    if action == "list":
        try:
            collections = client.list_collections()
            names = [c.name for c in collections]
            return json.dumps({
                "success": True,
                "collections": names,
                "count": len(names),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": f"获取知识库列表失败: {e}"}, ensure_ascii=False)

    # ── 查询 ─────────────────────────────────────────────────────────
    if not query:
        return json.dumps({
            "success": False,
            "error": "请提供搜索查询文本",
            "hint": '使用 run(query="你的问题") 或 run(action="list") 查看可用知识库',
        }, ensure_ascii=False)

    collection_name = kwargs.get("collection_name", "")
    allowed = kwargs.get("_allowed_collections")  # 由系统传入，限制可查询的知识库

    # 如果系统限制了允许的知识库，且用户指定了不在允许列表中的知识库，返回错误
    if allowed and collection_name and collection_name not in allowed:
        return json.dumps({
            "success": False,
            "error": f"无权访问知识库「{collection_name}」，可用: {', '.join(allowed)}",
        }, ensure_ascii=False)

    try:
        if collection_name:
            names = [collection_name]
        else:
            # 未指定 collection 时，只搜索允许的知识库
            all_names = [c.name for c in client.list_collections()]
            names = [n for n in all_names if not allowed or n in allowed]

        if not names:
            return json.dumps({
                "success": False,
                "error": "没有可用的知识库，请在管理后台创建并上传文档",
            }, ensure_ascii=False)

        emb_fn = _get_embedding_function()

        all_results = []
        for col_name in names:
            try:
                if emb_fn:
                    collection = client.get_collection(col_name, embedding_function=emb_fn)
                else:
                    collection = client.get_collection(col_name)
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                )
                docs = results.get("documents", [[]])[0]
                distances = results.get("distances", [[]])[0] if results.get("distances") else []
                metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []

                for i, doc in enumerate(docs):
                    score = 1 - distances[i] if i < len(distances) else 0
                    meta = metadatas[i] if i < len(metadatas) else {}
                    all_results.append({
                        "collection": col_name,
                        "score": round(score, 4),
                        "content": doc[:500],
                        "source": meta.get("source", "unknown"),
                    })
            except Exception:
                continue

        # 按相似度排序
        all_results.sort(key=lambda r: r["score"], reverse=True)

        if not all_results:
            return json.dumps({
                "success": True,
                "results": [],
                "collections_searched": names,
                "message": "未找到相关结果",
            }, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "results": all_results[:n_results],
            "collections_searched": names,
            "total_matches": len(all_results),
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": f"查询失败: {e}"}, ensure_ascii=False)
