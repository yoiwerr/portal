const feed = document.querySelector("#entryFeed");
const entryCount = document.querySelector("#entryCount");
const sidebarEntryCount = document.querySelector("#sidebarEntryCount");
const todayLabel = document.querySelector("#todayLabel");
const searchInput = document.querySelector("#searchInput");
const form = document.querySelector("#entryForm");
const entryId = document.querySelector("#entryId");
const entryTitle = document.querySelector("#entryTitle");
const entryContent = document.querySelector("#entryContent");
const entryError = document.querySelector("#entryError");
const editState = document.querySelector("#editState");
const cancelEntryButton = document.querySelector("#cancelEntryButton");
const submitButton = form.querySelector('button[type="submit"]');
const toast = document.querySelector("#toast");

let entries = [];

todayLabel.textContent = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(new Date());

function localISODate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function dateParts(entry) {
  const dateValue = entry.entry_date + "T00:00:00";
  const parsedDate = new Date(dateValue);
  const createdAt = new Date(entry.created_at);
  const validCreatedAt = !Number.isNaN(createdAt.getTime());

  return {
    day: new Intl.DateTimeFormat("zh-CN", { day: "2-digit" }).format(parsedDate),
    month: new Intl.DateTimeFormat("zh-CN", { month: "short" }).format(parsedDate),
    full: new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(parsedDate),
    time: validCreatedAt
      ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(createdAt)
      : "",
  };
}

function deriveTitle(content) {
  const firstLine = content.split(/\r?\n/).find((line) => line.trim());
  return (firstLine || "无标题").trim().slice(0, 120);
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
    const detail = Array.isArray(data.detail) ? "请检查输入内容" : data.detail;
    throw new Error(detail || "操作失败");
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

function visibleEntries() {
  const query = searchInput.value.trim().toLocaleLowerCase("zh-CN");
  if (!query) return entries;
  return entries.filter((entry) =>
    (entry.title + "\n" + entry.content).toLocaleLowerCase("zh-CN").includes(query)
  );
}

function renderEntries() {
  const filteredEntries = visibleEntries();
  feed.replaceChildren();
  entryCount.textContent = searchInput.value.trim()
    ? filteredEntries.length + " 条结果"
    : entries.length + " 条记录";
  sidebarEntryCount.textContent = String(entries.length);

  if (!filteredEntries.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("p");
    title.textContent = searchInput.value.trim() ? "没有匹配的日志" : "还没有日志";
    const detail = document.createElement("span");
    detail.textContent = searchInput.value.trim()
      ? "换一个关键词再试。"
      : "在上方记录第一条内容。";
    empty.append(title, detail);
    feed.append(empty);
    return;
  }

  filteredEntries.forEach((entry) => {
    const parts = dateParts(entry);
    const article = document.createElement("article");
    article.className = "timeline-entry";

    const rail = document.createElement("div");
    rail.className = "entry-rail";

    const dateBlock = document.createElement("time");
    dateBlock.className = "entry-date";
    dateBlock.dateTime = entry.entry_date;
    dateBlock.title = parts.full;

    const day = document.createElement("span");
    day.className = "entry-day";
    day.textContent = parts.day;

    const month = document.createElement("span");
    month.className = "entry-month";
    month.textContent = parts.month;
    dateBlock.append(day, month);

    const marker = document.createElement("span");
    marker.className = "timeline-marker";
    marker.setAttribute("aria-hidden", "true");
    rail.append(dateBlock, marker);

    const body = document.createElement("div");
    body.className = "entry-body";

    const meta = document.createElement("div");
    meta.className = "entry-meta";
    const timestamp = document.createElement("span");
    timestamp.textContent = parts.time ? parts.full + " · " + parts.time : parts.full;
    meta.append(timestamp);

    const heading = document.createElement("h2");
    heading.textContent = entry.title;

    const content = document.createElement("p");
    content.className = "entry-content";
    content.textContent = entry.content;

    const actions = document.createElement("div");
    actions.className = "entry-actions";
    actions.append(
      createAction("编辑", "entry-action", () => startEditing(entry)),
      createAction("删除", "entry-action danger", () => removeEntry(entry))
    );

    body.append(meta, heading, content, actions);
    article.append(rail, body);
    feed.append(article);
  });
}

function resetComposer() {
  form.reset();
  entryId.value = "";
  entryError.textContent = "";
  editState.hidden = true;
  cancelEntryButton.hidden = true;
  submitButton.textContent = "发布";
}

function startEditing(entry) {
  entryId.value = String(entry.id);
  entryTitle.value = entry.title;
  entryContent.value = entry.content;
  entryError.textContent = "";
  editState.hidden = false;
  cancelEntryButton.hidden = false;
  submitButton.textContent = "保存";
  form.closest(".composer").scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => entryContent.focus(), 250);
}

async function loadEntries() {
  try {
    entries = await api("/journal/api/entries");
    renderEntries();
  } catch (error) {
    feed.textContent = error.message;
  }
}

async function removeEntry(entry) {
  if (!window.confirm("确定删除《" + entry.title + "》吗？")) return;
  try {
    await api("/journal/api/entries/" + entry.id, { method: "DELETE" });
    entries = entries.filter((item) => item.id !== entry.id);
    if (entryId.value === String(entry.id)) resetComposer();
    renderEntries();
    showToast("已删除");
  } catch (error) {
    showToast(error.message);
  }
}

async function logout() {
  try {
    await api("/journal/api/logout", { method: "POST" });
  } finally {
    window.location.replace("/journal/login");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  entryError.textContent = "";

  const id = entryId.value;
  const currentEntry = entries.find((entry) => String(entry.id) === id);
  const content = entryContent.value.trim();
  const payload = {
    title: entryTitle.value.trim() || deriveTitle(content),
    entry_date: currentEntry ? currentEntry.entry_date : localISODate(),
    content,
  };

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

    const existingIndex = entries.findIndex((entry) => entry.id === saved.id);
    if (existingIndex >= 0) entries[existingIndex] = saved;
    else entries.unshift(saved);

    entries.sort((a, b) => {
      const byDate = b.entry_date.localeCompare(a.entry_date);
      return byDate || b.id - a.id;
    });
    resetComposer();
    renderEntries();
    showToast(id ? "已保存" : "已发布");
  } catch (error) {
    entryError.textContent = error.message;
    submitButton.textContent = id ? "保存" : "发布";
  } finally {
    submitButton.disabled = false;
  }
});

entryContent.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    form.requestSubmit();
  }
});

searchInput.addEventListener("input", renderEntries);
cancelEntryButton.addEventListener("click", resetComposer);
document.querySelector("#logoutButton").addEventListener("click", logout);
document.querySelector("#mobileLogoutButton").addEventListener("click", logout);

loadEntries();
