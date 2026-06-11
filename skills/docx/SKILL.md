---
name: docx
description: Word 文件处理 — 读取、创建、编辑 .docx 文档
parameters:
  - name: action
    type: string
    description: "操作: read(读取) / create(创建) / edit(编辑)"
    enum: ["read", "create", "edit"]
    required: true
  - name: file_path
    type: string
    description: 文件路径（read 用）
  - name: content
    type: string
    description: 文档内容（create 用，Markdown 格式）
  - name: filename
    type: string
    description: 输出文件名（create 用）
  - name: output_path
    type: string
    description: 保存路径
---

# DOCX Skill

对 Word 文档进行读取、创建和编辑操作，返回 JSON 结果。

## Actions

### read
读取 .docx 文件内容。
- `file_path`: 文件路径
- 返回: `{"success": true, "paragraphs": [...], "tables": [...], "para_count": N}`

### create
创建新 Word 文档。
- `content`: 纯文本内容
- `title`: 文档标题
- `headings`: 结构化内容 `[{heading: "章标题", body: "..."}]`
- `output`: 输出文件名
- 返回: `{"success": true, "output": "..."}`

### edit
编辑现有文档（追加内容）。
- `file_path`: 源文件路径
- `content`: 要追加的文本
- `output`: 输出路径

## 依赖

- `python-docx`（内置于 requirements.txt）