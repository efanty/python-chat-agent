---
name: memory_query
description: 查询用户的长期记忆，包括偏好、事实、习惯等个人信息
version: 1.0
author: DeepAgent Team
parameters:
  - name: key
    type: string
    description: 按 key 精确查询（可选）
  - name: type
    type: string
    description: "筛选类型: general(通用) / preference(偏好) / fact(事实) / context(上下文)"
  - name: query
    type: string
    description: 按关键词搜索记忆内容
  - name: expression
    type: string
    description: 要查询的记忆关键词或问题（纯文本方式，与 query 等效）
---

# 记忆查询 (memory_query)

查询当前用户在长期记忆中保存的信息。当需要了解用户的偏好、习惯、个人信息时，
使用此工具获取相关记忆。

## 能力

- 列出用户的所有记忆
- 按 key 精确查询
- 按类型筛选（偏好/事实/习惯）
- 按关键词搜索记忆内容

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `key` | string | 否 | 按 key 精确查询 |
| `type` | string | 否 | 筛选类型: general / preference / fact / context |
| `query` | string | 否 | 按关键词搜索 value |

### 调用示例

查询用户所有偏好：
```json
{
  "type": "preference"
}
```

搜索关键词：
```json
{
  "query": "编程"
}
```

### 返回格式

```json
{
  "success": true,
  "memories": [
    {"key": "preferred_language", "value": "Python", "type": "preference", "updated": "2025-01-15"}
  ],
  "count": 1
}
```
