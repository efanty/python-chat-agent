---
name: to_pdf
description: 文件转 PDF — 将 Word、Excel、PPT、HTML、Markdown、文本、图片等格式文件转换为 PDF
parameters:
  - name: file_path
    type: string
    description: 源文件路径（必填），支持 .docx/.xlsx/.pptx/.html/.md/.txt/.png/.jpg 等
    required: true
  - name: output
    type: string
    description: 输出 PDF 文件名（可选，默认 输入文件名.pdf）
  - name: title
    type: string
    description: PDF 文档标题（可选）
---

# to_pdf Skill

将多种格式的文件转换为 PDF 文档，自动处理中文显示。

## 支持的输入格式

| 格式 | 扩展名 | 说明 |
|------|--------|------|
| Word | `.docx`, `.doc` | 保留段落、标题、表格结构 |
| Excel | `.xlsx`, `.xls` | 每个工作表为一节，首行为表头 |
| PowerPoint | `.pptx`, `.ppt` | 每张幻灯片为一节，提取文本和表格 |
| HTML | `.html`, `.htm` | 解析标题(h1-h6)、段落、列表、表格 |
| Markdown | `.md`, `.markdown` | 通过 HTML 中间格式转换 |
| 纯文本 | `.txt`, `.text` | 直接渲染为 PDF |
| 图片 | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.tiff` | 等比例缩放至 A4 页面 |

## 使用方法

### 基本用法
```json
{
  "file_path": "文档.docx"
}
```

### 指定输出文件名
```json
{
  "file_path": "表格.xlsx",
  "output": "报表.pdf"
}
```

### 添加文档标题
```json
{
  "file_path": "报告.docx",
  "output": "最终报告.pdf",
  "title": "2024年度工作总结报告"
}
```

### 转换 Markdown 文件
```json
{
  "file_path": "笔记.md"
}
```

### 转换图片
```json
{
  "file_path": "照片.png",
  "output": "照片.pdf"
}
```

## 返回结果

成功时返回:
```json
{
  "success": true,
  "output": "G:/path/to/output.pdf",
  "source": "G:/path/to/source.docx",
  "source_format": "Word",
  "message": "已将 Word 文件转换为 PDF: G:/path/to/output.pdf"
}
```

失败时返回:
```json
{
  "success": false,
  "error": "错误描述信息"
}
```

## 中文支持

- 自动注册系统字体：微软雅黑（优先）→ 宋体 → 黑体 → 楷体 → 仿宋
- 所有段落、标题、表格均使用中文字体渲染
- 无需手动指定字体

## 依赖

- `reportlab` — PDF 生成引擎
- `python-docx` — Word 文件读取
- `openpyxl` — Excel 文件读取
- `python-pptx` — PowerPoint 文件读取
- `beautifulsoup4` — HTML 解析
- `markdown` — Markdown 转 HTML
- `Pillow` — 图片处理

以上依赖均已包含在项目 `requirements.txt` 中。
