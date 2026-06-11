"""html-anything Skill — 生成精美的独立 HTML 页面。

根据用户内容和选定的模板风格，生成完整的单文件 HTML 页面，
保存到 sandbox 目录供用户下载。
"""

import json
import os
import uuid
import datetime

_ACTION_DESCRIPTION = "HTML 页面生成"

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_SANDBOX_BASE = None  # resolved on first call


def _resolve_sandbox():
    """Resolve the project sandbox directory."""
    global _SANDBOX_BASE
    if _SANDBOX_BASE is None:
        # sandbox 在项目根目录下: {project_root}/sandbox/
        # skill 在 skills/html-anything/ 下，需要向上两级
        _SANDBOX_BASE = os.path.normpath(
            os.path.abspath(os.path.join(_SKILL_DIR, '..', '..', 'sandbox'))
        )
        os.makedirs(_SANDBOX_BASE, exist_ok=True)
    return _SANDBOX_BASE


def _save_html(html_content: str, filename: str = "", user_id=None) -> str:
    """Save HTML content to sandbox and return download path."""
    sandbox_dir = _resolve_sandbox()
    if user_id:
        user_dir = os.path.join(sandbox_dir, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        save_dir = user_dir
    else:
        save_dir = sandbox_dir

    if not filename:
        filename = f"page_{uuid.uuid4().hex[:12]}.html"
    if not filename.endswith('.html'):
        filename += '.html'

    # 防止路径穿越
    safe_name = os.path.basename(filename)
    filepath = os.path.join(save_dir, safe_name)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    # 如果文件保存在 user_id 子目录下，URL 中需要包含用户 ID
    if user_id:
        return f"/chat/sandbox/{user_id}/{safe_name}"
    return f"/chat/sandbox/{safe_name}"


# ── Template Data ─────────────────────────────────────────────────────────

_TEMPLATES = {
    "prototype-web": {"category": "网页原型", "description": "通用 Web 原型，Hero/Features/CTA/Footer"},
    "saas-landing":  {"category": "网页原型", "description": "SaaS 落地页，导航/定价/客户评价"},
    "dashboard":     {"category": "网页原型", "description": "管理后台/数据分析面板"},
    "pricing-page":  {"category": "网页原型", "description": "多套餐定价页"},
    "docs-page":     {"category": "网页原型", "description": "技术文档页面"},
    "blog-post":     {"category": "文章", "description": "长篇文章/博客"},
    "article-magazine": {"category": "文章", "description": "杂志风格文章"},
    "resume-modern": {"category": "文档", "description": "现代简历（A4 格式）"},
    "data-report":   {"category": "文档", "description": "CSV/数据 → 可视化数据报告"},
    "meeting-notes": {"category": "文档", "description": "会议记录/决策日志"},
    "weekly-update": {"category": "文档", "description": "团队周报"},
    "pm-spec":       {"category": "文档", "description": "产品需求文档"},
    "social-x-post-card": {"category": "社交", "description": "X/Twitter 引语卡片"},
    "card-xiaohongshu":   {"category": "社交", "description": "小红书图文卡片"},
    "social-carousel":    {"category": "社交", "description": "三页轮播图"},
    "deck-simple":        {"category": "演示", "description": "简洁幻灯片"},
    "deck-pitch":         {"category": "演示", "description": "投资人演示"},
    "deck-tech-sharing":  {"category": "演示", "description": "技术分享演示"},
}

_CATEGORIES = {}
for name, info in _TEMPLATES.items():
    cat = info["category"]
    if cat not in _CATEGORIES:
        _CATEGORIES[cat] = []
    _CATEGORIES[cat].append(name)


# ── Template Guide (returned by get_template) ─────────────────────────────

_TEMPLATE_GUIDES = {
    "prototype-web": """【HTML 模板: Web 产品原型】
风格: 现代 SaaS，柔和渐变，大字号
配色: 主色 #6366f1 (indigo)，辅色 #ec4899 (pink)，灰阶 #f8fafc / #1e293b
字体: Inter / Noto Sans SC
布局: Top Nav → Hero (双 CTA) → Features (3-6卡片) → How it works → CTA → Footer
交互: nav 滚动变色，卡片 hover 浮起，FAQ 手风琴
响应式: md 断点，移动端单栏""",

    "saas-landing": """【HTML 模板: SaaS 落地页】
风格: 企业级 SaaS，信任感设计
配色: 主色 #2563eb (blue)，辅色 #10b981 (emerald)
字体: Inter / Noto Sans SC
布局: Nav → Hero → Logos → Features → Testimonials → Pricing → FAQ → CTA → Footer
交互: 平滑滚动，轮播评价
响应式: 全端适配""",

    "dashboard": """【HTML 模板: 管理后台】
风格: 深色侧栏+浅色内容区
配色: 侧栏 #1e293b，内容 #f1f5f9，主色 #3b82f6
字体: Inter / Noto Sans SC
布局: 左侧导航 → 顶栏(搜索/用户) → KPI卡片 → 图表区 → 最近活动
组件: 数据表格，状态徽标，进度条
响应式: 移动端折叠侧栏""",

    "pricing-page": """【HTML 模板: 定价页】
风格: 三栏对比
配色: 主色 #8b5cf6 (violet)，推荐套餐高亮边框
字体: Inter / Noto Sans SC
布局: Header → 切换(月/年) → 三栏卡片(基础/专业/企业) → FAQ → Footer
组件: 价格卡片，功能列表，推荐标签
交互: 卡片 hover 上浮""",

    "docs-page": """【HTML 模板: 技术文档】
风格: 左侧导航 + 右侧内容 + 右侧目录
配色: #f8fafc 背景，#334155 正文
字体: Inter / Noto Sans SC / JetBrains Mono (代码)
布局: 侧栏(TOC) → 主内容 → 右侧锚点导航
组件: 代码块，警告框，表格，图表
响应式: 移动端隐藏侧栏""",

    "blog-post": """【HTML 模板: 博客文章】
风格: 清晰可读，专注内容
配色: 白底 #ffffff，正文 #374151，强调 #2563eb
字体: Merriweather / Noto Serif SC (标题)，Inter / Noto Sans SC (正文)
布局: 题图 → 标题/元数据 → 正文 → 分享 → 评论区
组件: 引用块，图片，代码块，标签
响应式: 最大宽度 720px 阅读区""",

    "article-magazine": """【HTML 模板: 杂志文章】
风格: 暖色调，羊皮纸质感
配色: 背景 #f5f4ed，正文 #3d3d3d，强调色 #8b4513
字体: Playfair Display / Noto Serif SC (标题)，Georgia / Noto Serif SC (正文)
布局: 跨栏标题 → 首字下沉 → 双栏正文 → 侧栏引语
组件: 拉引语(pull quote)，侧栏注释，分隔线
响应式: 移动端单栏""",

    "resume-modern": """【HTML 模板: 简历】
风格: 极简，A4 210×297mm
配色: 白底 #ffffff，主色 #1e40af，正文 #475569
字体: Inter / Noto Sans SC
布局: 左侧栏(联系/技能/教育) → 右侧栏(简介/经历/项目)
组件: 时间线，技能条，项目卡片
打印: @media print 优化，A4 尺寸""",

    "data-report": """【HTML 模板: 数据报告】
风格: 数据驱动，可视化优先
配色: 深色 #0f172a 背景，图表色 #3b82f6/#10b981/#f59e0b
字体: Inter / Noto Sans SC
布局: 标题区 → KPI 指标行 → 图表(条形/折线/饼图) → 数据表格 → 结论
组件: CSS 图表(无JS依赖)，数据表格，趋势指示器
响应式: 图表移动端堆叠""",

    "meeting-notes": """【HTML 模板: 会议记录】
风格: 简洁，结构化
配色: #f0fdf4 浅绿背景，#166534 深绿强调
字体: Inter / Noto Sans SC
布局: 标题(日期/与会者) → 议程 → 讨论摘要 → 决策项 → 待办 → 下次会议
组件: 待办复选框，决策标签
交互: 无特殊交互""",

    "weekly-update": """【HTML 模板: 团队周报】
风格: 清晰，数据驱动
配色: #f8fafc 背景，#0f172a 标题
字体: Inter / Noto Sans SC
布局: 头部(周次/团队) → 关键指标(KPI) → 完成项 → 进行中 → 阻塞项 → 下周计划
组件: 数字徽标，进度指示器，标签
交互: 无特殊交互""",

    "pm-spec": """【HTML 模板: 产品需求文档】
风格: 严谨，层次分明
配色: #ffffff 背景，#1e293b 正文，#0891b2 强调
字体: Inter / Noto Sans SC
布局: 标题/元数据 → 背景 → 目标 → 范围 → 功能列表 → 验收标准 → 决策日志
组件: 表格，优先级标签，状态标记
响应式: 文档宽版""",

    "social-x-post-card": """【HTML 模板: X/Twitter 卡片】
尺寸: 1600×900
风格: 大引语，品牌色强调
配色: 白底或黑底，#1d9bf0 X 蓝
字体: Inter / Noto Sans SC
布局: 引语(大字号) → 来源/头像 → 品牌底部
组件: 头像圆形裁剪，引号装饰
交互: 纯展示无交互""",

    "card-xiaohongshu": """【HTML 模板: 小红书卡片】
尺寸: 1080×1350 (竖版)
风格: 柔和，温暖，奶油色
配色: #fef9ef 背景，#d97706 暖橙强调
字体: Noto Serif SC / Noto Sans SC
布局: 标题图 → 标题 → 正文 → 标签 → 底部
组件: 渐变背景，圆角卡片，标签云
交互: 纯展示无交互""",

    "social-carousel": """【HTML 模板: 三页轮播图】
尺寸: 1080×1080 三页
风格: 现代，渐变色过渡
配色: 第一页 #667eea→#764ba2，第二页 #f093fb→#f5576c，第三页 #4facfe→#00f2fe
字体: Inter / Noto Sans SC
布局: 封面 → 内容页 → 结尾CTA
组件: 渐变背景，大数字页码指示器
交互: 纯展示无交互""",

    "deck-simple": """【HTML 模板: 简洁幻灯片】
风格: 极简，大留白
配色: 白底 #ffffff，#1e293b 正文，#6366f1 强调
字体: Inter / Noto Sans SC
布局: 封面 → 多个内容幻灯片(← → 切换) → 结尾
交互: 键盘 ← → 切换，底部页码
组件: slide 容器，导航点
响应式: 视口 100vw×100vh""",

    "deck-pitch": """【HTML 模板: 投资人演示】
风格: 高端，暗色奢华
配色: 深色 #0a0a0a 背景，#d4d4d8 正文，#f59e0b 金色强调
字体: Inter / Noto Sans SC
布局: 封面(大标题+副标题) → 问题 → 方案 → 市场 → 商业模式 → 团队 → 融资
交互: ← → 切换，进度条，演讲备注
组件: 大数字统计数据，时间线""",

    "deck-tech-sharing": """【HTML 模板: 技术分享演示】
风格: 深色科技感
配色: #0f172a 背景，#38bdf8 青色强调
字体: JetBrains Mono (代码) / Inter / Noto Sans SC
布局: 封面 → 目录 → 多个技术 slide → 代码示例 → 结尾
交互: ← → 切换，代码高亮
组件: 代码块(深色主题)，架构图占位，列表动画""",
}


# ── HTML Generator ────────────────────────────────────────────────────────

def _wrap_html(title: str, body_html: str, extra_css: str = "", dark_mode: bool = False) -> str:
    """Wrap body HTML in a complete HTML document."""
    bg_color = "#0f172a" if dark_mode else "#ffffff"
    text_color = "#f1f5f9" if dark_mode else "#1e293b"
    link_color = "#60a5fa" if dark_mode else "#2563eb"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_html(title)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-size: 16px; scroll-behavior: smooth; }}
  body {{
    font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, sans-serif;
    background: {bg_color};
    color: {text_color};
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  a {{ color: {link_color}; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  img {{ max-width: 100%; height: auto; }}
  {extra_css}
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
</head>
<body>
{body_html}
</body>
</html>"""


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def _content_to_html(content: str) -> str:
    """Simple markdown-like content to HTML conversion."""
    if not content:
        return ""
    lines = content.split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue
        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2>{_escape_html(stripped[3:])}</h2>')
        elif stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h3>{_escape_html(stripped[4:])}</h3>')
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f'<li>{_escape_html(stripped[2:])}</li>')
        elif stripped[0].isdigit() and ". " in stripped[:4]:
            if not in_list:
                html_parts.append("<ol>")
                in_list = True
            html_parts.append(f'<li>{_escape_html(stripped.split(". ", 1)[1])}</li>')
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p>{_escape_html(stripped)}</p>')
    if in_list:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


# ── Template Generators ───────────────────────────────────────────────────

def _gen_prototype_web(title: str, content_html: str) -> str:
    body = f"""<nav style="position:fixed;top:0;width:100%;background:rgba(255,255,255,0.95);backdrop-filter:blur(8px);z-index:100;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #e2e8f0;">
  <span style="font-weight:700;font-size:1.25rem;color:#6366f1;">{_escape_html(title)}</span>
  <div style="display:flex;gap:1.5rem;align-items:center;">
    <a href="#" style="color:#475569;">特性</a>
    <a href="#" style="color:#475569;">价格</a>
    <a href="#" style="color:#475569;">关于</a>
    <a href="#" style="background:#6366f1;color:#fff;padding:0.5rem 1.25rem;border-radius:0.5rem;font-weight:500;">开始使用</a>
  </div>
</nav>
<section style="padding:8rem 2rem 4rem;text-align:center;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;min-height:80vh;display:flex;flex-direction:column;justify-content:center;">
  <h1 style="font-size:3.5rem;font-weight:800;margin-bottom:1rem;line-height:1.2;">{_escape_html(title)}</h1>
  <p style="font-size:1.25rem;max-width:640px;margin:0 auto 2rem;opacity:0.9;">{_escape_html(content_html[:120])}</p>
  <div style="display:flex;gap:1rem;justify-content:center;">
    <a href="#" style="background:#fff;color:#6366f1;padding:0.75rem 2rem;border-radius:0.5rem;font-weight:600;">免费试用</a>
    <a href="#" style="border:2px solid rgba(255,255,255,0.5);color:#fff;padding:0.75rem 2rem;border-radius:0.5rem;font-weight:600;">了解更多</a>
  </div>
</section>
<section style="padding:4rem 2rem;max-width:1200px;margin:0 auto;">
  <h2 style="text-align:center;font-size:2rem;margin-bottom:3rem;">核心特性</h2>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:2rem;">
    {_gen_feature_card("🎯", "智能分析", "基于 AI 的深度数据分析，自动发现业务洞察")}
    {_gen_feature_card("⚡", "极速响应", "毫秒级响应时间，7×24 小时稳定运行")}
    {_gen_feature_card("🔒", "安全可靠", "企业级安全加密，SOC2 认证保障数据安全")}
    {_gen_feature_card("📊", "可视化", "丰富的图表组件，数据一目了然")}
    {_gen_feature_card("🔗", "无缝集成", "支持 50+ 第三方工具集成")}
    {_gen_feature_card("📱", "多端适配", "桌面端、移动端、平板完美适配")}
  </div>
</section>
<section style="background:#f8fafc;padding:4rem 2rem;text-align:center;">
  <h2 style="font-size:2rem;margin-bottom:1rem;">准备好开始了吗？</h2>
  <p style="color:#64748b;margin-bottom:2rem;">无需信用卡，立即开始使用</p>
  <a href="#" style="background:#6366f1;color:#fff;padding:0.75rem 2rem;border-radius:0.5rem;font-weight:600;font-size:1.125rem;">立即开始</a>
</section>
<footer style="background:#1e293b;color:#94a3b8;padding:2rem;text-align:center;font-size:0.875rem;">
  &copy; 2025 {_escape_html(title)}. All rights reserved.
</footer>"""
    return _wrap_html(title, body)


def _gen_feature_card(emoji: str, title: str, desc: str) -> str:
    return f"""<div style="background:#fff;border-radius:1rem;padding:2rem;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);transition:box-shadow 0.3s;" onmouseover="this.style.boxShadow='0 20px 25px -5px rgba(0,0,0,0.1)'" onmouseout="this.style.boxShadow='0 4px 6px -1px rgba(0,0,0,0.1)'">
  <div style="font-size:2.5rem;margin-bottom:1rem;">{emoji}</div>
  <h3 style="font-size:1.25rem;margin-bottom:0.5rem;color:#1e293b;">{_escape_html(title)}</h3>
  <p style="color:#64748b;font-size:0.875rem;">{_escape_html(desc)}</p>
</div>"""


def _gen_blog_post(title: str, content_html: str) -> str:
    body = f"""<article style="max-width:720px;margin:0 auto;padding:2rem 1.5rem;">
  <header style="margin-bottom:2rem;">
    <h1 style="font-size:2.5rem;font-weight:800;line-height:1.3;margin-bottom:0.5rem;">{_escape_html(title)}</h1>
    <div style="color:#94a3b8;font-size:0.875rem;">{datetime.date.today().isoformat()} · 预计阅读 5 分钟</div>
  </header>
  <div style="font-size:1.125rem;line-height:1.8;color:#374151;">
    {content_html}
  </div>
  <footer style="margin-top:3rem;padding-top:2rem;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:0.875rem;">
    感谢阅读！欢迎分享这篇文章。
  </footer>
</article>"""
    extra_css = """article p { margin-bottom: 1.5rem; }
article h2 { font-size: 1.75rem; margin: 2rem 0 1rem; color: #1e293b; }
article h3 { font-size: 1.375rem; margin: 1.5rem 0 0.75rem; color: #334155; }
article ul, article ol { margin: 0 0 1.5rem 1.5rem; }
article li { margin-bottom: 0.5rem; }
article blockquote { border-left: 4px solid #2563eb; padding: 0.5rem 1rem; margin: 1.5rem 0; background: #f8fafc; border-radius: 0 0.5rem 0.5rem 0; }
article code { background: #f1f5f9; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.875rem; }"""
    return _wrap_html(title, body, extra_css)


def _gen_resume(title: str, content_html: str) -> str:
    body = f"""<div style="max-width:794px;margin:2rem auto;background:#fff;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);display:grid;grid-template-columns:1fr 2fr;min-height:1123px;">
  <div style="background:#1e40af;color:#fff;padding:2rem;">
    <h1 style="font-size:1.5rem;margin-bottom:0.5rem;">{_escape_html(title)}</h1>
    <div style="font-size:0.875rem;opacity:0.8;margin-bottom:2rem;">全栈开发工程师</div>
    <h3 style="font-size:0.875rem;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:1rem;opacity:0.7;">联系方式</h3>
    <div style="font-size:0.875rem;margin-bottom:2rem;opacity:0.9;">
      📧 email@example.com<br>📱 +86 138-0000-0000<br>📍 Beijing, China
    </div>
    <h3 style="font-size:0.875rem;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:1rem;opacity:0.7;">技能</h3>
    <div style="font-size:0.875rem;opacity:0.9;">
      <div style="margin-bottom:0.5rem;">Python <span style="float:right;">★★★★★</span></div>
      <div style="margin-bottom:0.5rem;">JavaScript <span style="float:right;">★★★★☆</span></div>
      <div style="margin-bottom:0.5rem;">React <span style="float:right;">★★★★☆</span></div>
      <div style="margin-bottom:0.5rem;">Docker <span style="float:right;">★★★☆☆</span></div>
    </div>
  </div>
  <div style="padding:2rem;color:#475569;">
    <h2 style="font-size:1.125rem;color:#1e40af;border-bottom:2px solid #1e40af;padding-bottom:0.5rem;margin-bottom:1rem;">个人简介</h2>
    <p style="font-size:0.875rem;line-height:1.6;margin-bottom:2rem;">{_escape_html(content_html[:200])}</p>
    <h2 style="font-size:1.125rem;color:#1e40af;border-bottom:2px solid #1e40af;padding-bottom:0.5rem;margin-bottom:1rem;">工作经历</h2>
    <div style="margin-bottom:1.5rem;">
      <div style="font-weight:600;font-size:0.9375rem;">高级工程师 — 某科技公司</div>
      <div style="font-size:0.8125rem;color:#94a3b8;">2022-01 — 至今</div>
      <ul style="font-size:0.875rem;margin-top:0.5rem;padding-left:1.25rem;">
        <li>负责核心业务系统架构设计与开发</li>
        <li>带领 5 人团队完成平台迁移</li>
      </ul>
    </div>
  </div>
</div>"""
    return _wrap_html(title, body)


def _gen_social_x_card(title: str, content_html: str) -> str:
    quote = content_html[:200] if content_html else "精彩内容"
    body = f"""<div style="width:1600px;height:900px;background:#fff;display:flex;flex-direction:column;justify-content:center;padding:4rem;position:relative;">
  <div style="font-size:4rem;color:#1d9bf0;margin-bottom:0.5rem;">"</div>
  <div style="font-size:3rem;font-weight:700;line-height:1.3;color:#0f1419;margin-bottom:2rem;">{_escape_html(quote)}</div>
  <div style="display:flex;align-items:center;gap:1rem;">
    <div style="width:3.5rem;height:3.5rem;border-radius:50%;background:#1d9bf0;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:1.5rem;">{_escape_html(title[:1])}</div>
    <div>
      <div style="font-weight:700;font-size:1.25rem;">{_escape_html(title)}</div>
      <div style="color:#536471;">@{_escape_html(title.lower().replace(' ',''))}</div>
    </div>
  </div>
  <div style="position:absolute;bottom:2rem;right:2rem;color:#1d9bf0;font-weight:700;">𝕏</div>
</div>"""
    return _wrap_html(title, body)


def _gen_data_report(title: str, content_html: str) -> str:
    body = f"""<div style="max-width:1000px;margin:0 auto;padding:2rem;background:#0f172a;color:#f1f5f9;min-height:100vh;">
  <header style="margin-bottom:2rem;text-align:center;">
    <h1 style="font-size:2rem;font-weight:700;color:#f8fafc;">{_escape_html(title)}</h1>
    <p style="color:#94a3b8;">{datetime.date.today().isoformat()}</p>
  </header>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:2rem;">
    <div style="background:#1e293b;padding:1.5rem;border-radius:0.75rem;text-align:center;">
      <div style="font-size:0.75rem;text-transform:uppercase;color:#94a3b8;">总营收</div>
      <div style="font-size:1.5rem;font-weight:700;color:#3b82f6;">¥2.4M</div>
    </div>
    <div style="background:#1e293b;padding:1.5rem;border-radius:0.75rem;text-align:center;">
      <div style="font-size:0.75rem;text-transform:uppercase;color:#94a3b8;">增长率</div>
      <div style="font-size:1.5rem;font-weight:700;color:#10b981;">+23%</div>
    </div>
    <div style="background:#1e293b;padding:1.5rem;border-radius:0.75rem;text-align:center;">
      <div style="font-size:0.75rem;text-transform:uppercase;color:#94a3b8;">活跃用户</div>
      <div style="font-size:1.5rem;font-weight:700;color:#f59e0b;">45.2K</div>
    </div>
    <div style="background:#1e293b;padding:1.5rem;border-radius:0.75rem;text-align:center;">
      <div style="font-size:0.75rem;text-transform:uppercase;color:#94a3b8;">转化率</div>
      <div style="font-size:1.5rem;font-weight:700;color:#8b5cf6;">3.2%</div>
    </div>
  </div>
  <div style="background:#1e293b;padding:1.5rem;border-radius:0.75rem;margin-bottom:2rem;">
    <h3 style="font-size:1rem;margin-bottom:1rem;color:#f8fafc;">月度趋势</h3>
    <div style="display:flex;gap:0.5rem;align-items:flex-end;height:200px;padding-top:1rem;">
      {''.join(f'<div style="flex:1;height:{h}px;background:linear-gradient(to top,#3b82f6,#60a5fa);border-radius:0.25rem 0.25rem 0 0;position:relative;"><span style="position:absolute;top:-1.25rem;left:50%;transform:translateX(-50%);font-size:0.75rem;color:#94a3b8;">{v}</span></div>' for h, v in [(60,'1.2'),(80,'1.8'),(100,'2.2'),(140,'3.1'),(120,'2.8'),(180,'4.0'),(160,'3.5'),(200,'4.5'),(170,'3.8'),(190,'4.2'),(150,'3.3'),(130,'2.9')])}
    </div>
    <div style="display:flex;gap:0.5rem;margin-top:0.25rem;">
      {''.join(f'<div style="flex:1;text-align:center;font-size:0.7rem;color:#64748b;">{m}</div>' for m in ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'])}
    </div>
  </div>
  <div style="background:#1e293b;padding:1rem;border-radius:0.75rem;font-size:0.875rem;color:#cbd5e1;">
    <strong style="color:#f8fafc;">{_escape_html(content_html[:500])}</strong>
  </div>
</div>"""
    return _wrap_html(title, body, dark_mode=True)


def _gen_meeting_notes(title: str, content_html: str) -> str:
    body = f"""<div style="max-width:800px;margin:2rem auto;background:#f0fdf4;padding:2rem;border-radius:1rem;border:1px solid #bbf7d0;">
  <h1 style="font-size:1.5rem;color:#166534;margin-bottom:0.5rem;">{_escape_html(title)}</h1>
  <div style="color:#15803d;font-size:0.875rem;margin-bottom:2rem;">{datetime.date.today().isoformat()} | 会议室 A</div>
  <div style="margin-bottom:1.5rem;padding:1rem;background:#dcfce7;border-radius:0.5rem;">
    <strong style="color:#166534;">与会者:</strong> <span style="color:#374151;">张三, 李四, 王五, 赵六</span>
  </div>
  <h2 style="font-size:1.125rem;color:#166534;border-bottom:2px solid #86efac;padding-bottom:0.5rem;margin-bottom:1rem;">议程</h2>
  <ol style="margin:0 0 1.5rem 1.25rem;color:#374151;">
    <li style="margin-bottom:0.5rem;">回顾上周进展</li>
    <li style="margin-bottom:0.5rem;">讨论当前阻塞项</li>
    <li style="margin-bottom:0.5rem;">确定下周优先级</li>
  </ol>
  <h2 style="font-size:1.125rem;color:#166534;border-bottom:2px solid #86efac;padding-bottom:0.5rem;margin-bottom:1rem;">讨论摘要</h2>
  <div style="color:#374151;line-height:1.6;">{content_html}</div>
  <h2 style="font-size:1.125rem;color:#166534;border-bottom:2px solid #86efac;padding-bottom:0.5rem;margin:1.5rem 0 1rem;">待办事项</h2>
  <div style="display:grid;gap:0.5rem;">
    <div style="background:#dcfce7;padding:0.75rem;border-radius:0.5rem;display:flex;align-items:center;gap:0.5rem;">
      <input type="checkbox" style="accent-color:#166534;"> 完成项目方案 (张三)
    </div>
    <div style="background:#dcfce7;padding:0.75rem;border-radius:0.5rem;display:flex;align-items:center;gap:0.5rem;">
      <input type="checkbox" style="accent-color:#166534;"> 准备演示文稿 (李四)
    </div>
    <div style="background:#dcfce7;padding:0.75rem;border-radius:0.5rem;display:flex;align-items:center;gap:0.5rem;">
      <input type="checkbox" style="accent-color:#166534;"> 确认供应商报价 (王五)
    </div>
  </div>
</div>"""
    return _wrap_html(title, body)


def _gen_deck_simple(title: str, content_html: str) -> str:
    slides = content_html.split("\n\n") if content_html else ["内容页"]
    slide_html = ""
    for i, slide in enumerate(slides):
        slide_html += f"""<section class="slide" style="display:flex;flex-direction:column;justify-content:center;align-items:center;width:100vw;height:100vh;padding:4rem;text-align:center;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;" {"id=slide-"+str(i) if i > 0 else 'id="slide-0"'}>
  {f'<h1 style="font-size:3.5rem;font-weight:800;margin-bottom:1rem;">{_escape_html(title)}</h1><p style="font-size:1.25rem;opacity:0.8;">副标题</p>' if i == 0 else f'<h1 style="font-size:2.5rem;font-weight:700;">{_escape_html(slide.strip()[:80])}</h1>'}
</section>"""

    total = len(slides)
    body = f"""<main style="overflow:hidden;position:relative;">
  {slide_html}
</main>
<div id="counter" style="position:fixed;bottom:2rem;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.3);color:#fff;padding:0.5rem 1rem;border-radius:2rem;font-size:0.875rem;z-index:100;">1 / {total}</div>
<script>
let i=0, s=document.querySelectorAll('.slide');
document.addEventListener('keydown',function(e){{
  if(e.key==='ArrowRight'||e.key==='ArrowDown'){{if(i<s.length-1){{i++;s[i].scrollIntoView({behavior:'smooth'});document.getElementById('counter').textContent=(i+1)+' / '+s.length;}}}}
  if(e.key==='ArrowLeft'||e.key==='ArrowUp'){{if(i>0){{i--;s[i].scrollIntoView({behavior:'smooth'});document.getElementById('counter').textContent=(i+1)+' / '+s.length;}}}}
}});
</script>"""
    return _wrap_html(title, body)


def _gen_pm_spec(title: str, content_html: str) -> str:
    body = f"""<div style="max-width:900px;margin:2rem auto;padding:2rem;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.1);border-radius:0.5rem;">
  <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:2rem;">
    <div>
      <h1 style="font-size:1.75rem;font-weight:700;color:#1e293b;">{_escape_html(title)}</h1>
      <p style="color:#64748b;font-size:0.875rem;">PRD · {datetime.date.today().isoformat()} · v1.0</p>
    </div>
    <span style="background:#0891b2;color:#fff;padding:0.25rem 0.75rem;border-radius:1rem;font-size:0.75rem;">进行中</span>
  </div>
  <h2 style="font-size:1.125rem;color:#0891b2;border-bottom:2px solid #0891b2;padding-bottom:0.5rem;margin-bottom:1rem;">背景</h2>
  <p style="color:#475569;line-height:1.6;margin-bottom:2rem;">{_escape_html(content_html[:300])}</p>
  <h2 style="font-size:1.125rem;color:#0891b2;border-bottom:2px solid #0891b2;padding-bottom:0.5rem;margin-bottom:1rem;">目标</h2>
  <ul style="color:#475569;margin:0 0 2rem 1.25rem;">
    <li style="margin-bottom:0.5rem;">提升用户转化率 20%</li>
    <li style="margin-bottom:0.5rem;">减少页面加载时间 50%</li>
    <li style="margin-bottom:0.5rem;">支持 10 万并发用户</li>
  </ul>
  <h2 style="font-size:1.125rem;color:#0891b2;border-bottom:2px solid #0891b2;padding-bottom:0.5rem;margin-bottom:1rem;">范围</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:2rem;">
    <div style="background:#f0fdf4;padding:1rem;border-radius:0.5rem;">
      <strong style="color:#166534;">包含</strong>
      <ul style="font-size:0.875rem;color:#374151;margin-top:0.5rem;padding-left:1rem;">
        <li>用户认证系统</li>
        <li>数据仪表盘</li>
        <li>API 接口</li>
      </ul>
    </div>
    <div style="background:#fef2f2;padding:1rem;border-radius:0.5rem;">
      <strong style="color:#991b1b;">不包含</strong>
      <ul style="font-size:0.875rem;color:#374151;margin-top:0.5rem;padding-left:1rem;">
        <li>移动端 App</li>
        <li>第三方集成</li>
      </ul>
    </div>
  </div>
  <div style="background:#f8fafc;padding:1rem;border-radius:0.5rem;font-size:0.875rem;color:#64748b;">
    <strong>决策日志:</strong> 2025-01-15 — 确定使用 React + FastAPI 技术栈
  </div>
</div>"""
    return _wrap_html(title, body)


# ── Generator Dispatch ────────────────────────────────────────────────────

_GENERATORS = {
    "prototype-web": _gen_prototype_web,
    "blog-post": _gen_blog_post,
    "resume-modern": _gen_resume,
    "social-x-post-card": _gen_social_x_card,
    "data-report": _gen_data_report,
    "meeting-notes": _gen_meeting_notes,
    "deck-simple": _gen_deck_simple,
    "pm-spec": _gen_pm_spec,
    # Aliases
    "saas-landing": _gen_prototype_web,
    "article-magazine": _gen_blog_post,
    "weekly-update": _gen_meeting_notes,
    "deck-pitch": _gen_deck_simple,
    "deck-tech-sharing": _gen_deck_simple,
}


# ── Public API ────────────────────────────────────────────────────────────

def list_templates(**kwargs) -> str:
    """列出所有可用模板。"""
    lines = ["可用 HTML 模板列表:", ""]
    for cat in sorted(_CATEGORIES.keys()):
        lines.append(f"  【{cat}】")
        for name in sorted(_CATEGORIES[cat]):
            info = _TEMPLATES[name]
            lines.append(f"    {name:25s} {info['description']}")
        lines.append("")
    return "\n".join(lines)


def list_categories(**kwargs) -> str:
    """列出模板分类。"""
    cats = [f"  · {cat} ({len(templates)} 个模板)" for cat, templates in sorted(_CATEGORIES.items())]
    return "模板分类:\n" + "\n".join(cats)


def get_template(template: str = "prototype-web", **kwargs) -> str:
    """获取指定模板的设计指南。"""
    if template not in _TEMPLATES:
        available = ", ".join(sorted(_TEMPLATES.keys()))
        return f"未知模板: {template}。可用模板: {available}"
    info = _TEMPLATES[template]
    guide = _TEMPLATE_GUIDES.get(template, "")
    return (f"模板: {template}\n"
            f"分类: {info['category']}\n"
            f"说明: {info['description']}\n\n"
            f"设计指南:\n{guide}\n\n"
            f"提示: 将设计指南中的约束和风格应用到生成的 HTML 中。")


def generate(template: str = "prototype-web", content: str = "",
             title: str = "", filename: str = "",
             dark_mode: bool = False, **kwargs) -> str:
    """根据模板生成 HTML 文件。

    Args:
        template: 模板名称
        content: 用户提供的内容 (Markdown/文本)
        title: 页面标题
        filename: 自定义文件名
        dark_mode: 是否深色主题
    """
    if template not in _GENERATORS:
        # Fall back to prototype-web if unknown
        if template in _TEMPLATES:
            # Known template but no generator yet - return guide
            guide = _TEMPLATE_GUIDES.get(template, _TEMPLATES[template]["description"])
            return (f"模板 '{template}' 尚无内置生成器。\n"
                    f"设计指南如下，请 LLM 根据此指南生成 HTML：\n\n{guide}")
        available = ", ".join(sorted(_GENERATORS.keys()))
        return f"未知模板: {template}。当前支持的模板: {available}"

    if not title:
        title = template.replace("-", " ").title()
    content_html = _content_to_html(content)

    generator = _GENERATORS[template]
    html_content = generator(title, content_html)

    # Save to sandbox
    user_id = kwargs.get("_user_id")
    download_path = _save_html(html_content, filename, user_id)

    return (f"成功生成 HTML 文件\n"
            f"模板: {template}\n"
            f"标题: {title}\n"
            f"文件大小: {len(html_content)} 字节\n"
            f"下载地址: {download_path}\n\n"
            f"您可以在回复中提供下载链接：\n"
            f"[下载 HTML 文件]({download_path})")


def run(expression: str = "", action: str = "", **kwargs) -> str:
    """HTML 生成入口。

    Args:
        action: 操作类型 (list_templates / list_categories / get_template / generate)
        template: 模板名称
        content: 用户内容
        title: 页面标题
        filename: 自定义文件名
        dark_mode: 深色模式
    """
    params = {}
    if expression and expression.strip().startswith("{"):
        try:
            params = json.loads(expression)
        except json.JSONDecodeError:
            pass

    action = params.get("action") or action or kwargs.get("action", "")
    template = params.get("template") or kwargs.get("template", "prototype-web")
    content = params.get("content") or kwargs.get("content", "")
    title = params.get("title") or kwargs.get("title", "")
    filename = params.get("filename") or kwargs.get("filename", "")
    dark_mode = params.get("dark_mode") or kwargs.get("dark_mode", False)

    try:
        if action == "list_templates":
            return list_templates(**kwargs)
        elif action == "list_categories":
            return list_categories(**kwargs)
        elif action == "get_template":
            return get_template(template=template, **kwargs)
        elif action == "generate":
            return generate(
                template=template, content=content, title=title,
                filename=filename, dark_mode=dark_mode, **kwargs)
        else:
            return ("HTML 生成工具 (html-anything)\n"
                    "用法: run(action='操作类型', ...)\n\n"
                    "支持的操作:\n"
                    "  list_templates    — 列出可用模板\n"
                    "  list_categories   — 列出模板分类\n"
                    "  get_template      — 获取模板设计指南（需 template）\n"
                    "  generate          — 生成 HTML 文件（需 template + content）\n\n"
                    "示例:\n"
                    "  run(action='list_templates')\n"
                    "  run(action='generate', template='prototype-web', title='我的产品', content='## 特性1\\n描述...')")
    except FileNotFoundError as e:
        return json.dumps({"success": False, "error": str(e)})
    except Exception as e:
        return json.dumps({"success": False, "error": f"错误: {e}"})
