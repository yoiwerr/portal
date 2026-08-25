const feed = document.querySelector("#entryFeed");
const loadingState = document.querySelector("#loadingState");
const entryCount = document.querySelector("#entryCount");
const todayLabel = document.querySelector("#todayLabel");
const dialog = document.querySelector("#entryDialog");
const form = document.querySelector("#entryForm");
const dialogTitle = document.querySelector("#dialogTitle");
const entryId = document.querySelector("#entryId");
const entryDate = document.querySelector("#entryDate");
const entryTitle = document.querySelector("#entryTitle");
const entryContent = document.querySelector("#entryContent");
const entryError = document.querySelector("#entryError");
const toast = document.querySelector("#toast");

let entries = [];

const today = new Date();
todayLabel.textContent = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(today);

function localISODate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function dateParts(value) {
  const parsed = new Date(value + "T00:00:00");
  return {
    day: new Intl.DateTimeFormat("zh-CN", { day: "2-digit" }).format(parsed),
    monthYear: new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "short",
    }).format(parsed),
    full: new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(parsed),
  };
}

async function api(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET") {
    headers.set("X-Journal-Request", "1");
  }

  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    window.location.replace("/journal/login");
    throw new Error("请先登录");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "操作失败");
  }
  if (response.status === 204) return null;
  return response.json();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 1800);
}

function createAction(label, className, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

function renderEntries() {
  feed.replaceChildren();
  entryCount.textContent = entries.length ? entries.length + " 篇日志" : "";

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("p");
    title.textContent = "还没有日志。";
    const button = createAction("写第一篇", "primary-button compact", () => openEditor());
    empty.append(title, button);
    feed.append(empty);
    return;
  }

  entries.forEach((entry) => {
    const parts = dateParts(entry.entry_date);
    const article = document.createElement("article");
    article.className = "entry-card";

    const dateBlock = document.createElement("time");
    dateBlock.className = "entry-date";
    dateBlock.dateTime = entry.entry_date;
    dateBlock.title = parts.full;

    const day = document.createElement("span");
    day.className = "entry-day";
    day.textContent = parts.day;

    const monthYear = document.createElement("span");
    monthYear.className = "entry-month";
    monthYear.textContent = parts.monthYear;
    dateBlock.append(day, monthYear);

    const body = document.createElement("div");
    body.className = "entry-body";

    const heading = document.createElement("h2");
    heading.textContent = entry.title;

    const content = document.createElement("p");
    content.className = "entry-content";
    content.textContent = entry.content;

    const actions = document.createElement("div");
    actions.className = "entry-actions";
    actions.append(
      createAction("编辑", "text-button", () => openEditor(entry)),
      createAction("删除", "text-button danger", () => removeEntry(entry))
    );

    body.append(heading, content, actions);
    article.append(dateBlock, body);
    feed.append(article);
  });
}

function openEditor(entry = null) {
  form.reset();
  entryError.textContent = "";

  if (entry) {
    dialogTitle.textContent = "编辑日志";
    entryId.value = String(entry.id);
    entryDate.value = entry.entry_date;
    entryTitle.value = entry.title;
    entryContent.value = entry.content;
  } else {
    dialogTitle.textContent = "写日志";
    entryId.value = "";
    entryDate.value = localISODate();
  }

  dialog.showModal();
  window.setTimeout(() => entryTitle.focus(), 0);
}

function closeEditor() {
  dialog.close();
  entryError.textContent = "";
}

async function loadEntries() {
  try {
    entries = await api("/journal/api/entries");
    renderEntries();
  } catch (error) {
    if (loadingState) loadingState.textContent = error.message;
  }
}

async function removeEntry(entry) {
  if (!window.confirm("确定删除《" + entry.title + "》吗？")) return;
  try {
    await api("/journal/api/entries/" + entry.id, { method: "DELETE" });
    entries = entries.filter((item) => item.id !== entry.id);
    renderEntries();
    showToast("已删除");
  } catch (error) {
    showToast(error.message);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  entryError.textContent = "";

  const id = entryId.value;
  const payload = {
    title: entryTitle.value,
    entry_date: entryDate.value,
    content: entryContent.value,
  };

  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "保存中...";

  try {
    const saved = await api(
      id ? "/journal/api/entries/" + id : "/journal/api/entries",
      {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(payload),
      }
    );

    const existingIndex = entries.findIndex((item) => item.id === saved.id);
    if (existingIndex >= 0) entries[existingIndex] = saved;
    else entries.push(saved);

    entries.sort((a, b) => {
      const byDate = b.entry_date.localeCompare(a.entry_date);
      return byDate || b.id - a.id;
    });
    renderEntries();
    closeEditor();
    showToast("已保存");
  } catch (error) {
    entryError.textContent = Array.isArray(error.message) ? "请检查输入内容" : error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "保存";
  }
});

document.querySelector("#newEntryButton").addEventListener("click", () => openEditor());
document.querySelector("#closeDialogButton").addEventListener("click", closeEditor);
document.querySelector("#cancelEntryButton").addEventListener("click", closeEditor);
document.querySelector("#logoutButton").addEventListener("click", async () => {
  try {
    await api("/journal/api/logout", { method: "POST" });
  } finally {
    window.location.replace("/journal/login");
  }
});

dialog.addEventListener("click", (event) => {
  if (event.target === dialog) closeEditor();
});

loadEntries();
