---
name: send_email
description: 使用系统配置的 SMTP 服务器发送电子邮件，支持附件
version: 1.0
author: DeepAgent Team
requires: .env 中的 MAIL_SERVER / MAIL_PORT / MAIL_USERNAME / MAIL_PASSWORD
parameters:
  - name: to
    type: string
    description: 收件人邮箱，多个用英文逗号分隔
    required: true
  - name: subject
    type: string
    description: 邮件主题
    required: true
  - name: body
    type: string
    description: 邮件正文（纯文本或 HTML）
    required: true
  - name: content_type
    type: string
    description: 正文格式
    enum: ["plain", "html"]
  - name: cc
    type: string
    description: 抄送邮箱，多个用英文逗号分隔
  - name: attachments
    type: string
    description: 附件路径，多个用英文逗号分隔
---

# Send Email Skill

使用系统默认 SMTP 服务器发送电子邮件。

## 能力

- 发送纯文本或 HTML 邮件
- 支持多个收件人（逗号分隔）
- 支持抄送
- 支持附件（pdf / png / jpg / docx / xlsx / csv / zip 等，单附件≤10MB）

## 使用方式

参数以 JSON 字符串传入，调用 `run` 函数。

参数说明：
- `to` — 收件人，逗号分隔
- `subject` — 主题
- `body` — 正文
- `content_type` — "plain" 或 "html"（默认 plain）
- `cc` — 抄送（可选）
- `attachments` — 附件路径，逗号分隔（可选）
