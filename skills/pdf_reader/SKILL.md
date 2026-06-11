---
name: pdf_reader
description: 解析 PDF 文件，提取文本内容并转换为 Markdown 格式
version: 1.0
author: DeepAgent Team
requires: pip install pypdf
parameters:
  - name: action
    type: string
    description: "操作: extract(提取文本) / read(读取)"
    enum: ["extract", "read"]
  - name: file_path
    type: string
    description: PDF 文件路径，支持绝对路径或相对路径
    required: true
---

# PDF Reader Skill

解析 PDF 文件，提取文本内容并输出为 Markdown 格式。

## 能力

- 读取本地 PDF 文件
- 逐页提取文本内容
- 输出 Markdown 格式（页码标题 + 正文）
- 自动截断过长内容（最大 30000 字符）

## 使用方式

调用 `run(action, expression)` 函数：
- `action="extract"` 或 `action="read"` — 提取 PDF 内容
- `expression` — PDF 文件路径（绝对路径或相对路径）

也可通过 JSON 传参：
```json
{"action": "extract", "file_path": "/path/to/file.pdf"}
```