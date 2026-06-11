# DeepAgent Chat

基于 Flask + ChromaDB 的 AI 智能体对话平台。支持多模型（OpenAI / DeepSeek / 智谱 GLM）、MCP 工具协议、RAG 知识库、图片生成、Skill 扩展系统、用户长期记忆。

## 快速开始（5 分钟）

### Windows

```bat
:: 双击 deploy.bat 或在 cmd 中执行
deploy.bat
```

脚本自动按顺序完成：检查 Python → 创建 venv → 安装依赖 → 生成 `.env`（含随机 SECRET_KEY）→ 初始化数据库 → 启动服务。

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 API Key，至少需要一个 LLM 模型的 Key
python run.py
```

首次启动自动创建管理员账号，密码随机生成并打印到控制台（格式见下方日志输出）。

### Docker

```bash
docker compose up -d
docker compose logs -f    # 查看初始管理员密码
```

## 核心功能

### 多模型支持

| 提供商 | 支持类型 | 配置方式 |
|--------|----------|----------|
| OpenAI | 文本 / Embedding / 视觉 | 管理后台添加 |
| DeepSeek | 文本 | 管理后台添加 |
| 智谱 GLM | 文本 / 视觉 / 图片生成 | 管理后台添加 |
| 兼容 OpenAI 协议 | 通用 | 管理后台添加 |

### 智能体系统

智能体（Agent）聚合以下能力：

- **系统提示词** — 自定义角色和行为指令
- **Skills** — 模块化工具扩展（计算/数据库/图片生成/邮件等）
- **MCP 工具** — Model Context Protocol，支持 stdio/SSE 传输
- **RAG 知识库** — ChromaDB 向量检索，文档自动分块和 Embedding
- **API 端点** — 自定义 HTTP API 集成

### 17 个预置 Skills

| Skill | 功能 | Python 依赖 |
|-------|------|-------------|
| **calculator** | 安全数学计算（加减乘除、三角函数、幂运算） | 无 |
| **db_operator** | SQLite 数据库增查改（禁止删除），支持自动操作日志 | 无 |
| **docx** | Word 文档读取/创建/编辑 | `python-docx` |
| **gen_image** | 智谱 CogView 图片生成 | 无 |
| **get_date** | 公历/农历/生肖/日期计算 | 无 |
| **kb_query** | ChromaDB 语义检索 | ChromaDB（内置） |
| **memory_save** | 保存用户长期记忆（偏好/事实/习惯） | 无 |
| **memory_query** | 查询用户长期记忆 | 无 |
| **ocr_reader** | 智谱 GLM-4V 图片文字识别 | 无 |
| **pdf** | PDF 合并/拆分/旋转/加水印/创建/表格提取 | `pypdf`, `reportlab`, `pdfplumber` |
| **pdf_reader** | PDF 文本提取转 Markdown | `pypdf` |
| **pptx** | PowerPoint 读取/创建/编辑 | `python-pptx` |
| **send_email** | SMTP 发送邮件（支持附件） | 无 |
| **skill_creator** | 在线创建新 Skill（文件 + 数据库注册） | 无 |
| **web_search** | Serper API 网络搜索 | 无 |
| **xlsx** | Excel 读取/创建/编辑/CSV 转 XLSX | `openpyxl`, `pandas` |

> **自动检测**：Skill 在管理后台绑定到智能体后生效。依赖库未安装时返回友好提示，不需要全部预装。

### Skill 调用参考

智能体自动按名称调用 Skill。每个 Skill 的精确命名规则为 `skill__<folder_name>()`，参数以关键字形式传入。以下是所有 Skill 的完整调用格式和示例。

#### 通用工具

| Skill | 调用方式 | 示例 |
|-------|----------|------|
| calculator | `skill__calculator(expression="...")` | `skill__calculator(expression="2 + 3 * sqrt(16)")` |
| db_operator | `skill__db_operator(action="query", table="...", ...)` | `skill__db_operator(action="query", table="users", limit=5)` |
| get_date | `skill__get_date(expression="...")`<br>`skill__get_date(action="calc", expression='{"base":"...","days":N}')` | `skill__get_date(expression="now")`<br>`skill__get_date(action="calc", expression='{"base":"2025-01-01","days":30}')` |
| web_search | `skill__web_search(query="...")` | `skill__web_search(query="2025年春节放假安排")` |
| send_email | `skill__send_email(to="...", subject="...", body="...", attachments="...")` | `skill__send_email(to="user@example.com", subject="报告", body="详见附件")` |
| skill_creator | `skill__skill_creator(name="...", description="...")` | `skill__skill_creator(name="天气查询", description="根据城市名查实时天气")` |

#### 图片 / 文件处理

| Skill | 调用方式 | 示例 |
|-------|----------|------|
| gen_image | `skill__gen_image(prompt="...", size="square|landscape", quality="hd")` | `skill__gen_image(prompt="一只可爱的小猫，阳光窗台，蓝天白云", size="square")` |
| ocr_reader | `skill__ocr_reader(file_path="...")` | `skill__ocr_reader(file_path="uploads/img.png")` |
| pdf_reader | `skill__pdf_reader(file_path="...")` | `skill__pdf_reader(file_path="uploads/doc.pdf")` |

#### 文档处理（需对应依赖）

| Skill | 调用方式 | 示例 |
|-------|----------|------|
| docx | `skill__docx(action="read", data={"file_path":"..."})`<br> `skill__docx(action="create", data={"content":"...","output":"..."})`<br> `skill__docx(action="edit", data={"file_path":"...","content":"..."})` | `skill__docx(action="read", data={"file_path":"report.docx"})` |
| pdf | `skill__pdf(action="merge", data={"files":["a.pdf","b.pdf"],"output":"merged.pdf"})`<br> `skill__pdf(action="split", data={"file_path":"doc.pdf"})`<br> `skill__pdf(action="create", data={"content":"...","output":"new.pdf"})`<br> `skill__pdf(action="extract_table", data={"file_path":"table.pdf"})` | `skill__pdf(action="merge", data={"files":[ "ch1.pdf","ch2.pdf"],"output":"book.pdf"})` |
| pptx | `skill__pptx(action="read", data={"file_path":"..."})`<br> `skill__pptx(action="create", data={"slides":[...],"output":"..."})`<br> `skill__pptx(action="edit", data={"file_path":"...","content":"..."})` | `skill__pptx(action="create", data={"slides":[{"title":"封面","content":"内容"}],"output":"demo.pptx"})` |
| xlsx | `skill__xlsx(action="read", data={"file_path":"...","sheet":"Sheet1"})`<br> `skill__xlsx(action="create", data={"columns":[...],"rows":[...],"output":"..."})`<br> `skill__xlsx(action="csv", data={"file_path":"data.csv","delimiter":","})` | `skill__xlsx(action="create", data={"columns":["姓名","分数"],"rows":[["张三",95],["李四",87]],"output":"成绩.xlsx"})` |

#### 记忆 / 知识库

| Skill | 调用方式 | 示例 |
|-------|----------|------|
| memory_save | `skill__memory_save(key="...", value="...")` | `skill__memory_save(key="hobby", value="编程")` |
| memory_query | `skill__memory_query(key="...")`<br>`skill__memory_query(action="all")` | `skill__memory_query(action="all")` — 列出所有记忆 |
| kb_query | `skill__kb_query(query="...")`<br>`skill__kb_query(action="list")` | `skill__kb_query(query="产品的定价方案？")` |

### 系统功能

以下功能由系统自动处理，不需要智能体或用户手动调用：

- **RAG 知识库自动检索**：每次对话开始时，系统自动从关联的知识库中检索与用户问题最相关的文档段落，注入到系统提示词中。智能体无需显式调用 `kb_query`，除非要查询非关联的知识库。
- **用户记忆自动加载**：系统每次对话自动加载当前用户的所有已保存记忆（偏好、事实、习惯）作为上下文。智能体可调用 `memory_save` / `memory_query` 进行增删查改。
- **用户身份感知**：系统自动注入当前登录用户的信息（用户 ID、用户名、昵称、角色、邮箱）到每次对话中。智能体可根据这些信息提供个性化服务（如知道用户邮箱后可发送邮件）。

### 余额查询

管理后台 LLM 模型列表中，带**钱包图标**的模型行支持余额查询。当前支持的提供商：

| 提供商 | 查询地址 | 认证方式 |
|--------|----------|----------|
| DeepSeek | `GET https://api.deepseek.com/user/balance` | Bearer Token |
| OpenAI | `GET https://api.openai.com/dashboard/billing/subscription` | Bearer Token |
| 智谱 GLM | `GET https://bigmodel.cn/api/biz/account/query-customer-account-report` | Bearer Token → URL 参数（自动降级） |

