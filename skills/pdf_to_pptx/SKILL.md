---
name: pdf_to_pptx
description: 将 PDF 文件转换为 PowerPoint (.pptx) 演示文稿 — 使用智谱视觉大模型识别 PDF 页面内容，自动重建为 PPT 幻灯片
version: 1.0
requires: ZHIPU_API_KEY 环境变量 (https://open.bigmodel.cn)
parameters:
  - name: action
    type: string
    description: "操作: convert(转换PDF为PPT)"
    enum: ["convert"]
    required: true
  - name: file_path
    type: string
    description: PDF 文件路径
    required: true
  - name: output
    type: string
    description: 输出 PPT 文件名（可选，默认 输入文件名.pptx）
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

# PDF to PPTX Skill

将 PDF 文件转换为 PowerPoint (.pptx) 演示文稿。

## 工作原理

1. **PDF 转图片** — 使用 `PyMuPDF`（fitz）将 PDF 每页转为 PNG 图片
2. **视觉识别** — 调用智谱 GLM-4V 视觉大模型识别图片中的内容结构（标题、要点、表格）
3. **重建 PPT** — 使用 `python-pptx` 将识别结果重建为 .pptx 文件，每页 PDF 对应一张幻灯片

## 使用方式

```
run(action="convert", file_path="/path/to/演示.pdf", output="结果.pptx")
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `file_path` | ✅ | PDF 文件路径（相对于项目根目录或绝对路径） |
| `output` | ❌ | 输出文件名，默认 `{PDF文件名}.pptx` |
| `pages` | ❌ | 页码范围，如 "1-3,5" 或 "all"，默认全部 |
| `prompt` | ❌ | 自定义识别提示词，默认使用针对幻灯片结构优化的提示 |
| `model` | ❌ | 视觉模型，默认 `glm-4v-flash` |

## 依赖

- `PyMuPDF` — PDF 转图片（无需 poppler）
- `python-pptx` — 创建 PPT

## 注意事项

- 需要设置 `ZHIPU_API_KEY` 环境变量
- 每页 PDF 生成一张幻灯片
- 复杂排版可能无法完美还原
