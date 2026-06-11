---
name: html-anything
description: 生成精美的独立 HTML 页面 — 网页原型、博客文章、简历、数据报告、社交卡片、演示文稿等
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: generate(生成) / list_templates(列出模板) / get_template(获取模板) / list_categories(列出分类)"
    enum: ["generate", "list_templates", "get_template", "list_categories"]
    required: true
  - name: template
    type: string
    description: 模板名称（generate/get_template 用）
  - name: content
    type: string
    description: 用户提供的内容（generate 用，Markdown 格式）
  - name: title
    type: string
    description: 页面标题（generate 用）
  - name: filename
    type: string
    description: 自定义输出文件名（generate 用）
  - name: dark_mode
    type: boolean
    description: 深色主题（generate 用，默认 false）
---

# HTML 生成 (html-anything)

将用户提供的内容（Markdown / 文本 / 数据）转换为精美的独立 HTML 页面。
支持多种模板风格，生成的 HTML 文件可下载并在浏览器中直接打开。

## 能力

- `list_templates` — 列出所有可用的模板列表
- `get_template` — 获取指定模板的完整设计指南
- `generate` — 根据内容和模板生成 HTML 文件，保存到可下载的路径
- `list_categories` — 列出模板分类

## 支持的设计风格

| 分类 | 模板 | 说明 |
|------|------|------|
| 网页原型 | `prototype-web` | 通用 Web 原型，Hero/Features/CTA/Footer |
| 网页原型 | `saas-landing` | SaaS 落地页，导航/定价/客户评价 |
| 网页原型 | `dashboard` | 管理后台/数据分析面板 |
| 网页原型 | `pricing-page` | 多套餐定价页 |
| 网页原型 | `docs-page` | 技术文档页面 |
| 文章 | `blog-post` | 长篇文章/博客 |
| 文章 | `article-magazine` | 杂志风格文章 |
| 文档 | `resume-modern` | 现代简历（A4 格式） |
| 文档 | `data-report` | CSV/数据 → 可视化数据报告 |
| 文档 | `meeting-notes` | 会议记录/决策日志 |
| 文档 | `weekly-update` | 团队周报 |
| 文档 | `pm-spec` | 产品需求文档 |
| 社交 | `social-x-post-card` | X/Twitter 引语卡片 |
| 社交 | `card-xiaohongshu` | 小红书图文卡片 |
| 社交 | `social-carousel` | 三页轮播图 |
| 演示 | `deck-simple` | 简洁幻灯片 |
| 演示 | `deck-pitch` | 投资人演示 |
| 演示 | `deck-tech-sharing` | 技术分享演示 |

## 使用方式

### 参数说明

| 参数 | 类型 | 必需 | 默认 | 适用操作 | 说明 |
|------|------|------|------|----------|------|
| `action` | string | 是 | — | 所有 | `list_templates` / `list_categories` / `get_template` / `generate` |
| `template` | string | 是 | `prototype-web` | get_template / generate | 模板名称 |
| `content` | string | 否 | — | generate | 用户提供的内容（Markdown 格式） |
| `title` | string | 否 | — | generate | 页面标题 |
| `filename` | string | 否 | 自动生成 | generate | 自定义输出文件名 |
| `dark_mode` | bool | 否 | `false` | generate | 是否生成深色主题 |

### 调用示例

列出可用模板：

```json
{
  "action": "list_templates"
}
```

生成 HTML：

```json
{
  "action": "generate",
  "template": "prototype-web",
  "title": "智能助手平台",
  "content": "## 产品简介\n\n智能助手平台是一款面向企业的 AI 对话系统..."
}
```

获取模板设计指南（供 LLM 参考，用于后续精细调整 HTML）：

```json
{
  "action": "get_template",
  "template": "data-report"
}
```

### 返回格式

`generate` 操作返回生成的 HTML 文件路径，可在回复中以链接形式提供下载：

```
成功生成 HTML 文件
下载地址: /chat/sandbox/my_page.html
```