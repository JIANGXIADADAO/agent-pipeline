---
title: "Agent Pipeline — 交互设计"
type: overview
tags: [agent-pipeline, interaction, ui, web, visualization]
created: 2026-06-10
updated: 2026-06-10
---

# Agent Pipeline — 交互设计

> Web UI 基于 agent-team-dashboard 的 SSE + Pipeline 组件复用。
> 覆盖用户操作流、Agent 流水线可视化、边界/异常状态。

---

## 一、UI 整体布局

```
┌─────────────────────────────────────────────────────────────────┐
│  Agent Pipeline                                      [Settings] │
│  多 Agent 开发流水线                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  💬 输入需求区域                                           │   │
│  │  ┌────────────────────────────────────────────────────┐   │   │
│  │  │ 描述你的产品需求...                                    │   │   │
│  │  │                                                      │   │   │
│  │  │ 例如："做一个 CLI 工具，自动生成项目的 CHANGELOG"       │   │   │
│  │  └────────────────────────────────────────────────────┘   │   │
│  │  [▶ 启动流水线]    [📋 示例需求]                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────┬────────────────┐   │
│  │  流水线可视化看板                            │  详情面板      │   │
│  │                                          │               │   │
│  │  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐ │  Agent 名称    │   │
│  │  │Scout │→ │Desgnr│→ │Builr │→ │Tester│→│  状态: running │   │
│  │  │ ✅   │  │ ▶    │  │ ⏳   │  │ ⏳   │ │  耗时: 45s     │   │
│  │  └──────┘  └──────┘  └──────┘  └──────┘ │  输出: —       │   │
│  │                    ┌──────┐              │               │   │
│  │                    │Sller │              │  工具调用历史:  │   │
│  │                    │ ⏳   │              │  search_web    │   │
│  │                    └──────┘              │  read_url...   │   │
│  │                                          │               │   │
│  │  总进度: ███████░░░░░ 60%                │  [查看详细]    │   │
│  │                                          │               │   │
│  └──────────────────────────────────────────┴────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  输出区                                                   │   │
│  │  📁 scout/report.md      ✅ 已生成 · 12KB                │   │
│  │  📁 designer/            ⏳ 进行中                        │   │
│  │  ...                                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、用户操作流程

### 2.1 第一次使用（无配置）

```
用户打开页面
    │
    ▼
[首页状态: 未配置]
    ├─ 提示："需要配置 Anthropic API Key 才能使用"
    ├─ 显示 API Key 输入框 + 保存按钮
    └─ 示例：输入 API Key → 保存到 localStorage / .env
    │
    ▼
[配置完成后]
    ├─ 首页变为正常输入状态
    └─ 提示消失
```

### 2.2 启动流水线

```
用户在输入框键入需求
    │
    ├─ 自动保存草稿到 localStorage（防误关丢失）
    ├─ 示例需求下拉菜单（供快速尝试）
    │
    ▼
点击[启动流水线]
    │
    ├─ 输入验证：非空 + >10 字符
    ├─ 空输入 → 按钮 disabled + 提示"需求不能为空"
    ├─ 短输入 → 提示"请提供更详细的需求描述（至少 10 字）"
    │
    ▼
[流水线启动]
    ├─ 创建 PipelineState
    ├─ 发送 SSE 连接到 /api/pipeline/{id}/events
    ├─ 按钮变更为 [🔄 运行中...] (disabled)
    ├─ 流水线看板出现，Scout 卡片高亮
    └─ 输入框变为只读
```

### 2.3 查看流水线进度

```
Scout Agent 正在运行
    │
    ▼
看板上的 Scout 卡片状态: ▶ running
    ├─ 图标旋转动画
    ├─ 实时耗时更新 (0s → 5s → 10s...)
    ├─ 工具调用实时显示:
    │   ├─ search_web("AI coding assistant market 2026")
    │   ├─ read_url("https://...")
    │   └─ write_report("scout/report.md")
    │
    ▼
Scout 完成
    ├─ 卡片状态: ✅ completed
    ├─ 连接线流向 Designer
    ├─ Designer 卡片状态: ⏳ queued → ▶ running
    └─ 输出区出现 scout/report.md 链接
```

### 2.4 查看 Agent 详细输出

```
点击流水线卡片（或 [查看详细] 按钮）
    │
    ▼
[详情面板]
    ├─ Tab 1: Agent 对话记录（完整 ReAct 轨迹）
    │   ├─ 思考过程展开/折叠
    │   └─ 工具调用 → 结果 → 继续思考
    ├─ Tab 2: 产出物列表（文件路径 + 大小 + 预览）
    └─ Tab 3: 耗时分析（各工具调用耗时 + 总耗时）
```

### 2.5 流水线完成

```
全部 Agent 完成
    │
    ▼
