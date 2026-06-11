---
name: agent-memory
description: 智能体记忆系统 — 记录用户偏好、事实、习惯，跨会话追踪实体和经验学习
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: remember(记忆) / recall(回忆) / list(列出)"
    enum: ["remember", "recall", "list", "forget"]
  - name: expression
    type: string
    description: 要记忆或查询的内容
---

# Agent Memory Skill

智能体跨会话持久化记忆系统。使用项目内置的 `skill__memory_save` 和 `skill__memory_query` 工具。

## 能力

- **记忆事实**：记录用户个人信息、偏好、习惯、重要上下文
- **经验学习**：从对话中学习经验教训，在后续对话中应用
- **实体追踪**：追踪人物、项目、团队等实体的信息和关系
- **跨会话持久化**：所有记忆自动保存到数据库，重启后仍然可用

## 工作机制

本 Skill 不直接操作数据库，而是通过已有的 `skill__memory_save` 和 `skill__memory_query` 工具完成所有记忆操作。

### 记忆保存

当对话中出现以下信息时，自动使用 `skill__memory_save` 保存：

- 用户告知的个人信息（姓名、职业、位置、联系方式等）
- 明确的偏好（"我喜欢……"、"我习惯……"）
- 重要事实（"我的项目是……"、"我正在学习……"）
- 上下文信息（"这周我在……"）

### 记忆查询

新对话开始时或遇到相关话题时，使用 `skill__memory_query` 查询已有记忆。

### 实体追踪

实体信息统一存储在 `entity_` 前缀的 key 下：

| key 格式 | 内容 | 示例 |
|----------|------|------|
| `entity_person_{name}` | 人物信息 | `{"role":"工程师","project":"AI平台"}` |
| `entity_project_{name}` | 项目信息 | `{"status":"进行中","tech":"Python"}` |
| `entity_team_{name}` | 团队信息 | `{"members":["张三","李四"]}` |

### 经验学习

经验教训存储在 `lesson_` 前缀的 key 下：

| key 格式 | 内容 | 示例 |
|----------|------|------|
| `lesson_{topic}` | 经验教训 | `"用户偏好使用异步方式处理文件"` |

## 使用方式

当需要操作记忆时，直接使用以下工具：

- **保存记忆**：调用 `skill__memory_save`，传入 `key`, `value`, `type`
- **查询记忆**：调用 `skill__memory_query`，可传 `key`、`type` 或关键词搜索