const attachmentIds = [];

const statusLabels = {
  draft: "草稿",
  queued: "排队中",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  interrupted: "已中断",
};

const stageLabels = {
  independent: "独立分析",
  blue_team: "蓝军质询",
  summary: "共识汇总",
  report: "报告生成",
};

const attachmentModeLabels = {
  embedded: "已注入上下文",
  listed_only: "仅列表展示",
};

const extractionLabels = {
  ready: "已提取",
  pending: "待处理",
  failed: "提取失败",
  skipped: "未注入",
};

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "请求失败");
  }
  return data;
}

function bindSettingsPage() {
  document.querySelectorAll(".provider-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const provider = form.dataset.provider;
      const apiKey = form.querySelector("input[name='api_key']").value;
      await postJson("/api/settings/secrets", { provider, api_key: apiKey });
      window.location.reload();
    });
  });

  const modelsForm = document.getElementById("models-form");
  if (!modelsForm) return;
  modelsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const enabledModels = {};
    modelsForm.querySelectorAll("input[type='checkbox']").forEach((input) => {
      enabledModels[input.name] = input.checked;
    });
    await postJson("/api/settings/models", { enabled_models: enabledModels });
    window.location.reload();
  });
}

function bindSessionComposer() {
  const uploadButton = document.getElementById("upload-button");
  const attachmentInput = document.getElementById("attachment-input");
  const attachmentList = document.getElementById("attachment-list");
  const sessionForm = document.getElementById("session-form");

  if (uploadButton && attachmentInput && attachmentList) {
    uploadButton.addEventListener("click", async () => {
      if (!attachmentInput.files.length) return;
      const file = attachmentInput.files[0];
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/api/attachments", { method: "POST", body: formData });
      const data = await response.json();
      if (!response.ok) {
        window.alert(data.detail || data.error || "附件上传失败");
        return;
      }
      attachmentIds.push(data.attachment_id);
      const item = document.createElement("li");
      item.textContent = `${data.filename} · ${attachmentModeLabels[data.injection_mode] || data.injection_mode} · ${extractionLabels[data.extraction_status] || data.extraction_status}`;
      attachmentList.appendChild(item);
      attachmentInput.value = "";
    });
  }

  if (!sessionForm) return;
  sessionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const roles = Array.from(document.querySelectorAll(".role-card")).map((card) => ({
      role_id: card.dataset.roleId,
      enabled: card.querySelector(".role-enabled").checked,
      display_name: card.querySelector(".role-display-name").value,
      responsibility: card.querySelector(".role-responsibility").value,
      instruction: card.querySelector(".role-instruction").value,
      model: card.querySelector(".role-model").value,
    }));

    const payload = {
      title: sessionForm.querySelector("input[name='title']").value,
      project_name: sessionForm.querySelector("input[name='project_name']").value,
      task_description: sessionForm.querySelector("textarea[name='task_description']").value,
      roles,
      attachment_ids: attachmentIds,
    };
    const draft = await postJson("/api/sessions", payload);
    await postJson(`/api/sessions/${draft.session_id}/start`, {});
    window.location.href = `/sessions/${draft.session_id}`;
  });
}

function bindSessionDetail() {
  const detailGrid = document.querySelector(".detail-grid");
  const pollButton = document.getElementById("poll-status-button");
  const statusBlock = document.getElementById("session-status");
  if (!detailGrid || !pollButton || !statusBlock) return;

  const sessionId = detailGrid.dataset.sessionId;
  const refresh = async () => {
    const response = await fetch(`/api/sessions/${sessionId}`);
    const data = await response.json();
    statusBlock.innerHTML = `
      <strong>${statusLabels[data.status.status] || data.status.status}</strong>
      <p>当前阶段：${data.status.current_stage ? (stageLabels[data.status.current_stage] || data.status.current_stage) : "尚未开始"}</p>
      <p>下一步动作：${data.status.next_action || "无"}</p>
      ${data.status.error_summary ? `<p class="error-copy">错误：${data.status.error_summary}</p>` : ""}
    `;
  };

  pollButton.addEventListener("click", refresh);
}

document.addEventListener("DOMContentLoaded", () => {
  bindSettingsPage();
  bindSessionComposer();
  bindSessionDetail();
});
