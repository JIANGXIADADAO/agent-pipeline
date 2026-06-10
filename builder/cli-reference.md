# Agent Pipeline — CLI 参考

> CLI 工具 `agent-pipeline` 的完整命令参考（Phase 2）。
> 五 Agent 流水线：Scout → Designer → Builder → Tester → Seller

---

## 全局选项

| 选项 | 说明 |
|------|------|
| `--help` | 显示帮助信息 |
| `--version` | 显示版本号 |

---

## 命令：`run`

启动五 Agent 流水线。

### 用法

```bash
agent-pipeline run [OPTIONS] REQUIREMENT
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `REQUIREMENT` | 字符串 | 是 | 产品需求或问题描述 |

### 选项

| 选项 | 类型 | 说明 |
|------|------|------|
| `--resume` | flag | 从最近未完成的流水线恢复执行 |

### 示例

```bash
# 标准用法
agent-pipeline run "设计一个 CLI TODO 应用"

# 调研类需求
agent-pipeline run "调研 AI 编码助手市场"

# 恢复未完成的流水线
agent-pipeline run --resume
```

### 典型输出

```
🚀 五 Agent 流水线已启动 (ID: pl_20260610_143022_abc123)
📋 需求: 设计一个 CLI TODO 应用
📁 项目: 设计一个-cli-todo-应用

📊 Agent 流水线:
  🔍 Scout — 市场调研  ⏳
  🎨 Designer — 产品设计  ⏳
  ⚙️ Builder — 编码实现  ⏳
  🧪 Tester — 质量验证  ⏳
  📦 Seller — 发布准备  ⏳

✅ 五 Agent 流水线完成 (总耗时: 123.4s)

📄 产出物:
  - output/设计一个-cli-todo-应用/scout→designer--调研报告.md (12.3 KB)
  - output/设计一个-cli-todo-应用/designer→builder--需求分析.md (5.1 KB)
  - output/设计一个-cli-todo-应用/designer→builder--架构设计.md (6.2 KB)
  - output/设计一个-cli-todo-应用/builder→tester--src/ (目录)
  - output/设计一个-cli-todo-应用/tester→seller--测试报告.md (3.4 KB)
  - output/设计一个-cli-todo-应用/seller→user--README.md (8.7 KB)
```

### 异常输出

```bash
# 空需求
❌ 错误: 需求不能为空。请提供有效的需求描述。

# 无 API Key
❌ 错误: 未设置 DEEPSEEK_API_KEY 环境变量。
请设置后再运行:
  export DEEPSEEK_API_KEY=sk-xxx

# API Key 无效
❌ 流水线异常: API Key 认证失败
```

---

## 命令：`status`

查看流水线运行状态（五 Agent 执行情况）。

### 用法

```bash
agent-pipeline status [PIPELINE_ID]
```

### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `PIPELINE_ID` | 字符串 | 否 | 流水线 ID（不指定则显示最新） |

### 示例

```bash
# 查看最新流水线状态
agent-pipeline status

# 指定流水线
agent-pipeline status pl_20260610_143022_abc123
```

### 典型输出

```
流水线状态 (pl_20260610_143022_abc123)
  状态: ✅ completed
  需求: 设计一个 CLI TODO 应用
  项目: 设计一个-cli-todo-应用
  Agent 执行情况:
    🔍 Scout: completed · 调研报告已生成
    🎨 Designer: completed · 需求分析与架构设计已生成
    ⚙️ Builder: completed · 代码已生成（迭代 0/3）
    🧪 Tester: completed · 测试报告已生成
    📦 Seller: completed · README 已生成
```

---

## 命令：`list`

列出历史流水线记录。

### 用法

```bash
agent-pipeline list [OPTIONS]
```

### 选项

| 选项 | 类型 | 默认 | 说明 |
|------|------|:----:|------|
| `--limit` | 整数 | 20 | 显示最近 N 条记录 |

### 示例

```bash
# 查看最近 10 条记录
agent-pipeline list --limit 10

# 默认查看最近 20 条
agent-pipeline list
```

### 典型输出

```
最近 2 条流水线记录

ID                        状态          项目                       时间
----------------------------------------------------------------------------------
pl_20260610_143022_abc123 ✅ completed  设计一个-cli-todo-应用     2026-06-10T14:30:22
pl_20260610_141500_def456 ❌ failed     调研-ai-编码助手市场       2026-06-10T14:15:00
```

---

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `DEEPSEEK_API_KEY` | 是 | — | DeepSeek API Key（所有 5 Agent 共用） |
| `AGENT_PIPELINE_WIKI_PATH` | 否 | `../../wiki/` | Wiki 根目录路径 |
| `AGENT_PIPELINE_DEBUG` | 否 | — | 设置后显示完整异常栈 |

---

## 快速安装

```bash
cd projects/agent-pipeline
pip install -e .
export DEEPSEEK_API_KEY=sk-xxx
agent-pipeline run "设计一个 TODO 应用"
```

---

## Agent 参考

| Agent | 工具 | 产出文件 |
|-------|------|---------|
| 🔍 Scout | search_web, read_url, write_report, query_knowledge | `scout→designer--调研报告.md` |
| 🎨 Designer | read_file, write_report, query_knowledge | `designer→builder--需求分析.md`, `designer→builder--架构设计.md` |
| ⚙️ Builder | read_file, write_code, run_command, query_knowledge | `builder→tester--src/` (代码目录) |
| 🧪 Tester | read_file, run_command, write_report | `tester→seller--测试报告.md`, 失败时产生 `tester→builder--修复指令.md` |
| 📦 Seller | read_file, write_report, query_knowledge | `seller→user--README.md` |
