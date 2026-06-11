---
name: pdf_to_docx
description: 将 PDF 文件转换为 Word (.docx) 文档 — 使用智谱视觉大模型识别 PDF 页面内容，自动重建为 Word 文档，保留标题、段落、表格等结构
version: 1.0
requires: ZHIPU_API_KEY 环境变量 (https://open.bigmodel.cn)
parameters:
  - name: action
    type: string
    description: "操作: convert(转换PDF为Word)"
    enum: ["convert"]
    required: true
  - name: file_path
    type: string
    description: PDF 文件路径
    required: true
  - name: output
    type: string
    description: 输出 Word 文件名（可选，默认 输入文件名.docx）
  - name: pages
    type: string
    description: 页码范围，如 "1-3,5" 或 "all"（可选，默认 all）
  - name: prompt
    type: string
    description: 自定义识别提示词（可选）
  - name: model
    type: string
    description: 智谱视觉模型名称（可选，默认 glm-4v-flash）
---

# PDF to DOCX Skill

将 PDF 文件转换为 Word (.docx) 文档。

## 工作原理

1. **PDF 转图片** — 使用 `PyMuPDF`（fitz）将 PDF 每页转为 PNG 图片
2. **视觉识别** — 调用智谱 GLM-4V 视觉大模型识别图片中的文字内容、标题层级、表格结构
3. **重建 Word** — 使用 `python-docx` 将识别结果重建为 .docx 文件

## 使用方式

```
run(action="convert", file_path="/path/to/文档.pdf", output="结果.docx")
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `file_path` | ✅ | PDF 文件路径（相对于项目根目录或绝对路径） |
| `output` | ❌ | 输出文件名，默认 `{PDF文件名}.docx` |
| `pages` | ❌ | 页码范围，如 "1-3,5" 或 "all"，默认全部 |
| `prompt` | ❌ | 自定义识别提示词，默认使用针对文档结构优化的提示 |
| `model` | ❌ | 视觉模型，默认 `glm-4v-flash` |

## 依赖

- `PyMuPDF` — PDF 转图片（无需 poppler）
- `python-docx` — 创建 Word 文档
- `requests` — 调用智谱 API

## 注意事项

- 需要设置 `ZHIPU_API_KEY` 环境变量
- 复杂排版（多栏、图文混排）可能无法完美还原
- 图片质量影响识别准确率
