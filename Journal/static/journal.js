const feed = document.querySelector("#entryFeed");
const entryCount = document.querySelector("#entryCount");
const searchInput = document.querySelector("#searchInput");
const form = document.querySelector("#entryForm");
const entryId = document.querySelector("#entryId");
const entryTitle = document.querySelector("#entryTitle");
const entryContent = document.querySelector("#entryContent");
const entryImages = document.querySelector("#entryImages");
const imagePreview = document.querySelector("#imagePreview");
const imageCount = document.querySelector("#imageCount");
const entryError = document.querySelector("#entryError");
const editState = document.querySelector("#editState");
const cancelEntryButton = document.querySelector("#cancelEntryButton");
const submitButton = form.querySelector('button[type="submit"]');
const toast = document.querySelector("#toast");

let entries = [];
let pendingImages = [];
let editingImages = [];

const allowedImageTypes = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);
const maxImageBytes = 8 * 1024 * 1024;
const maxImages = 9;

function localISODate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function deriveTitle(content) {
  const firstLine = content.split(/\r?\n/).find((line) => line.trim());
  return (firstLine || "无标题").trim().slice(0, 120);
}

function formatTime(entry) {
  const createdAt = new Date(entry.created_at);
  const clock = Number.isNaN(createdAt.getTime())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(createdAt);
  const today = localISODate();
  const yesterday = localISODate(new Date(Date.now() - 86_400_000));

  if (entry.entry_date === today) return "今天 " + clock;
  if (entry.entry_date === yesterday) return "昨天 " + clock;

  const date = new Date(entry.entry_date + "T00:00:00");
  const dateText = new Intl.DateTimeFormat("zh-CN", {
    year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
  return clock ? dateText + " " + clock : dateText;
}

async function api(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
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
  const filteredEntries = query ? entries.filter((entry) =>
    (entry.title + "\n" + entry.content).toLocaleLowerCase("zh-CN").includes(query)
  ) : entries;
  return [...filteredEntries].sort((a, b) => {
    const byCreatedAt = b.created_at.localeCompare(a.created_at);
    return byCreatedAt || b.id - a.id;
  });
}

function createGallery(images) {
  const gallery = document.createElement("div");
  const visibleImages = images.slice(0, 9);
  gallery.className = "post-gallery gallery-" + Math.min(visibleImages.length, 4);

  visibleImages.forEach((imageData, index) => {
    const source = typeof imageData === "string" ? imageData : imageData.url;
    const link = document.createElement("a");
    link.href = source;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", "查看动态图片 " + (index + 1));
    const image = document.createElement("img");
    image.src = source;
    image.alt = "动态图片 " + (index + 1);
    image.loading = "lazy";
    image.addEventListener("error", () => link.remove());
    link.append(image);
    gallery.append(link);
  });
  return gallery;
}

function renderEntries() {
  const filteredEntries = visibleEntries();
  feed.replaceChildren();
  entryCount.textContent = searchInput.value.trim()
    ? filteredEntries.length + " 条结果"
    : entries.length + " 条动态";

  if (!filteredEntries.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    const title = document.createElement("p");
    title.textContent = searchInput.value.trim() ? "没有找到相关动态" : "还没有动态";
    const detail = document.createElement("span");
    detail.textContent = searchInput.value.trim()
      ? "换一个关键词试试。"
      : "在上方记录第一条内容。";
    empty.append(title, detail);
    feed.append(empty);
    return;
  }

  filteredEntries.forEach((entry) => {
    const article = document.createElement("article");
    article.className = "post";

    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    const avatarImage = document.createElement("img");
    avatarImage.src = "/journal/assets/avatar.jpg";
    avatarImage.alt = "";
    avatar.append(avatarImage);

    const main = document.createElement("div");
    main.className = "post-main";

    const header = document.createElement("header");
    header.className = "post-header";
    const identity = document.createElement("div");
    const author = document.createElement("strong");
    author.textContent = "我";
    identity.append(author);
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.created_at;
    timestamp.textContent = formatTime(entry);
    header.append(identity, timestamp);

    main.append(header);

    if (entry.title && entry.title !== deriveTitle(entry.content)) {
      const heading = document.createElement("h2");
      heading.textContent = entry.title;
      main.append(heading);
    }

    const content = document.createElement("p");
    content.className = "post-content";
    content.textContent = entry.content;
    main.append(content);

    if (Array.isArray(entry.images) && entry.images.length) {
      main.append(createGallery(entry.images));
    }

    const footer = document.createElement("footer");
    footer.className = "post-footer";
    footer.append(
      createAction("编辑", "post-action", () => startEditing(entry)),
      createAction("删除", "post-action danger", () => removeEntry(entry))
    );
    main.append(footer);
    article.append(avatar, main);
    feed.append(article);
  });
}

function clearPendingImages() {
  pendingImages.forEach((item) => URL.revokeObjectURL(item.url));
  pendingImages = [];
}

function composerImage(source, label, removeHandler) {
  const item = document.createElement("div");
  item.className = "composer-image";
  const image = document.createElement("img");
  image.src = source;
  image.alt = label;
  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "image-remove";
  removeButton.textContent = "移除";
  removeButton.addEventListener("click", removeHandler);
  item.append(image, removeButton);
  return item;
}

function renderComposerImages() {
  imagePreview.replaceChildren();

  editingImages.forEach((imageData, index) => {
    const source = typeof imageData === "string" ? imageData : imageData.url;
    imagePreview.append(
      composerImage(source, "已保存图片 " + (index + 1), () => removeStoredImage(imageData))
    );
  });

  pendingImages.forEach((item, index) => {
    imagePreview.append(
      composerImage(item.url, "待上传图片 " + (index + 1), () => {
        URL.revokeObjectURL(item.url);
        pendingImages = pendingImages.filter((candidate) => candidate !== item);
        renderComposerImages();
      })
    );
  });

  const count = editingImages.length + pendingImages.length;
  imagePreview.hidden = count === 0;
  imageCount.textContent = count ? count + "/" + maxImages : "";
  entryImages.disabled = count >= maxImages;
}

async function removeStoredImage(imageData) {
  if (typeof imageData === "string") {
    editingImages = editingImages.filter((image) => image !== imageData);
    renderComposerImages();
    return;
  }
  if (!window.confirm("确定移除这张图片吗？")) return;
  try {
    await api("/journal/api/images/" + imageData.id, { method: "DELETE" });
    editingImages = editingImages.filter((image) => image.id !== imageData.id);
    const currentEntry = entries.find((entry) => String(entry.id) === entryId.value);
    if (currentEntry) currentEntry.images = [...editingImages];
    renderComposerImages();
    renderEntries();
    showToast("图片已移除");
  } catch (error) {
    entryError.textContent = error.message;
  }
}

function resetComposer() {
  clearPendingImages();
  editingImages = [];
  form.reset();
  entryId.value = "";
  entryError.textContent = "";
  editState.hidden = true;
  cancelEntryButton.hidden = true;
  submitButton.textContent = "发布";
  renderComposerImages();
}

function startEditing(entry) {
  clearPendingImages();
  entryId.value = String(entry.id);
  entryTitle.value = entry.title;
  entryContent.value = entry.content;
  entryError.textContent = "";
  editState.hidden = false;
  cancelEntryButton.hidden = false;
  submitButton.textContent = "保存";
  editingImages = [...(entry.images || [])];
  renderComposerImages();
  form.closest(".composer").scrollIntoView({ behavior: "smooth", block: "center" });
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
  if (!window.confirm("确定删除这条动态吗？")) return;
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
    let saved = await api(id ? "/journal/api/entries/" + id : "/journal/api/entries", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });

    if (pendingImages.length) {
      const imageData = new FormData();
      pendingImages.forEach((item) => imageData.append("files", item.file));
      try {
        saved = await api("/journal/api/entries/" + saved.id + "/images", {
          method: "POST",
          body: imageData,
        });
      } catch (uploadError) {
        const savedIndex = entries.findIndex((entry) => entry.id === saved.id);
        if (savedIndex >= 0) entries[savedIndex] = saved;
        else entries.unshift(saved);
        entryId.value = String(saved.id);
        editingImages = [...(saved.images || [])];
        renderComposerImages();
        renderEntries();
        throw new Error("动态已保存，但图片上传失败：" + uploadError.message);
      }
    }

    const existingIndex = entries.findIndex((entry) => entry.id === saved.id);
    if (existingIndex >= 0) entries[existingIndex] = saved;
    else entries.unshift(saved);
    resetComposer();
    renderEntries();
    showToast(id ? "已保存" : "已发布");
  } catch (error) {
    entryError.textContent = error.message;
    submitButton.textContent = entryId.value ? "保存" : "发布";
  } finally {
    submitButton.disabled = false;
  }
});

entryImages.addEventListener("change", () => {
  entryError.textContent = "";
  const selectedFiles = Array.from(entryImages.files || []);
  entryImages.value = "";
  if (!selectedFiles.length) return;

  if (editingImages.length + pendingImages.length + selectedFiles.length > maxImages) {
    entryError.textContent = "每条动态最多 " + maxImages + " 张图片";
    return;
  }

  const invalidType = selectedFiles.find((file) => !allowedImageTypes.has(file.type));
  if (invalidType) {
    entryError.textContent = "仅支持 JPEG、PNG、WebP 或 GIF 图片";
    return;
  }

  const oversized = selectedFiles.find((file) => file.size > maxImageBytes);
  if (oversized) {
    entryError.textContent = "单张图片不能超过 8 MB";
    return;
  }

  selectedFiles.forEach((file) => {
    pendingImages.push({ file, url: URL.createObjectURL(file) });
  });
  renderComposerImages();
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

loadEntries();
