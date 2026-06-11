---
name: 项目看板
description: 生成模具项目的可视化 HTML 看板，展示各阶段进度、问题数量、待办完成率、成本分析等
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: generate(生成看板) / list(列出看板) / get(查看看板)"
    enum: ["generate", "list", "get"]
    required: true
  - name: mold_number
    type: string
    description: 模具编号（generate 时必需），如 M26007
  - name: board_id
    type: integer
    description: 看板 ID（get 时必需）
  - name: keyword
    type: string
    description: 搜索关键词（list 用）
  - name: limit
    type: integer
    description: 最大返回条数（list 用，默认 20）
---

# 项目看板 (project_board)

生成模具项目的可视化 HTML 看板，整合模具数据库中的项目信息、进度、成本、问题等数据，
以直观的图表和卡片形式展示项目全貌。

## 能力

- `generate` — 根据模具编号生成 HTML 看板，保存到 sandbox 目录
- `list` — 查询已生成的看板列表
- `get` — 查看看板详情（返回 HTML 文件路径）

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `generate` / `list` / `get` |
| `mold_number` | string | 是(generate) | — | generate | 模具编号，如 M26007 |
| `board_id` | int | 是(get) | — | get | 看板 ID |
| `keyword` | string | 否 | — | list | 按模具编号搜索 |
| `limit` | int | 否 | 20 | list | 最大返回条数 |

### 调用示例

生成看板：

```json
{
  "action": "generate",
  "mold_number": "M26007"
}
```

查询看板列表：

```json
{
  "action": "list",
  "keyword": "M26007",
  "limit": 10
}
```

查看看板：

```json
{
  "action": "get",
  "board_id": 1
}
```

### 返回格式

generate 返回：

```json
{
  "success": true,
  "board_id": 1,
  "mold_number": "M26007",
  "html_file": "sandbox/board_M26007_20260603.html",
  "url": "/sandbox/board_M26007_20260603.html"
}
```

## 安全限制

- 只读操作，不修改模具数据库
- HTML 文件保存在 sandbox 目录，可通过浏览器访问
