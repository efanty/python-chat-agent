---
name: web_search
description: 通过 Serper API 执行网络搜索，获取实时信息
version: 1.0
author: DeepAgent Team
requires: SERPER_API_KEY 环境变量 (https://serper.dev)
parameters:
  - name: query
    type: string
    description: 搜索关键词。使用中文搜索效果更佳。
    required: true
---

# Web Search Skill

通过 Google 搜索获取实时网页信息。

## 能力

- 关键词网页搜索
- 返回搜索结果标题、摘要、日期
- 格式化输出供 LLM 分析

## 前置条件

需要设置环境变量 `SERPER_API_KEY`，从 https://serper.dev 免费申请。

## 使用方式

当用户需要实时信息或网络搜索时，智能体自动调用此 Skill。

参数：`query` — 搜索关键词。