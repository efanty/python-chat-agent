---
name: calculator
description: 执行数学计算和表达式求值
version: 1.0
author: DeepAgent Team
parameters:
  - name: expression
    type: string
    description: 数学表达式，如 1+2*3
    required: true
---

# Calculator Skill

执行数学计算和表达式求值。

## 能力

- 基本算术运算（加减乘除）
- 幂运算、取模
- 三角函数（sin, cos, tan）
- 数学常量（pi, e）
- 单位换算

## 使用方式

当用户需要数学计算时，使用 Python 的 `math` 模块执行计算。

```python
import math
result = eval(expression, {"__builtins__": {}}, {"math": math})
```

## 安全限制

- 仅允许使用 math 模块中的函数
- 禁止访问文件系统、网络、系统调用
- 表达式长度限制在 500 字符以内