---
name: ocr_reader
description: 使用智谱视觉大模型识别图片内容，输出 Markdown 格式
version: 1.0
author: DeepAgent Team
requires: ZHIPU_API_KEY 环境变量 (https://open.bigmodel.cn)
parameters:
  - name: action
    type: string
    description: "操作: ocr(文字识别)"
    enum: ["ocr"]
  - name: file_path
    type: string
    description: 图片文件路径
    required: true
---

# OCR Reader Skill

使用智谱 GLM-4V 视觉大模型识别图片中的文字和内容。

## 能力

- 识别图片中的文字（OCR）
- 描述图片中的图表、表格、布局
- 输出 Markdown 格式（保留标题、列表、表格等结构）
- 支持 PNG / JPG / JPEG / WebP / GIF 格式

## 前置条件

需要设置环境变量 `ZHIPU_API_KEY`，从 https://open.bigmodel.cn 获取。

## 使用方式

调用 `run(action, expression)` 函数：
- `action="ocr"` — 识别图片
- `expression` — 图片文件路径

也可通过 JSON 传参：
```json
{"action": "ocr", "file_path": "/path/to/image.png", "prompt": "请识别此图片中的所有文字"}
```