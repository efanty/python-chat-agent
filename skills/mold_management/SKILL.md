---
name: mold_management
description: 模具项目管理 — 查询项目信息、模具信息、试模记录、待办事项等
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: list_projects(项目列表) / get_project(项目详情) / list_molds(模具列表: 传入mold_number+action) / list_trials(试模记录) / list_open_items(未完成项) / list_issues(问题) / list_lessons(经验教训)"
    required: true
  - name: keyword
    type: string
    description: 搜索关键词（list_projects 用，按模具编号/客户名/产品名搜索）
  - name: mold_number
    type: string
    description: 模具编号，如 M25021
---

# 模具项目管理 (mold_management)

管理模具项目的全部数据，包括项目信息、模具信息、产品信息、团队信息、
试模记录、改模记录、问题记录、成本分析等。

## 能力

- `list_projects` — 查询项目列表，支持按关键词搜索
- `get_project` — 获取指定项目的完整信息
- `list_molds` — 查询模具列表
- `list_trials` — 查询试模记录
- `list_open_items` — 查询待办事项
- `list_events` — 查询事件记录
- `list_modifications` — 查询改模记录
- `list_issues` — 查询问题记录（mold_issue_records）
- `list_lessons` — 查询经验教训（lesson_learn）
- `list_materials` — 查询材料信息（material_info）
- `list_changes` — 查询ECN变更记录（change_management）
- `list_cost_info` — 查询成本总表（cost_info）
- `list_dimension_reports` — 查询尺寸检测报告（dimensional_reports）
- `list_injection_info` — 查询注塑成型信息（injection_molding_info）
- `list_packaging` — 查询包装要求（packaging_requirements）
- `list_shipments` — 查询样品寄送记录（sample_shipment_records）
- `list_timeline_tasks` — 查询时间线任务（timeline_tasks）

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `list_projects` / `get_project` / `list_molds` / `list_trials` / `list_open_items` / `list_events` / `list_modifications` / `list_issues` / `list_lessons` / `list_materials` / `list_changes` / `list_cost_info` / `list_dimension_reports` / `list_injection_info` / `list_packaging` / `list_shipments` / `list_timeline_tasks` |
| `keyword` | string | 否 | — | list_projects | 按模具编号/客户名/产品名搜索 |
| `mold_number` | string | 是 | — | get_project/list_trials/list_open_items/list_issues/list_lessons/list_materials/list_changes/list_cost_info/list_dimension_reports/list_injection_info/list_packaging/list_shipments/list_timeline_tasks | 模具编号 |

### 调用示例

查询项目列表：

```json
{
  "action": "list_projects",
  "keyword": "M26007"
}
```

获取项目详情：

```json
{
  "action": "get_project",
  "mold_number": "M26007"
}
```

查询试模记录：

```json
{
  "action": "list_trials",
  "mold_number": "M26007"
}
```

查询待办事项：

```json
{
  "action": "list_open_items",
  "mold_number": "M26007"
}
```