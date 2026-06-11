---
name: tavily-search
description: Web search using Tavily's LLM-optimized API. Returns relevant results with content snippets, scores, and metadata.
version: 1.0
author: DeepAgent Team
requires: TAVILY_API_KEY 环境变量 (https://tavily.com)
parameters:
  - name: query
    type: string
    description: 搜索关键词
    required: true
  - name: max_results
    type: integer
    description: 返回结果数量（默认 5）
---

# Tavily Search

使用 Tavily API 执行网络搜索，返回优化过的搜索结果供 LLM 分析。

## 前置条件

需要设置环境变量 `TAVILY_API_KEY`（从 https://tavily.com 获取）。

## 能力

- 关键词网络搜索
- 深度搜索模式
- 新闻搜索
- 域名过滤
- 时间范围筛选
- 搜索结果包含标题、摘要、URL、评分

## 使用方式

通过 `skill__tavily_search` 工具调用，传入 `query` 参数。

### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索关键词 |
| `limit` | int | 否 | 返回结果数 (1-20)，默认 10 |
| `depth` | string | 否 | 搜索深度: basic / advanced，默认 basic |
| `topic` | string | 否 | 主题: general / news，默认 general |
| `time_range` | string | 否 | 时间范围: day / week / month / year |
| `include_domains` | string | 否 | 限定域名，逗号分隔 |
| `exclude_domains` | string | 否 | 排除域名，逗号分隔 |

### 示例

```
skill__tavily_search(query="Python async patterns")
skill__tavily_search(query="AI news", topic="news", limit=5)
skill__tavily_search(query="machine learning", depth="advanced")
```

### 返回格式

```
[1] 标题
    摘要
    来源: url | 评分: 0.95

[2] 标题
    ...
```

## 提示

- 搜索词控制在 400 字符以内
- 复杂查询拆分为多个子搜索效果更好
- 使用 `include_domains` 限定可信来源
- 使用 `time_range` 获取最新信息