### 管理后台

| 路径 | 功能 |
|------|------|
| `/admin/` | 控制面板 — 系统统计 |
| `/admin/users` | 用户 CRUD + 权限管理 |
| `/admin/models` | LLM 模型配置 + 余额查询（DeepSeek/OpenAI/智谱） |
| `/admin/agents` | 智能体创建/编辑/删除 + 绑定工具 |
| `/admin/mcp-tools` | MCP 工具管理 |
| `/admin/skills` | Skill 注册 + ZIP 上传安装 |
| `/admin/knowledge-bases` | 创建知识库 + 上传文档（PDF/文本） |
| `/admin/settings` | 网站设置/速率限制/超时配置 |
| `/admin/memories` | 用户长期记忆管理 |

### 主题切换

聊天界面、个人设置、管理后台均支持 **深色 ↔ 浅色** 一键切换。偏好通过 `localStorage` 持久化，新标签页自动继承。

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `SECRET_KEY` | **是** | 自动生成 | Flask 会话加密 + JWT 签名密钥。生产环境务必修改 |
| `ADMIN_PASSWORD` | 否 | 随机 32 位 | 覆盖初始管理员密码。不设置则每次重置数据库时随机生成 |
| `DATABASE_URL` | 否 | `sqlite:///app.db` | 数据库连接。生产环境推荐 MySQL: `mysql+pymysql://user:pass@host:3306/dbname?charset=utf8mb4` |
| `ZHIPU_API_KEY` | 荐 | — | 智谱 API Key（图片生成 `cogview-3-flash` + OCR `glm-4v-flash`） |
| `SERPER_API_KEY` | 荐 | — | Serper API Key（网络搜索） |
| `MAIL_SERVER` | 否 | `smtp.gmail.com` | SMTP 服务器 |
| `MAIL_PORT` | 否 | `587` | SMTP 端口（465=SSL, 587=TLS） |
| `MAIL_USERNAME` | 否 | — | SMTP 用户名 |
| `MAIL_PASSWORD` | 否 | — | SMTP 密码 |
| `QUERY_EMBEDDING_API_KEY` | 否 | — | RAG Embedding 模型 API Key（在管理后台配置模型更灵活） |
| `QUERY_EMBEDDING_API_URL` | 否 | — | RAG Embedding 模型 API 地址 |

