---
name: save_note
description: 将指定的内容，自动提取标题和正文，通过 POST 发送到笔记系统API进行保存
version: 2.0
author: DeepAgent Team
requires: requests
parameters:
  - name: title
    type: string
    description: 笔记标题，根据内容总结的简短标题
    required: true
  - name: content
    type: string
    description: 笔记正文内容（Markdown 格式）
    required: true
---

# save_note Skill

将指定的内容，自动提取标题和正文，发送到笔记系统API保存为笔记。

## 工作流程

本 Skill 自动完成以下操作：

### 发送内容到笔记系统

step 1. 将指定的内容，自动提取标题和正文。标题要简短，可以根据正文来命名标题。
step 2. 通过 POST 请求发送到笔记系统 API。
step 3. 获取笔记系统API的响应。
step 4: 将响应结果进行加工，格式化显示在聊天界面，给用户查看

## 前置条件

在 `.env` 文件中配置：

| 环境变量 | 说明 |
|---------|------|
| `NOTE_API_URL` | 笔记系统API地址（默认：https://note.easonai.cn/api/notes） |
| `NOTE_API_KEY` | 笔记系统的 API 认证密钥 |

## 使用方式

调用 `run(expression)` 或 `run(title=..., content=...)`：


### 调用示例

```
# 保存自定义内容
skill__save_note(title="我的笔记标题", content="笔记正文内容")
```

### 发送数据格式

```json
{
  "title": "文章标题（从正文总结并命名，要求简短）",
  "content": "文章正文（Markdown 格式）"
}
```

请求头：
- `Content-Type: application/json`
- `Authorization: {NOTE_API_KEY}`

### 返回格式

```
✅ 笔记已保存成功！
📄 标题: [文章标题]
🔗 笔记链接: [笔记URL](笔记URL)
📝 笔记ID:  [笔记ID]

📥 笔记API 响应:
  [完整响应 JSON]
```

发送成功后，会自动：
1. 从 笔记API响应中提取笔记 URL和笔记ID
2. 展示笔记预览和链接

## 错误处理

- 如果POST请求发送失败：返回具体的错误原因
- 如果 笔记API 配置缺失：提示检查 `.env` 配置
- 如果发送失败：返回 HTTP 状态码和错误信息
