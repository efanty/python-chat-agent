---
name: xlsx
description: Excel 文件处理 — 读取、创建、编辑 .xlsx 电子表格和 CSV 转换
parameters:
  - name: action
    type: string
    description: "操作: read(读取) / create(创建) / edit(编辑) / csv(CSV转xlsx)"
    enum: ["read", "create", "edit", "csv"]
    required: true
  - name: file_path
    type: string
    description: 文件路径（read/edit/csv 操作使用）
  - name: columns
    type: string
    description: "列名列表，JSON数组格式，如 [\"姓名\", \"年龄\", \"部门\"]（create 操作使用）"
  - name: rows
    type: string
    description: "数据行，JSON数组格式，如 [{\"姓名\": \"张三\", \"年龄\": \"28\", \"部门\": \"技术部\"}] 或 [[\"张三\", \"28\", \"技术部\"]]（create 操作使用）"
  - name: content
    type: string
    description: "表格内容（create 操作使用），CSV格式文本，第一行为列名，后续每行为数据行"
  - name: output
    type: string
    description: 输出文件名（create/edit/csv 操作使用，如 "report.xlsx"）
  - name: sheet_name
    type: string
    description: 工作表名称（可选，默认 Sheet1）
  - name: updates
    type: string
    description: "更新映射，JSON对象格式，如 {\"Sheet1\": {\"A1\": \"新值\", \"B2\": 123}}（edit 操作使用）"
  - name: delimiter
    type: string
    description: CSV分隔符（可选，默认逗号，csv 操作使用）
---

# XLSX Skill

对 Excel 电子表格进行读取、创建和编辑操作，返回 JSON 结果。

## Actions

### read
读取 .xlsx 文件数据。
- `file_path`: 文件路径
- `sheet`: 工作表名称（可选，默认返回所有工作表）
- 返回: `{"success": true, "sheets": {"Sheet1": {columns, rows, shape}}}`

### create
创建新电子表格。
- `columns`: 列名列表 `["col1", "col2"]`
- `rows`: 数据行 `[{"col1": "v1", "col2": "v2"}, ...]` 或 `[["v1", "v2"]]`
- `content`: 也可以用 CSV 格式文本代替 rows/columns，第一行为列名
- `sheet_name`: 工作表名称（可选，默认 Sheet1）
- `output`: 输出文件名（如 "output.xlsx"）
- 返回: `{"success": true, "output": "...", "rows": N}`

### edit
编辑现有电子表格。
- `file_path`: 文件路径
- `updates`: 更新映射 `{"Sheet1": {"A1": "value", "B2": 123}}`
- `output`: 输出路径

### csv
将 CSV/TSV 转换为 .xlsx。
- `file_path`: CSV 文件路径
- `delimiter`: 分隔符（可选，默认逗号）
- `output`: 输出路径

## 使用示例

### 创建 Excel 文件（推荐方式）
```json
{
  "action": "create",
  "columns": ["姓名", "年龄", "部门"],
  "rows": [
    {"姓名": "张三", "年龄": "28", "部门": "技术部"},
    {"姓名": "李四", "年龄": "32", "部门": "市场部"}
  ],
  "output": "员工信息.xlsx",
  "sheet_name": "员工表"
}
```

### 使用 CSV 文本创建
```json
{
  "action": "create",
  "content": "姓名,年龄,部门\n张三,28,技术部\n李四,32,市场部",
  "output": "员工信息.xlsx"
}
```

## 依赖

- `openpyxl`, `pandas`（内置于 requirements.txt）
