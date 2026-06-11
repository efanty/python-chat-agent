---
name: gen_image
description: 生成图片并返回Markdown标签，请将返回结果直接嵌入回复中显示
version: 2.3
author: DeepAgent Team
requires: ZHIPU_API_KEY 环境变量 (https://open.bigmodel.cn)
parameters:
  - name: prompt
    type: string
    description: 图片生成的描述文字，支持中文
    required: true
  - name: filename
    type: string
    description: 自定义输出文件名（可选）
  - name: size
    type: string
    description: 图片尺寸，如 1024x1024（可选）
  - name: quality
    type: string
    description: "质量: hd(高细节) 或 standard(快速)"
    enum: ["hd", "standard"]
---

# 图片生成 (gen_image)

根据文本描述（Prompt），调用智谱 GLM-Image / CogView 模型生成图片，
自动下载到沙箱 `sandbox/<user_id>/` 目录，返回 Markdown 图片标签
以便在对话中直接展示。

## 能力

- 根据文本描述生成图片，支持中文 prompt
- 支持多种尺寸（方形、竖屏、横屏、宽屏等），支持尺寸别名
- 支持标准质量（standard）和高清质量（hd）
- 图片自动下载到沙箱，用户隔离
- 返回结果已包含 Markdown 图片标签，无需额外解析

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | string | 是 | — | 图片内容的文字描述，支持中文 |
| `size` | string | 否 | `1024x1024` | 图片尺寸，也支持别名（见下方尺寸别名表） |
| `quality` | string | 否 | `standard` | 质量：`hd`（高细节，~20s）或 `standard`（快速，~5-10s） |
| `watermark` | bool | 否 | `true` | 是否添加 AI 生成水印 |

### 尺寸别名

| 别名 | 实际尺寸 | 比例 | 说明 |
|------|----------|------|------|
| `square` | 1024×1024 | 1:1 | 方形（默认） |
| `portrait` | 768×1344 | 9:16 | 竖屏 |
| `landscape` | 1344×768 | 16:9 | 横屏 |
| `medium_portrait` | 864×1152 | 3:4 | 中等竖屏 |
| `medium_landscape` | 1152×864 | 4:3 | 中等横屏 |
| `widescreen` | 1440×720 | 2:1 | 宽屏 |
| `vertical` | 720×1440 | 1:2 | 竖屏长图 |

也支持直接传入 `"1024x1024"`、`"768x1344"` 等自定义尺寸。
自定义尺寸要求：长宽 512px–2048px 之间，需被 16 整除，最大像素 ≤ 2²¹。

### 调用示例

```json
{
  "prompt": "一只可爱的小猫咪，坐在阳光明媚的窗台上，背景是蓝天白云",
  "size": "square",
  "quality": "hd"
}
```

### 返回格式

成功时返回 Markdown 文本（包含图片标签），LLM 可直接在回复中展示：

```markdown
![一只可爱的小猫咪...](/chat/sandbox/gen_a1b2c3d4_image.png)

— 模型: cogview-3-flash | 尺寸: 1024x1024
```

失败时返回纯文本错误信息（如 "错误：ZHIPU_API_KEY 未设置"）。

### 在回复中展示图片

gen_image 返回的结果已包含 Markdown 图片标签 `![prompt](url)`，
LLM 收到后直接将其包含在回复正文中即可显示图片。

## 安全限制

- 禁止生成暴力、色情、违法等不良内容
- 生成的图片经过智谱内容安全过滤
- 图片存储在沙箱 `sandbox/<user_id>/` 目录，用户隔离
