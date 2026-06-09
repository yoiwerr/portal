/* ═══════════════════════════════════════════════════════
   ChatLab.js · Two-Column · Inline Import · Right Preview
   ═══════════════════════════════════════════════════════ */

(function () {
  "use strict";

  var API = "/api/v1";

  var S = { chats: [], target: "对方", bg: "", rag: false };
  var pf; /* pending file */

  var modal = document.getElementById("modal");
  var modalTitle = document.getElementById("modalTitle");
  var modalBody = document.getElementById("modalBody");
  var modalClose = document.getElementById("modalClose");
  var badge = document.getElementById("badge");

  var previewEmpty = document.getElementById("previewEmpty");
  var previewContent = document.getElementById("previewContent");
  var previewBar = document.getElementById("previewBar");
  var previewMsgs = document.getElementById("previewMsgs");

  function openModal(t) { modalTitle.textContent = t; modal.classList.add("open"); }
  function closeModal() { modal.classList.remove("open"); setTimeout(function () { modalBody.innerHTML = ""; }, 200); }
  modalClose.addEventListener("click", closeModal);
  modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && modal.classList.contains("open")) closeModal(); });

  function toast(msg, kind) {
    var t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
    t.textContent = msg;
    t.className = "toast " + (kind || "") + " show";
    clearTimeout(t._tid);
    t._tid = setTimeout(function () { t.classList.remove("show"); }, 2400);
  }

  function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }

  function spin(msg) { modalBody.innerHTML = '<div class="spin-w"><div class="spin"></div><p class="spin-tx">' + esc(msg) + '</p></div>'; }
  function err(msg) { modalBody.innerHTML = '<div class="box er">' + esc(msg) + '</div>'; }

  function updateBadge() {
    if (S.chats.length) {
      badge.textContent = S.chats.length + " 条消息";
      badge.className = "badge on";
    } else {
      badge.className = "badge";
    }
  }

  /* ── Preview Panel ──────────────────────────── */
  function renderPreview() {
    if (!S.chats.length) {
      previewEmpty.style.display = "flex";
      previewContent.style.display = "none";
      return;
    }
    previewEmpty.style.display = "none";
    previewContent.style.display = "flex";

    previewBar.innerHTML =
      '<span>' + S.chats.length + ' 条消息</span>' +
      '<span style="margin-left:auto;color:var(--dim);">目标：' + esc(S.target) + '</span>';

    var h = "";
    for (var i = 0; i < S.chats.length; i++) {
      var c = S.chats[i], me = (c.sender || "").indexOf("我") !== -1;
      h += '<div class="bub ' + (me ? "bub-u" : "bub-o") + '"><div class="bub-s ' + (me ? "bub-su" : "bub-so") + '">' + esc(c.sender) + " · " + esc(c.timestamp || "") + '</div><span>' + esc(c.content || "") + '</span></div>';
    }
    previewMsgs.innerHTML = h;
  }

  /* ── Import ──────────────────────────────────── */
  function initImport() {
    var dz = document.getElementById("dz");
    var fi = document.getElementById("fi");
    var fh = document.getElementById("fh");

    dz.addEventListener("click", function () { fi.click(); });
    ["dragenter","dragover"].forEach(function (ev) {
      dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("on"); });
    });
    ["dragleave","drop"].forEach(function (ev) {
      dz.addEventListener(ev, function () { dz.classList.remove("on"); });
    });
    dz.addEventListener("drop", function (e) {
      e.preventDefault();
      var f = e.dataTransfer.files[0];
      if (f) { pf = f; fh.textContent = "📄 " + f.name; }
    });
    fi.addEventListener("change", function () {
      if (fi.files[0]) { pf = fi.files[0]; fh.textContent = "📄 " + pf.name; }
    });
    document.getElementById("bs").addEventListener("click", doImport);
  }

  function readForm() {
    var a = document.getElementById("ti"), b = document.getElementById("bi"), c = document.getElementById("rc");
    if (a) S.target = a.value.trim() || "对方";
    if (b) S.bg = b.value.trim();
    if (c) S.rag = c.checked;
  }

  async function doImport() {
    readForm();
    var manual = document.getElementById("mi");
    var txt = manual ? manual.value.trim() : "";

    if (pf) {
      spin("解析文件中…");
      openModal("导入聊天记录");
      var fd = new FormData();
      fd.append("file", pf);
      fd.append("target_person", S.target);
      fd.append("save_to_rag", String(S.rag));
      try {
        var r = await fetch(API + "/upload_chat_file", { method: "POST", body: fd });
        if (!r.ok) { var t1 = await r.text(); throw new Error("HTTP " + r.status + " " + t1.slice(0, 250)); }
        var d = await r.json();
        S.chats = d.parsed_chats || [];
        updateBadge();
        renderPreview();
        toast(d.message || "已载入 " + S.chats.length + " 条", "ok");
        pf = null;
        document.getElementById("fh").textContent = "TXT · JSON · PNG · JPG · WebP";
        closeModal();
      } catch (e) { err(e.message); }
      return;
    }

    if (txt) {
      spin("解析文本中…");
      openModal("导入聊天记录");
      try {
        var r2 = await fetch(API + "/import_chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ format_type: "text", text_data: txt, target_person: S.target, save_to_rag: S.rag }),
        });
        if (!r2.ok) { var t2 = await r2.text(); throw new Error("HTTP " + r2.status + " " + t2.slice(0, 250)); }
        var d2 = await r2.json();
        S.chats = d2.data || [];
        updateBadge();
        renderPreview();
        toast(d2.message || "已载入 " + S.chats.length + " 条", "ok");
        closeModal();
      } catch (e) { err(e.message); }
      return;
    }

    toast("请选择文件或粘贴聊天记录", "bad");
  }

  /* ── Analysis (modal results) ───────────────── */
  async function analyze(ep, title) {
    if (!S.chats.length) {
      modalBody.innerHTML = '<div class="box er" style="text-align:center;">请先在左侧导入聊天记录</div>';
      openModal(title);
      return;
    }
    openModal(title);
    spin("AI 分析中…");

    var p = {
      target_person: S.target,
      recent_chat: S.chats.map(function (c) { return { sender: c.sender, content: c.content, timestamp: c.timestamp || "" }; }),
    };
    if (S.bg) p.background_info = S.bg;

    try {
      var r = await fetch(API + "/" + ep, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
      if (!r.ok) { var t = await r.text(); throw new Error("HTTP " + r.status + " " + t.slice(0, 250)); }
      var d = await r.json();

      if (ep === "imitate") {
        modalBody.innerHTML =
          '<div class="rs"><p class="rs-l">对方可能会这样回复</p><div class="box">' + esc(d.reply || "—") + '</div></div>' +
          '<p style="font-size:.65rem;color:var(--dim);text-align:center;margin-top:.6rem;">AI 生成 · 仅供娱乐</p>';

      } else if (ep === "emotion_analyze") {
        var sc = d.emotion_score ?? 0;
        var col = sc >= 70 ? "var(--green)" : sc >= 40 ? "var(--amber)" : "var(--red)";
        var lb = sc >= 70 ? "积极" : sc >= 40 ? "中性" : "消极";
        modalBody.innerHTML =
          '<div class="met"><div class="met-v" style="color:' + col + ';">' + sc + '</div><div class="met-l">情感指数 / 100 · ' + lb + '</div></div>' +
          '<div style="text-align:center;margin-bottom:.6rem;"><span class="tag">' + esc(d.dominant_emotion || "—") + '</span></div>' +
          '<hr class="dv">' +
          '<div class="rs"><p class="rs-l">分析依据</p><div class="box">' + esc(d.analysis_reasoning || "—") + '</div></div>';

      } else if (ep === "analyze_atmosphere") {
        var steps = "", sugs = d.actionable_suggestions || [];
        for (var i = 0; i < sugs.length; i++) { steps += '<div class="step"><span class="step-n">' + (i + 1) + '</span><span>' + esc(sugs[i]) + '</span></div>'; }
        modalBody.innerHTML =
          '<div class="rs"><p class="rs-l">气氛总结</p><div class="box">' + esc(d.atmosphere_summary || "—") + '</div></div>' +
          '<div class="rs"><p class="rs-l">权力动态</p><div class="box ok">' + esc(d.power_dynamic || "—") + '</div></div>' +
          (steps ? '<div class="rs"><p class="rs-l">行动建议</p>' + steps + '</div>' : "");
      }
    } catch (e) { err(e.message); }
  }

  /* ── Init ────────────────────────────────────── */
  initImport();
  renderPreview();

  document.getElementById("btnImitate").addEventListener("click", function () { analyze("imitate", "模仿回复"); });
  document.getElementById("btnEmotion").addEventListener("click", function () { analyze("emotion_analyze", "情感分析"); });
  document.getElementById("btnAtmosphere").addEventListener("click", function () { analyze("analyze_atmosphere", "气氛分析"); });
})();
