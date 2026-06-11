---
name: url_fetcher
description: 获取指定网址的内容，自动将 HTML 转换为 Markdown 格式返回
version: 1.0
author: DeepAgent Team
requires: beautifulsoup4 (已内置)
parameters:
  - name: url
    type: string
    description: 要获取内容的网址
    required: true
---

# URL Fetcher Skill

获取指定网址的内容，自动解析 HTML 并转换为 Markdown 格式。

## 能力

- 获取任意公开 URL 的内容
- 自动将 HTML → Markdown 格式转换（保留标题、链接、列表、代码块、表格等结构）
- 自动截断过长内容（最大 50000 字符）
- 支持自定义 User-Agent
- 智能编码检测

## 使用方式

调用 `run(expression)` 或 `run(url=...)`：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 要获取内容的网址（expression 中也可传入） |
| `max_chars` | int | 否 | 最大返回字符数，默认 50000 |
| `cookie` | string | 否 | 自定义 Cookie，用于反爬严格的站点（如百度百家号） |
| `headers` | dict | 否 | 自定义请求头，合并到默认 headers 中 |

> **百度百家号**：百家号有反爬机制，需要设置 Cookie 和 Referer 才能正常获取内容。
> 1. 在 `.env` 文件中配置 `BAIDU_COOKIE=你的Cookie`（推荐）
> 2. 或在调用时传入 `cookie="你的Cookie"` 参数

### 调用示例

```
skill__url_fetcher(url="https://example.com")
skill__url_fetcher(url="https://docs.python.org/3/", max_chars=10000)
skill__url_fetcher(expression="https://example.com/article")
```

### 返回格式

```
📄 页面标题: [页面标题]
🔗 来源: [URL]
📝 内容:

[Markdown 格式的内容]

---

⌛ 页面共 X 字符，返回 Y 字符 | 耗时 Z 秒
```

## 注意事项

- 仅支持 `http://` 和 `https://` 协议
- 请求超时 30 秒
- 只获取页面正文区域（跳过导航、页脚等非主要内容）
- 如果页面需要登录或反爬，可能无法获取完整内容