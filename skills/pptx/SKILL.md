---
name: pptx
description: PowerPoint 文件处理 — 读取、创建、编辑 .pptx 演示文稿
parameters:
  - name: action
    type: string
    description: "操作: read(读取) / create(创建) / edit(编辑)"
    enum: ["read", "create", "edit"]
    required: true
  - name: file_path
    type: string
    description: 文件路径（read/edit 用）
  - name: content
    type: string
    description: 演示文稿内容（create 用，Markdown 格式）
  - name: filename
    type: string
    description: 输出文件名（create 用）
---

# PPTX Skill

对 PowerPoint 演示文稿进行读取、创建和编辑操作，返回 JSON 结果。

## Actions

### read
读取 .pptx 文件内容。
- `file_path`: 文件路径
- 返回: `{"success": true, "slides": [{slide: 1, texts: [...]}], "total": N}`

### create
创建新演示文稿。
- `slides`: 幻灯片列表 `[{title: "...", content: "..."}]`
- `output`: 输出文件名（可选，默认 presentation.pptx）
- 返回: `{"success": true, "output": "...", "slides": N}`

### edit
编辑现有演示文稿（追加幻灯片）。
- `file_path`: 源文件路径
- `content`: 新幻灯片内容
- `title`: 新幻灯片标题
- `output`: 输出路径

## 依赖

- `python-pptx`（内置于 requirements.txt）