[完成状态]
    ├─ 所有卡片显示 ✅ completed
    ├─ 输出区列出所有产出物
    ├─ 按钮: [📥 下载全部产出] [📋 复制结果摘要]
    ├─ 显示总耗时: "5 Agent · 3 分 42 秒"
    └─ 输入框恢复可编辑，可再次提交
```

---

## 三、流水线可视化组件规格

### 3.1 流水线看板（PipelineBoard）

| 属性 | 类型 | 说明 |
|------|------|------|
| `agents` | AgentCard[] | 五个 Agent 卡片 |
| `connections` | Connection[] | Agent 间连接线 |
| `progress` | number | 0-100 总体进度 |
| `status` | "idle" \| "running" \| "completed" \| "failed" | 流水线状态 |

### 3.2 Agent 卡片（AgentCard）

| 状态 | 图标 | 卡片样式 | 说明 |
|------|------|---------|------|
| `idle` | ⏹ | 灰色边框 + 灰图标 | 等待执行 |
| `queued` | ⏳ | 灰色边框 + 加载图标 | 排队中 |
| `running` | ▶ | 蓝色高亮边框 + 旋转动画 | 执行中 |
| `completed` | ✅ | 绿色边框 | 成功完成 |
| `failed` | ❌ | 红色边框 | 失败（可点击查看错误） |
| `skipped` | ⏭ | 灰色虚线边框 | 因上游失败被跳过 |

### 3.3 Agent 间连接线

| 状态 | 样式 | 说明 |
|------|------|------|
| `pending` | 灰色虚线 | 未执行 |
| `active` | 蓝色实线 + 流动动画 | 正在连接前一个到当前 |
| `completed` | 绿色实线 | 已通过 |
| `failed` | 红色实线 | 连接失败 |

### 3.4 输出文件列表（ArtifactList）

| 文件状态 | 图标 | 说明 |
|----------|------|------|
| `pending` | ⏳ | 尚未生成 |
| `generated` | ✅ | 已生成，可预览/下载 |
| `failed` | ❌ | 生成失败 |
| Size | — | 文件大小（KB/MB） |
| Preview | — | 鼠标悬停显示前 200 字预览 |

---

## 四、边界与异常状态

### 4.1 加载状态

| 场景 | 视觉表现 | 用户操作 |
|------|---------|---------|
| 页面首次加载 | Skeleton 骨架屏（卡片占位 + 脉冲动画） | 无 |
| API Key 验证中 | 按钮 disabled + 旋转指示器 | 不能操作 |
| 流水线启动中 | 启动按钮 → 旋转加载 + "正在启动..." | 不能重复点击 |
| SSE 重连中 | 顶部提示条 "连接断开，正在重连..." | 无需操作 |
| 文件预览加载 | 预览区域显示旋转指示器 | 可等待或关闭 |

### 4.2 空状态

| 场景 | 提示语 | 推荐操作 |
|------|--------|---------|
| 首次打开（无流水线历史） | "欢迎使用 Agent Pipeline！输入一个产品需求，5 个 Agent 将自动协作完成。" | [📋 试试示例需求] |
| 无 API Key | "需要配置 Anthropic API Key 才能使用" | [⚙️ 去配置] |
| 流水线无产出 | "流水线尚未运行完成" | — |
| 搜索结果为空 | "未找到相关 Agent 产出" | — |

### 4.3 错误状态

| 场景 | 错误提示 | 恢复操作 |
|------|---------|---------|
| API Key 无效 | "API Key 认证失败，请检查配置" | [⚙️ 更新 API Key] |
| Agent 超时（>5min） | "Scout Agent 执行超时，已自动重试" | 重试 1 次后显示失败原因 |
| Agent 失败 | "Builder Agent 执行失败：{错误详情}" | [🔄 重试此 Agent] [⏭ 跳过继续] |
| SSE 连接断开 | "与服务器的连接已断开，正在自动重连..." | 等待重连（最多 3 次） |
| 多 Agent 全部失败 | "流水线运行失败：5 个 Agent 均未正常完成" | [🔄 从需求重新开始] |
| 网络错误 | "网络请求失败，请检查网络连接" | [🔄 重试] |
| 浏览器版本过低 | "浏览器版本过低，部分功能可能不可用" | 更新浏览器 |

### 4.4 CLI 交互（Phase 1 主要交互）

| 命令 | 说明 | 输出示例 |
|------|------|---------|
| `agent-pipeline init` | 初始化配置（创建 .env 模板） | `✅ Agent Pipeline 已初始化。请设置 ANTHROPIC_API_KEY` |
| `agent-pipeline run "需求"` | 启动流水线 | `🚀 流水线已启动\n  → Scout Agent 正在调研...\n  → 搜索关键词：AI coding assistant\n  → 调研报告已生成：output/scout/report.md\n✅ 流水线完成 (耗时: 2m15s)` |
| `agent-pipeline run --resume` | 从断点恢复 | `🔄 从上次中断处恢复...` |
| `agent-pipeline status` | 查看当前流水线状态 | `📊 流水线状态\n  - 当前阶段: designer\n  - 运行时间: 45s\n  - 已完成: scout ✅` |
| `agent-pipeline list` | 列出历史流水线 | `📋 历史流水线\n  1. 2026-06-10: "调研 AI 编码助手" → 已完成\n  2. 2026-06-09: "CLI 工具" → 失败 (原因: API 超时)` |

### 4.5 CLI 进度输出格式

```
🚀 Agent Pipeline 启动
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 需求: "做一个 AI 编码助手市场调研"
📁 项目: ai-coding-assistant-market-research
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ Phase 1/5: Scout Agent
  ⏳ search_web("AI coding assistant market 2026")...
  ✅ 找到 5 个来源
  ⏳ read_url("https://example.com/report")...
  ✅ 读取成功 (12KB)
  ⏳ write_report("output/scout/report.md")...
  ✅ 调研报告已生成 (8KB)
