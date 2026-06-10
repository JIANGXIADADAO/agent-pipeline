# Agent Pipeline — 多 Agent 开发流水线

> [English](README.md) · **中文**

**输入产品需求，五个 AI Agent 自动协作，输出代码 + 测试 + README。**

[![版本](https://img.shields.io/badge/version-0.2.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-green)]()
[![测试](https://img.shields.io/badge/tests-48%20passed-success)]()

---

## 这是什么？

Agent Pipeline 是一个**开源的多 Agent 开发流水线**。你只需要描述一个产品需求，五个 AI Agent 就会依次执行——从调研、设计、编码、测试到文档——端到端自动完成。

| 序号 | Agent | 角色 | 产出文件 |
|:----:|-------|------|----------|
| 1 | **Scout** (侦察兵) | 市场调研 | `scout→designer--调研报告.md` |
| 2 | **Designer** (设计师) | 产品设计 | `designer→builder--需求分析.md` + `架构设计.md` |
| 3 | **Builder** (构建者) | 编码实现 | `builder→tester--src/` (代码目录) |
| 4 | **Tester** (测试员) | 质量验证 | `tester→seller--测试报告.md` |
| 5 | **Seller** (发布经理) | 发布准备 | `seller→user--README.md` |

**核心亮点：**

- **五 Agent 全自动协作** — 一个需求触发全链条
- **Tester→Builder 回退循环** — 发现 bug 自动回修，最多 3 次
- **Web UI + SSE 实时看板** — 浏览器中观看五个 Agent 依次工作
- **Eclipse 一键熄灯** — 优雅关闭服务器，释放端口
- **文件命名即流水线文档** — `生产者→消费者--内容.md`，一眼看出文件由谁产出、给谁看
- **预索引门控 RAG** — 知识库命中时直接加载 wiki 页面，无需向量检索

---

## 快速开始

### 路径 1：零配置体验（无需 API Key）

先看看流水线长什么样：

```bash
# 1. 安装
pip install -e .

# 2. 查看命令列表
agent-pipeline --help
```

**你会看到：**

```
Usage: agent-pipeline [OPTIONS] COMMAND [ARGS]...

  Agent Pipeline — 五 Agent 开发流水线。

  用户输入产品需求 → 五个 Agent 依次执行：
  Scout(市场调研) → Designer(产品设计) → Builder(编码实现) → Tester(质量验证) → Seller(发布准备)

Options:
  --version  显示版本号并退出
  --help     显示帮助信息并退出

Commands:
  run     启动五 Agent 流水线
  status  查看流水线状态
  list    列出历史流水线记录
  serve   启动 Web 服务
```

不需要 API Key 就能看帮助。你也可以启动 Web UI（见路径 3）查看界面。

---

### 路径 2：有 Key 完整运行（CLI 模式）

你需要一个 **DeepSeek API Key**。在 [platform.deepseek.com](https://platform.deepseek.com) 免费注册获取。

```bash
# 1. 安装
pip install -e .

# 2. 设置 API Key
# Windows (cmd):
set DEEPSEEK_API_KEY=sk-你的-key

# Windows (PowerShell):
$env:DEEPSEEK_API_KEY="sk-你的-key"

# macOS / Linux:
export DEEPSEEK_API_KEY=sk-你的-key

# 3. 启动流水线
agent-pipeline run "设计一个 CLI TODO 应用"
```

**你会看到：**

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

> **注意：** 首次运行可能需要几分钟（Scout 搜索网络、Designer 写规格、Builder 生成代码、Tester 审查、Seller 写 README）。每个 Agent 有 5 分钟超时。

---

### 路径 3：Web UI 模式（有 API Key）

喜欢图形界面？启动 Web 看板：

```bash
# 1. 设置 API Key
export DEEPSEEK_API_KEY=sk-你的-key

# 2. 启动服务
agent-pipeline serve
```

**你会看到：**

```
🌐 Agent Pipeline Web 服务已启动 (http://localhost:3456)
按 Ctrl+C 停止服务
```

打开浏览器访问 **http://localhost:3456**，你会看到：

1. **输入框** — 输入你的需求（如"设计一个 CLI TODO 应用"）
2. 点击 **▶ 启动** — 五个 Agent 卡片依次亮起
3. **实时日志** — 每个 Agent 的工具调用（搜索、读取、写入）实时显示
4. **进度条** — 一目了然看到整体完成度
5. **产出物** — 点击即可下载每个输出文件
6. **◉ Eclipse 按钮** — 一键优雅关闭服务器

---

## 命令参考

### `agent-pipeline run`

启动五 Agent 流水线。

```bash
agent-pipeline run [选项] 需求
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `需求` | 字符串 | 是 | 产品需求或问题描述 |

| 选项 | 说明 |
|------|------|
| `--resume` | 从最近未完成的流水线恢复执行 |

**示例：**

```bash
agent-pipeline run "调研 AI 编码助手市场"
agent-pipeline run --resume
```

### `agent-pipeline status`

查看流水线运行状态。

```bash
agent-pipeline status [流水线ID]
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `流水线ID` | 字符串 | 否 | 流水线 ID（不指定则显示最新） |

**示例输出：**

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

### `agent-pipeline list`

列出历史流水线记录。

```bash
agent-pipeline list [--limit N]
```

| 选项 | 默认 | 说明 |
|------|:----:|------|
| `--limit` | 20 | 显示最近 N 条记录 |

### `agent-pipeline serve`

启动 Web 服务。

```bash
agent-pipeline serve [--port 端口] [--no-open]
```

| 选项 | 默认 | 说明 |
|------|:----:|------|
| `--port` | 3456 | Web 服务端口 |
| `--no-open` | — | 不自动打开浏览器 |

---

## 架构概览

```
用户输入需求
    │
    ▼
┌──────────────────────────────────────────────┐
│  LangGraph StateGraph (编排器)                 │
│                                               │
│  START → 解析 → 调研 → 设计 → 编码            │
│                                    │          │
│                                    │          │
│  测试 ←────────────────────────────┘          │
│    │                                          │
│    ├── (发现问题, < 3 次) → 编码              │
│    └── (全部通过或 ≥ 3 次) → 发布             │
│                                              │
│  发布 → 收尾 → END                           │
└──────────────────────────────────────────────┘
    │
    ▼
 代码 + 测试 + README
```

### Tester→Builder 回退循环如何工作

1. **Tester** 审查 Builder 的代码是否满足 Designer 的设计规格
2. 发现问题 → 写入 `tester→builder--修复指令.md`
3. **条件路由** 自动回到 Builder（最多 3 次）
4. 3 次后仍不合格 → 前进到 Seller（并记录警告）
5. 全部通过 → 直接前进到 Seller

### 预索引门控 RAG

在调用 Agent 之前，编排器会：
1. 读取 `wiki/index.md` 寻找相关知识
2. **命中** — 直接加载对应的 wiki 页面作为上下文（无需向量检索）
3. **未命中** — 走外部搜索

这是一个设计差异化——"什么时候不该用 RAG"。

---

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:----:|--------|------|
| `DEEPSEEK_API_KEY` | 是 | — | DeepSeek API Key（所有 5 个 Agent 共用） |
| `AGENT_PIPELINE_WIKI_PATH` | 否 | `../../wiki/` | Wiki 根目录路径 |
| `AGENT_PIPELINE_DEBUG` | 否 | — | 设置后显示完整异常栈（调试用） |

---

## 产出物说明

文件名遵循 `{生产者}→{消费者}--{内容}.md` 的约定——一眼看出谁产出、给谁看。

| 文件 | 生产者 | 消费者 | 说明 |
|------|:------:|:------:|------|
| `scout→designer--调研报告.md` | Scout | Designer | 市场调研报告 |
| `designer→builder--需求分析.md` | Designer | Builder | JTBD + RICE + MVP 需求分析 |
| `designer→builder--架构设计.md` | Designer | Builder | 技术架构与选型 |
| `builder→tester--src/` | Builder | Tester | 生成的代码目录 |
| `tester→seller--测试报告.md` | Tester | Seller | 测试结果汇总 |
| `tester→builder--修复指令.md` | Tester | Builder | 修复说明（仅在发现问题时生成） |
| `seller→user--README.md` | Seller | 用户 | 生成的 README 文档 |

---

## 常见问题 (FAQ)

**不配 API Key 能用吗？**
可以执行 `--help` 和 `serve`（看界面），但运行流水线需要有效的 `DEEPSEEK_API_KEY`。

**怎么申请 DeepSeek API Key？**
在 [platform.deepseek.com](https://platform.deepseek.com) 注册即可，免费获取。

**支持什么操作系统？**
Windows、macOS、Linux 都支持。Windows 用户使用 Web UI 时推荐 WSL，但 CLI 模式原生可用。

**流水线跑一半断了怎么办？**
使用 `agent-pipeline run --resume` 从最近保存的断点恢复。每个 Agent 完成后会自动保存 `state.json`。

**Web UI 端口被占用了？**
换个端口：`agent-pipeline serve --port 8888`

**怎么停止 Web 服务器？**
点击右上角的 **◉ Eclipse** 按钮，或者在终端按 `Ctrl+C`。

**Builder 会生成什么语言的代码？**
默认生成 Python 代码（匹配项目的技术栈）。但实际上 LLM 支持任何语言，你可以通过修改 System Prompt 来指定。

**我能自定义 Agent 吗？**
Phase 4 计划中。目前你可以修改 `src/agent_pipeline/agents/` 下的 System Prompt。

**为什么需要 DeepSeek？可以用其他模型吗？**
当前版本内置 DeepSeek API 支持。如果要用其他模型（如 Claude、GPT），需要修改 `src/agent_pipeline/agents/` 下的 LLM 初始化代码。

---

## 开发指南

```bash
# 克隆并安装
git clone <仓库地址>
cd agent-pipeline
pip install -e .

# 运行测试
cd src
python -m pytest tests/test_cli.py -v

# 预期结果：48 passed，0 failed
```

---

## 许可证

MIT
