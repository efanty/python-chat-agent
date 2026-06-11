---
name: self-improving
description: "Self-reflection + Self-criticism + Self-learning + Self-organizing memory. Agent evaluates its own work, catches mistakes, and improves permanently."
version: 1.0
author: DeepAgent Team
parameters:
  - name: action
    type: string
    description: "操作: review(反思) / improve(改进) / learn(学习)"
    enum: ["review", "improve", "learn", "reflect"]
    required: true
  - name: expression
    type: string
    description: 要反思或学习的内容
---

# Self-Improving Skill

智能体自我改进系统。通过记录用户纠正和自省，持续积累经验，在后续对话中避免重复错误。

## 能力

- **纠正学习**：用户指出错误时记录教训，下次不再犯
- **偏好学习**：记录用户的风格偏好和习惯
- **自省评估**：完成重要任务后自我评估，识别改进点
- **模式识别**：重复出现的指令自动识别为规则

## 工作机制

通过 `skill__memory_save` 和 `skill__memory_query` 持久化存储经验教训，不依赖外部文件。

### 学习信号

当出现以下情况时，自动记录到经验库：

**用户纠正** → 记录到 `lesson_` 前缀的记忆：
- "不是这样的…" / "应该是…"
- "你搞错了…" / "我之前说过…"
- "不要这样做…" / "为什么你老是…"

**偏好信号** → 记录到 `preferred_` 前缀的记忆：
- "我喜欢你…" / "我习惯…"
- "总是给我…" / "永远不要…"

**重复模式** → 同一条指令出现 3 次以上，确认为规则

### 自省评估

完成重要任务后，在思考中自我评估：

1. **是否达到预期？** — 对比结果与目标
2. **哪里可以更好？** — 识别下次可改进的点
3. **这是否是模式？** — 如果是，记录为经验

**自省时机：**
- 完成多步骤任务后
- 收到反馈（正面或负面）后
- 修正错误后

## 使用方式

使用 `skill__memory_save` 记录经验：
- key 格式：`lesson_{topic}` — 经验教训
- key 格式：`preferred_{topic}` — 用户偏好

使用 `skill__memory_query` 查询已有经验：
- 按 key 或关键词搜索
- 新对话开始时查询相关经验

## 存储规则

| 层级 | 位置 | 说明 |
|------|------|------|
| 热数据 | memory_save (lesson_/preferred_) | 随查询自动加载 |
| 冷数据 | memory_query 搜索 | 需要时按关键词查询 |

## 注意事项

- 不要从沉默中学习 — 只有明确的纠正才记录
- 不要过度泛化 — 区分一次性指令和长期规则
- 记录冲突时 — 最新的优先，更具体的优先