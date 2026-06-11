---
name: memory_save
description: 保存用户记忆到长期记忆库，包括偏好、事实、习惯等个人信息
version: 1.0
author: DeepAgent Team
parameters:
  - name: key
    type: string
    description: 记忆标识，如 preferred_language、hobby_reading
    required: true
  - name: value
    type: string
    description: 记忆内容，如 "喜欢阅读科幻小说"
    required: true
  - name: type
    type: string
    description: "记忆类型: general(通用) / preference(偏好) / fact(事实) / context(上下文)"
  - name: expression
    type: string
    description: 要保存的内容（纯文本方式，与 key+value 二选一）
---

# 记忆保存 (memory_save)

保存用户的长期记忆。在对话中了解到用户的个人信息、偏好、习惯、重要事实时，
使用此工具记录下来，以便后续对话中提供个性化服务。

## 能力

- 保存任意类型的用户记忆（偏好、事实、习惯、上下文）
- 支持覆盖更新已有记忆
- 每个用户 + 每个 key 唯一

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `key` | string | 是 | 记忆标识，如 `hobby_reading`、`preferred_language` |
| `value` | string | 是 | 记忆内容，如 `喜欢阅读科幻小说` |
| `type` | string | 否 | 类型: general / preference / fact / context |

### 命名规范

key 使用英文小写 + 下划线，按类别分组：
- 偏好: `preferred_xxx`、`like_xxx`、`hate_xxx`
- 习惯: `habit_xxx`、`routine_xxx`
- 事实: `fact_xxx`、`has_xxx`
- 个人信息: `name_xxx`、`job_xxx`、`location_xxx`

### 调用示例

```json
{
  "key": "preferred_language",
  "value": "Python",
  "type": "preference"
}
```

### 返回格式

```json
{
  "success": true,
  "key": "preferred_language",
  "type": "preference",
  "action": "saved"
}
```

## 说明

- 固定 prefix 的 key（如 `profile_`、`fact_`）会自动赋予对应类型
- 后续对话会自动加载相关记忆作为上下文