▶ Scout Agent 完成 (耗时: 1m30s)

⏳ 下一阶段: Designer Agent (准备中...)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 五、响应式布局断点

| 断点 | 宽度 | 布局 |
|------|------|------|
| Desktop | ≥1024px | 三栏：输入区 + Pipeline 看板 + 详情面板 |
| Tablet | 768-1023px | 两栏：输入 + Pipeline 看板（详情面板折叠为 overlay） |
| Mobile | <768px | 单栏堆叠：输入 → Pipeline 看板 → 详情（可切换 Tab） |

---

## 六、动效参数

| 元素 | 动效 | 参数 |
|------|------|------|
| Agent 卡片状态切换 | 渐入 + 颜色过渡 | 300ms ease-in-out |
| 连接线流动 | 虚线路径动画 | 2s 循环 |
| 工具调用实时更新 | 列表项滑入 | 200ms slide-up |
| 产出物出现 | 弹入 + 轻微缩放 | 400ms spring (0.4, 1.2, 0.8, 1) |
| 错误提示 | 红色闪烁 + 抖动 | 500ms shake |
| 加载骨架 | 脉冲发光 | 1.5s ease-in-out 循环 |
| 页面过渡 | 淡入 | 200ms fade-in |

---

## 七、组件树（Phase 2 Web UI）

```
Page
├── Header
│   ├── Logo + 项目名
│   └── SettingsButton (API Key 配置)
├── InputSection
│   ├── RequirementTextarea
│   │   ├─ 占位文本（带示例）
│   │   └─ 字数统计 + 最低字数提示
│   ├── ExampleDropdown
│   │   └─ ExampleOption × 3
│   └── StartButton (disabled 状态)
├── PipelineBoard
│   ├── AgentCard × 5
│   │   ├─ AgentIcon (根据状态变化)
│   │   ├─ AgentName
│   │   ├─ StatusBadge
│   │   ├─ TimerDisplay
│   │   └─ ProgressBar (running 时)
│   ├── ConnectionLine × 4
│   └── OverallProgress
├── DetailPanel (右侧 / 底部)
│   ├── TabBar (对话 / 产出 / 耗时)
│   ├── ConversationView (ReAct 轨迹)
│   │   ├─ ThoughtBlock (可折叠)
│   │   ├─ ToolCallBlock
│   │   └─ ToolResultBlock
│   ├── ArtifactList
│   │   └─ ArtifactItem (状态 + 文件名 + 大小 + 预览)
│   └── TimelineView
├── OutputSection (底部)
│   ├── ArtifactList (同 DetailPanel)
│   └── ActionButtons
│       ├─ DownloadAllButton
│       └─ CopySummaryButton
└── StatusBar
    ├─ ConnectionStatus (SSE)
    └─ PipelineStatus
```

---

## 八、SSE 事件 → UI 状态映射

| SSE 事件 | UI 响应 |
|----------|---------|
| `pipeline.created` | 创建新的流水线看板实例 |
| `agent.started` | 对应 AgentCard → `running` 状态，计时器启动 |
| `agent.tool_call` | DetailPanel 对话 Tab 追加工具调用行 |
| `agent.tool_result` | 工具调用行更新为 ✅，显示结果摘要 |
| `agent.completed` | AgentCard → `completed`，输出区出现文件 |
| `agent.failed` | AgentCard → `failed`，错误详情显示 |
| `agent.retrying` | AgentCard 显示重试次数 "重试 1/2" |
| `pipeline.completed` | 全部卡片完成，按钮恢复，总耗时显示 |
| `pipeline.failed` | 顶部错误 banner，恢复操作按钮 |
| `knowledge.hit` | 知识来源 badge 显示（可选扩展） |
