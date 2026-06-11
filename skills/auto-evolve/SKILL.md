---
name: auto-evolve
description: "Use this skill to self-improve: create new skills, record learnings from conversations, and review existing capabilities."
parameters:
  - name: action
    type: string
    description: "操作: review(自评) / improve(改进) / learn(学习)"
  - name: expression
    type: string
    description: 要处理的内容
---

# Auto-Evolve Skill

## Overview

This skill gives you the ability to **self-improve** and **learn** over time.

## Tools

### 创建新技能
`create_skill(name, description, instructions, tool_code="")`
- 当用户反复要求同类任务时，主动创建新的 Skill
- 例如：用户多次要求格式转换 → 创建 `file-converter` skill

### 记录学习笔记
`record_learning(topic, content)`
- 学到用户偏好后记录下来（如："用户喜欢简洁的回复"）
- 发现有效的问题处理方法时记录（如："处理长文件时先总结再回答"）
- 这些笔记在下次启动时自动加载

### 查看已有技能
`list_skills()`
- 了解自己已掌握的所有技能

## Self-Evolution 规则

1. **主动学习** — 聊到有价值的信息时，用 `record_learning` 记下来
2. **发现重复** — 用户多次提出同类型需求时，用 `create_skill` 创建新工具
3. **经验积累** — 每次启动加载 `role/learnings.md`，从历史经验中受益