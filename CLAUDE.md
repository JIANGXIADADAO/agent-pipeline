# CLAUDE.md — {{PROJECT_NAME}}

> 项目级指令。Cub 和所有 Worker 启动后先读此文件定位全局上下文。

## 产品信息

- **产品名**：Agent Pipeline — 多 Agent 开发流水线
- **一句话**：用户输入需求 → 五 Agent 自动协作 → 输出代码 + 测试 + README
- **目标用户**：AI Agent 岗位招聘方（面试官）+ 开源社区开发者
- **定价锚点**：开源免费（MIT），展示项目不售卖

## 产品周期阶段

```
Scout  →  Designer  →  Builder  →  Tester  →  Seller  →  Cub 用户模拟  →  发布
```

| 阶段 | Worker | 状态 | 产出 |
|------|--------|------|------|
| 找方向+验证 | Scout | ✅ 已完成 | `briefs/scout→designer.md` + 市场调研报告 |
| 设计 | Designer | ✅ 已完成 | `briefs/designer→builder.md` + 需求分析 + 架构设计 |
| 开发 | Builder | ✅ 已完成 | `src/agent_pipeline/`（LangGraph StateGraph + 五 Agent） |
| 测试 | Tester | ✅ 已完成 | 48 passed / 0 failed |
| 封版+文档 | Seller | ⏳ 待激活 | README（中英、保姆级、场景路径）|
| 用户模拟 | Cub | ✅ 已完成 | 模拟测试报告（全流程通过，Builder 路径 bug 已修） |
| 分发运营 | Seller | ⏳ 待激活 | ProductHunt / Reddit / HN / 知乎 / 掘金 / V2EX |

### Cub 用户模拟测试

**时机**：Seller 完成 README 后、正式分发前。

**Cub 做什么**：
1. 假装自己是第一次用的新用户。删掉所有配置、token、缓存
2. 打开 README，从 Quick Start 第一步开始逐条执行
3. 每条路径都走：零配置路径 → 有 API key 路径 → 有 GitHub PR 路径 → 发布路径
4. 需要 token 时找用户要（不自己造）
5. 每一步记录：命令是否成功、输出是否符合预期、有没有困惑

**判定标准**：
- 每条 README 中的命令都能成功执行
- 每个"你会看到"的输出和实际一致（格式、关键字段）
- 任何降级/跳过/失败都有明确提示告诉用户发生了什么
- 新手按 README 操作无需任何额外知识

**发现问题 →** 回传对应 Worker 修复，修完 Cub 再测。全部通过 → 绿灯发布。

## 目录结构

```
projects/{{project-slug}}/
├── CLAUDE.md                     ← 本文件
├── .gitignore                    ← Worker 目录 + 临时文件忽略
├── .claude/
│   └── settings.json             ← PostToolUse auto-commit hook
├── briefs/
│   ├── scout→designer.md         ← Scout 写 → Designer/Seller 读
│   ├── designer→builder.md       ← Designer 写 → Builder/Tester 读
│   └── builder→tester.md         ← Builder 写 → Tester 读
├── scout/CLAUDE.md
├── designer/CLAUDE.md
├── builder/CLAUDE.md
├── tester/CLAUDE.md
├── seller/CLAUDE.md
└── src/
    ├── tests/                    ← Tester 唯一可写
    └── ...
```

## 硬约束（所有 Worker 通用）

- `wiki/`：所有 Worker 只读。Cub 是唯一维护者
- `inboxes/`：每个 Worker 只能写自己的文件
- Worker 之间不直接通信——通过 briefs/ 和用户传递信息
- 同项目其他 Worker 的子目录：只读（自己的目录除外）

## 共享记忆

- 导航：`../../wiki/index.md`
- 模板来源：`../../agents/templates/`
- 踩坑上报：`../../inboxes/<role>.md`

## 断点规则

- 存档：每个 Worker 在自己 CLAUDE.md 末尾写入 `<!-- ROLE:RESUME -->` 标记块
- 恢复：下次启动时检测标记块 → 读出 → 删除 → 继续
- 关键：读后即删，避免过期断点残留

## Git 与操作日志

本项目使用 Git 作为操作日志引擎。每步重要产出自动或手动 commit：

- **自动**：`.claude/settings.json` 的 PostToolUse hook，每次 Write/Edit 自动 `[auto]` commit
- **语义**：Worker 完成交付时手动 `git commit -m "[scout] 竞品深挖完成"` ——用于 Dashboard 操作日志面板展示

### Commit 标签约定

| 标签 | 使用角色 |
|------|---------|
| `[scout]` | Scout 交付 |
| `[designer]` | Designer 交付 |
| `[builder]` | Builder 功能完成 |
| `[tester]` | Tester 测试完成 |
| `[seller]` | Seller 发布完成 |

### 新项目初始化

```bash
mkdir -p projects/新项目/src
cp agents/templates/project.template.md projects/新项目/CLAUDE.md
cp agents/templates/.gitignore projects/新项目/.gitignore
mkdir -p projects/新项目/.claude
cp agents/templates/settings.json projects/新项目/.claude/settings.json
cd projects/新项目
git init                                    ← 项目级 Git，Dashboard 依赖
git add -A && git commit -m "[init] 项目创建"
# 编辑 CLAUDE.md，填入项目信息
```

> **项目级 Git**：每个项目独立的 `.git/`，不会和公司根仓库冲突。git 在工作目录内自动使用最近的 `.git/`。Dashboard 只读项目级 git log。