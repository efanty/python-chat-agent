---
name: pdf
description: PDF 文件处理 — 合并、拆分、旋转、加水印、提取表格、创建新 PDF
parameters:
  - name: action
    type: string
    description: "操作: merge(合并) / split(拆分) / rotate(旋转) / watermark(水印) / extract_tables(提取表格)"
    enum: ["merge", "split", "rotate", "watermark", "extract_tables"]
    required: true
  - name: file_path
    type: string
    description: PDF 文件路径
  - name: pages
    type: string
    description: 页码范围，如 1-3,5（split 用）
  - name: output_path
    type: string
    description: 输出文件路径
---

# PDF Skill

对 PDF 文件进行各种操作，返回 JSON 结果。

## Actions

### merge
合并多个 PDF 文件为一个。
- `files`: PDF 文件路径列表
- `output`: 输出路径（可选，默认 merged.pdf）
- 返回: `{"success": true, "output": "...", "pages": N}`

### split
按页拆分 PDF。
- `file_path`: PDF 文件路径
- `output_dir`: 输出目录（可选）
- 返回: `{"success": true, "pages": [...], "total": N}`

### rotate
旋转 PDF 页面。
- `file_path`: 文件路径
- `angle`: 旋转角度（可选，默认 90）
- `pages`: 页面列表如 "1,3,5" 或 "all"（可选）
- `output`: 输出路径

### extract_table
从 PDF 中提取表格。
- `file_path`: 文件路径
- `pages`: 页面范围（可选）
- 需要 `pdfplumber`

### create
从文本创建 PDF。
- `content`: 文本内容
- `title`: 文档标题（可选）
- `output`: 输出路径
- 需要 `reportlab`

## 依赖

内置于 `requirements.txt`: `pypdf`, `pdfplumber`, `reportlab`