## 安全特性（v2.x）

| 类别 | 措施 |
|------|------|
| **API Key 加密** | 所有 LLM API Key 使用 Fernet 对称加密（`cryptography`）存储。数据库泄露不会直接暴露密钥 |
| **JWT 签名** | 邮箱验证和密码重置 Token 统一使用 `SECRET_KEY` 签名，消除硬编码密钥 |
| **CSRF 保护** | Flask-WTF CSRFProtect 对所有 POST/表单请求强制验证。JSON API 端点豁免（已受 `@login_required` 保护）|
| **速率限制** | Flask-Limiter：登录 10 次/分钟、注册 3 次/分钟、忘记密码 3 次/分钟 |
| **Open Redirect** | 登录 `next` 参数白名单校验，仅允许相同域名的相对路径 |
| **SSL 验证** | 余额查询默认启用 SSL 证书验证。智谱业务 API 降级策略（见 `model_balance()`）|
| **MIME 校验** | 文件上传扩展名 + python-magic 字节签名双重校验 |
| **安全响应头** | `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block` |
| **会话安全** | `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`。生产环境启用 `SESSION_COOKIE_SECURE=True` |
| **管理员账户** | 首次启动自动生成随机密码。可通过 `ADMIN_PASSWORD` 环境变量预设 |
| **日志审计** | 认证、管理操作、业务操作分标签记录到 `logs/app.log` 和 `logs/app-error.log`，含用户/IP/请求路径 |

## 日志系统

日志统一由 `app/logger.py` 管理，输出格式：

```
2026-05-10 11:36:10 | INFO  | user(admin/1) | 192.168.1.88 | POST /auth/login | [认证] 登录成功 — username=admin
2026-05-10 11:36:15 | INFO  | user(admin/1) | 192.168.1.88 | POST /admin/users/add | [管理] 用户已添加 — user_id=3
2026-05-10 11:36:20 | ERROR | user(admin/1) | 192.168.1.88 | POST /chat/stream | [错误] API 调用失败
```

### 日志分类

| 函数 | 标签 | 适用场景 |
|------|------|----------|
| `log_action()` | `[操作]` | 创建/删除/更新对话、上传文件等 |
| `log_auth()` | `[认证]` | 登录/登出/注册/TOTP 验证 |
| `log_admin()` | `[管理]` | 管理后台 CRUD/设置变更 |
| `log_error()` | `[错误]` | 异常捕获（含 traceback）|

### 日志文件

