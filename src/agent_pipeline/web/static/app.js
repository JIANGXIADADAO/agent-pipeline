/* ============================================================
   Agent Pipeline — Web UI 前端逻辑
   SSE 消费者 + Agent 卡片更新 + 实时日志 + Eclipse 熄灯
   ============================================================ */

(function () {
  "use strict";

  // ---- DOM 引用 ----
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  const el = {
    input: $("#requirement-input"),
    startBtn: $("#start-btn"),
    exampleBtn: $("#example-btn"),
    eclipseBtn: $("#eclipse-btn"),
    liveDot: $("#live-dot"),
    statusBanner: $("#status-banner"),
    logContainer: $("#log-container"),
    logCount: $("#log-count"),
    progressFill: $("#progress-fill"),
    progressText: $("#progress-text"),
    artifactsSection: $("#artifacts-section"),
    artifactsList: $("#artifacts-list"),
    eclipseOverlay: $("#eclipse-overlay"),
    helpToggle: $("#help-toggle"),
    helpContent: $("#help-content"),
  };

  const agentCards = {
    scout: { el: $("#agent-scout"), statusEl: null, durationEl: null },
    designer: { el: $("#agent-designer"), statusEl: null, durationEl: null },
    builder: { el: $("#agent-builder"), statusEl: null, durationEl: null },
    tester: { el: $("#agent-tester"), statusEl: null, durationEl: null },
    seller: { el: $("#agent-seller"), statusEl: null, durationEl: null },
  };

  // 初始化卡片子元素引用
  for (const [name, card] of Object.entries(agentCards)) {
    if (card.el) {
      card.statusEl = card.el.querySelector(".agent-status");
      card.durationEl = card.el.querySelector(".agent-duration");
    }
  }

  const AGENT_ORDER = ["scout", "designer", "builder", "tester", "seller"];
  const AGENT_LABELS = {
    scout: { icon: "🔍", label: "Scout", role: "市场调研" },
    designer: { icon: "🎨", label: "Designer", role: "产品设计" },
    builder: { icon: "⚙️", label: "Builder", role: "编码实现" },
    tester: { icon: "🧪", label: "Tester", role: "质量验证" },
    seller: { icon: "📦", label: "Seller", role: "发布准备" },
  };

  // ---- 状态 ----
  let currentPipelineId = null;
  let eventSource = null;
  let logCount = 0;
  let agentStatus = {}; // agent_name -> "pending"|"running"|"completed"|"failed"
  let completedCount = 0;
  let lastElapsed = 0;

  // ---- Agent 状态管理 ----
  function resetAgentStatus() {
    agentStatus = {};
    completedCount = 0;
    for (const name of AGENT_ORDER) {
      agentStatus[name] = "pending";
    }
    updateAllCards();
  }

  function setAgentStatus(agent, status) {
    agentStatus[agent] = status;
    updateCard(agent);
    updateProgress();
  }

  function updateCard(agent) {
    const card = agentCards[agent];
    if (!card || !card.el) return;

    const status = agentStatus[agent] || "pending";
    const info = AGENT_LABELS[agent] || {};

    // Remove all state classes
    card.el.classList.remove("pending", "running", "completed", "failed");
    card.el.classList.add(status);

    if (card.statusEl) {
      const statusTexts = {
        pending: "⏳ 等待中",
        running: "🔄 运行中",
        completed: "✅ 已完成",
        failed: "❌ 失败",
      };
      card.statusEl.textContent = statusTexts[status] || status;
    }
  }

  function updateAllCards() {
    for (const name of AGENT_ORDER) {
      updateCard(name);
    }
  }

  function updateProgress() {
    let running = false;
    let done = 0;
    for (const name of AGENT_ORDER) {
      const s = agentStatus[name] || "pending";
      if (s === "completed" || s === "failed") done++;
      if (s === "running") running = true;
    }

    const total = AGENT_ORDER.length;
    const pct = Math.round((done / total) * 100);
    el.progressFill.style.width = pct + "%";
    el.progressText.textContent = `${done}/${total} Agent`;
  }

  function setAllCardsDone() {
    for (const name of AGENT_ORDER) {
      if (agentStatus[name] === "pending" || agentStatus[name] === "running") {
        agentStatus[name] = "completed";
      }
    }
    updateAllCards();
    updateProgress();
  }

  // ---- 日志 ----
  function addLogLine(time, agent, eventType, detail) {
    const line = document.createElement("div");
    line.className = "log-line";

    // Determine CSS class based on event type
    let eventClass = "";
    if (eventType === "agent_start") eventClass = "log-agent-start";
    else if (eventType === "agent_end") eventClass = "log-agent-end";
    else if (eventType === "tool_start") eventClass = "log-tool-start";
    else if (eventType === "tool_end") eventClass = "log-tool-end";
    else if (eventType === "pipeline_end") eventClass = "log-pipeline-end";
    else if (eventType === "error") eventClass = "log-error";
    else if (eventType === "llm_start" || eventType === "llm_end") eventClass = "log-llm-end";
    if (eventClass) line.classList.add(eventClass);

    const agentDisplay = agent ? agent.toUpperCase() : "SYS";
    const eventDisplay = formatEvent(eventType, detail);

    line.innerHTML = `
      <span class="log-time">${time || "--:--:--"}</span>
      <span class="log-agent">${agentDisplay}</span>
      <span class="log-event">${escapeHtml(eventDisplay)}</span>
    `;

    el.logContainer.appendChild(line);
    el.logContainer.scrollTop = el.logContainer.scrollHeight;

    logCount++;
    el.logCount.textContent = `${logCount} 条`;
  }

  function formatEvent(eventType, detail) {
    switch (eventType) {
      case "agent_start":
        return "▶ 开始工作";
      case "agent_end":
        return detail
          ? `✓ 完成 (${detail.duration_s || "?"}s)`
          : "✓ 完成";
      case "tool_start":
        return `→ ${escapeHtml(detail.tool || "unknown")} ("${escapeHtml((detail.input || "").slice(0, 60))}")`;
      case "tool_end":
        return `← ${escapeHtml(detail.tool || "unknown")} 返回`;
      case "llm_start":
        return "🤖 LLM 调用";
      case "llm_end":
        return "🤖 LLM 返回";
      case "pipeline_end":
        return detail
          ? `🏁 流水线结束 (${detail.status || "completed"})`
          : "🏁 流水线结束";
      default:
        return eventType;
    }
  }

  function clearLog() {
    el.logContainer.innerHTML = "";
    logCount = 0;
    el.logCount.textContent = "0 条";
  }

  // ---- Artifacts ----
  function showArtifacts(artifacts) {
    if (!artifacts || artifacts.length === 0) {
      el.artifactsSection.classList.remove("visible");
      return;
    }
    el.artifactsList.innerHTML = "";
    for (const art of artifacts) {
      const item = document.createElement("div");
      item.className = "artifact-item";
      item.innerHTML = `
        <span class="artifact-icon">📄</span>
        <span class="artifact-path">${escapeHtml(art)}</span>
      `;
      el.artifactsList.appendChild(item);
    }
    el.artifactsSection.classList.add("visible");
  }

  // ---- Status Banner ----
  function showBanner(message, type) {
    el.statusBanner.className = "status-banner visible " + (type || "info");
    el.statusBanner.textContent = message;
  }

  function hideBanner() {
    el.statusBanner.className = "status-banner";
  }

  // ---- SSE Connection ----
  function connectSSE(pipelineId) {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }

    currentPipelineId = pipelineId;
    const url = `/stream/${pipelineId}`;
    eventSource = new EventSource(url);

    eventSource.onmessage = function (e) {
      try {
        const event = JSON.parse(e.data);
        handleEvent(event);
      } catch (err) {
        console.warn("SSE parse error:", err);
      }
    };

    eventSource.onerror = function () {
      // EventSource auto-reconnects, but we close on pipeline end
      console.warn("SSE connection error");
    };

    eventSource.onopen = function () {
      console.log("SSE connected:", url);
    };
  }

  function disconnectSSE() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  // ---- Event Handler ----
  function handleEvent(event) {
    const { time, agent, event: eventType, ...detail } = event;

    // Add log line
    addLogLine(time, agent || "system", eventType, detail);

    if (eventType === "agent_start" && agent) {
      setAgentStatus(agent, "running");
      showBanner(`${AGENT_LABELS[agent]?.icon || ""} ${(AGENT_LABELS[agent]?.label || agent)} 开始工作`, "info");
    } else if (eventType === "agent_end" && agent) {
      const status = detail.status || "completed";
      if (status === "failed") {
        setAgentStatus(agent, "failed");
      } else {
        setAgentStatus(agent, "completed");
      }
      // Set duration on card
      const card = agentCards[agent];
      if (card && card.durationEl && detail.duration_s) {
        card.durationEl.textContent = `${detail.duration_s}s`;
      }
    } else if (eventType === "pipeline_end") {
      const status = detail.status || "completed";
      if (status === "cancelled") {
        // Eclipse was triggered
        showEclipseOverlay();
      } else {
        setAllCardsDone();
        if (status === "failed") {
          showBanner("❌ 流水线执行失败", "error");
        } else {
          showBanner("✅ 流水线执行完成", "success");
        }
        // Disconnect SSE after a brief delay
        setTimeout(() => disconnectSSE(), 1000);
      }
      el.liveDot.classList.add("off");
    }
  }

  // ---- Eclipse ----
  function showEclipseOverlay() {
    el.eclipseOverlay.classList.add("visible");
  }

  async function triggerEclipse() {
    try {
      const resp = await fetch("/shutdown", { method: "POST" });
      const data = await resp.json();
      console.log("Eclipse response:", data);
    } catch (err) {
      // Server is shutting down, connection will drop
      console.log("Eclipse triggered, server shutting down");
    }
    showEclipseOverlay();
  }

  // ---- Start Pipeline ----
  async function startPipeline() {
    const requirement = el.input.value.trim();
    if (!requirement) {
      showBanner("请输入需求描述", "error");
      el.input.focus();
      return;
    }

    // Reset UI
    hideBanner();
    clearLog();
    resetAgentStatus();
    el.artifactsSection.classList.remove("visible");
    el.liveDot.classList.remove("off");
    el.startBtn.disabled = true;
    el.eclipseBtn.disabled = false;
    el.progressFill.style.width = "0%";
    el.progressText.textContent = "0/5 Agent";

    showBanner("🚀 正在启动流水线...", "info");

    try {
      const resp = await fetch("/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirement }),
      });

      const data = await resp.json();

      if (resp.status !== 200) {
        showBanner("❌ " + (data.error || "启动失败"), "error");
        el.startBtn.disabled = false;
        return;
      }

      showBanner("🔗 已连接到流水线，等待 Agent 执行...", "info");
      connectSSE(data.pipeline_id);
    } catch (err) {
      showBanner("❌ 网络错误: " + err.message, "error");
      el.startBtn.disabled = false;
    }
  }

  // ---- Example Prompts ----
  const EXAMPLES = [
    "设计一个 CLI TODO 应用，支持添加、完成、删除任务，数据持久化到 JSON 文件",
    "开发一个 Markdown 转 HTML 的命令行工具",
    "做一个天气查询 CLI 工具，调用免费天气 API",
  ];

  let exampleIndex = 0;

  function fillExample() {
    el.input.value = EXAMPLES[exampleIndex % EXAMPLES.length];
    exampleIndex++;
    el.input.focus();
  }

  // ---- Help Toggle ----
  function toggleHelp() {
    const isHidden = el.helpContent.classList.contains("hidden");
    el.helpContent.classList.toggle("hidden");
    el.helpToggle.textContent = isHidden ? "▲ 收起" : "▼ 展开";
  }

  // ---- Utility ----
  function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ---- Event Bindings ----
  function init() {
    el.startBtn.addEventListener("click", startPipeline);
    el.exampleBtn.addEventListener("click", fillExample);
    el.eclipseBtn.addEventListener("click", triggerEclipse);

    if (el.helpToggle && el.helpContent) {
      el.helpToggle.addEventListener("click", toggleHelp);
    }

    // Enter key to start (Shift+Enter for newline)
    el.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        startPipeline();
      }
    });

    // Initial state
    resetAgentStatus();
    updateProgress();
  }

  // ---- Boot ----
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
