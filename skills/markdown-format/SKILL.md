---
name: markdown-format
description: Markdown 输出规范：确保输出格式正确渲染。
parameters:
  - name: expression
    type: string
    description: 要格式化的 Markdown 内容
    required: true
---

# Markdown 输出规范

## 强制规则

1. **标题**：前后各空一行
2. **列表**：`- ` 或 `1. ` 开头，标记后必须有空格
3. **嵌套列表**：前空一行
4. **表格**：仅数据稳定时使用，否则用列表
5. **代码块**：内部不嵌套 Markdown
6. **中文**：字符间不插多余空格

## 示例

### 正确

```markdown
## 标题

- 列表项1
- 列表项2
  - 嵌套项

1. 有序项1
2. 有序项2
```

### 错误

```markdown
## 标题
-列表项（缺空格）
-列表项2
```