| 文件 | 内容 | 级别 | 轮转 |
|------|------|------|------|
| `logs/app.log` | 全部日志 | DEBUG ~ CRITICAL | 10MB × 5 |
| `logs/app-error.log` | 仅错误 | ERROR ~ CRITICAL | 10MB × 3 |
| 控制台 | 实时输出 | INFO ~ CRITICAL | — |

## API 加密存储

所有存储在数据库中的 API Key（LLM 模型、API 端点）均使用 Fernet 加密：

```python
from app.utils.crypto import encrypt, decrypt

encrypted = encrypt("sk-xxx")  # 返回 "gAAAAAB..."
plaintext = decrypt(encrypted)  # 恢复 "sk-xxx"
```

- **加密密钥**：派生自 `SECRET_KEY`（`cryptography.fernet.Fernet` + `base64` HMAC-SHA256）
- **TypeDecorator**：SQLAlchemy 模型字段 `EncryptedString` 自动加密/解密
- **迁移兼容**：`decrypt()` 函数对未加密的明文无操作返回，平滑升级

## FAQ / 常见问题

**Q: 启动后控制台找不到管理员密码？**

检查日志输出。首次启动会打印：
```
==============================================================
  默认管理员账户已创建
   用户名: admin
   密  码: <随机生成的密码>
   邮  箱: admin@agentapp.local
  ⚠ 请首次登录后立即修改密码！
==============================================================
```
**Q: 数据库已有数据，如何启用 API Key 加密？**

执行离线迁移命令：
```bash
python -m app.utils.migrate_encrypt
```
该命令遍历所有 `llm_models` 记录，将明文 API Key 加密存储。

**Q: 余额查询报 SSL 错误？**

DeepSeek 和 OpenAI 接口强制 SSL 验证。智谱业务 API 存在证书兼容问题，代码已内置降级策略。如 SSL 错误持续，检查系统时间是否正确。

**Q: 如何添加自定义 Skill？**

1. 在 `skills/` 下创建文件夹，实现 `run()` 函数（返回 JSON 字符串）
2. 编写 `SKILL.md`（含 YAML 前置元数据）
3. 管理后台 → Skills → 添加 Skill
4. 管理后台 → 智能体管理 → 绑定 Skill

## 项目结构

```
app/                    # Flask 应用
├── blueprints/         # 路由模块
│   ├── admin/          #   管理后台 (users/models/agents/skills/kb...)
│   ├── auth/           #   认证 (login/register/TOTP/password reset)
│   ├── chat/           #   聊天 (send/stream/file upload)
│   └── main/           #   首页/landing page
├── models/             # SQLAlchemy 数据模型
├── services/           # 业务逻辑 (agent_service, tools.py, sandbox.py)
├── utils/              # 工具函数 (crypto.py, settings.py, migrate_encrypt.py)
├── static/css/         # 样式 (style.css — 深色+浅色双主题)
└── templates/          # Jinja2 模板
    ├── admin/          #   管理后台页面 (10 个)
    ├── auth/           #   认证页面
    ├── chat/           #   聊天页面
    ├── errors/         #   错误页面
    └── main/           #   首页
skills/                 # Skill 扩展系统
├── calculator/         #   数学计算
├── db_operator/        #   数据库增查改
├── docx/               #   Word 文件处理
├── gen_image/          #   图片生成
├── get_date/           #   日期时间
├── kb_query/           #   RAG 知识库检索
├── markdown-format/    #   Markdown 格式化
├── memory_query/       #   记忆查询
├── memory_save/        #   记忆保存
├── ocr_reader/         #   图片 OCR
├── pdf/                #   PDF 处理（合并/拆分/创建/表格提取）
├── pdf_reader/         #   PDF 文本读取
├── pptx/               #   PowerPoint 处理
├── send_email/         #   邮件发送
├── skill_creator/      #   在线创建新 Skill
├── web_search/         #   网络搜索
└── xlsx/               #   Excel 处理
logs/                   # 日志文件（自动轮转）
uploads/                # 用户上传文件
chroma_data/            # ChromaDB 向量数据
sandbox/                # 代码执行沙箱
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | Flask 3.x |
| ORM | SQLAlchemy 2.x + Flask-Migrate |
| 数据库 | SQLite / MySQL (pymysql) |
| 前端 | Bootstrap 5.3 + FontAwesome 5 + marked.js |
| 向量数据库 | ChromaDB (PersistentClient) |
| AI 协议 | OpenAI 兼容 API |
| MCP 协议 | mcp Python SDK |
| 会话管理 | Flask-Login + Flask-WTF CSRF |
| 速率限制 | Flask-Limiter |
| 加密 | cryptography (Fernet) |
| 部署 | Waitress / Gunicorn / Docker |

## License

MIT
