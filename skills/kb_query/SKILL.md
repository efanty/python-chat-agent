---
name: kb_query
description: 语义检索 RAG 知识库，根据问题查找最相关的文档内容
version: 1.0
author: DeepAgent Team
requires: QUERY_EMBEDDING_MODEL / QUERY_EMBEDDING_API_KEY / QUERY_EMBEDDING_API_BASE 环境变量
parameters:
  - name: query
    type: string
    description: 检索查询文本，自然语言描述要查找的内容
    required: true
  - name: collection_name
    type: string
    description: 知识库名称
  - name: n_results
    type: integer
    description: 返回结果数量（默认 3）
---

# 知识库查询 (kb_query)

查询 ChromaDB 向量知识库，根据用户的问题语义检索最相关的文档片段。
当用户询问与知识库相关的问题时，使用此工具获取答案所需的上下文。

## 能力

- 语义搜索知识库中的文档内容
- 支持指定知识库名称，默认搜索所有知识库
- 返回匹配结果的相似度分数（0-1）
- 列出当前可用的所有知识库

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 说明 |
|------|------|------|------|------|
| `query` | string | 是 | — | 搜索查询文本，用自然语言描述要找的内容 |
| `collection_name` | string | 否 | 全部 | 指定在哪个知识库中搜索（可通过 `action=list` 查看可用列表） |
| `n_results` | int | 否 | 3 | 返回结果数量，最大 10 |
| `action` | string | 否 | `query` | `query` = 搜索，`list` = 列出知识库 |

### 调用示例

搜索知识库：
```json
{
  "query": "产品的价格是多少？",
  "collection_name": "产品文档",
  "n_results": 5
}
```

列出所有知识库：
```json
{
  "action": "list"
}
```

### 返回格式

```json
{
  "success": true,
  "results": [
    {
      "collection": "产品文档",
      "score": 0.9234,
      "content": "产品定价分为三个档位...",
      "source": "pricing.md"
    }
  ],
  "collections_searched": ["产品文档"],
  "total_matches": 1
}
```

## 说明

- 查询基于语义相似度（向量距离），而非关键词匹配
- 结果按相关性降序排列
- 搜索所有知识库时会合并结果并重排序

## 配置要求

查询时使用的 Embedding 模型必须与上传文档时使用的模型一致，否则无法匹配到结果。
请在 `.env` 文件中配置：

```
QUERY_EMBEDDING_MODEL=text-embedding-ada-002
QUERY_EMBEDDING_API_KEY=你的API密钥
QUERY_EMBEDDING_API_BASE=https://api.openai.com/v1
```

这三个值需要与知识库绑定的 Embedding 模型的配置保持一致。