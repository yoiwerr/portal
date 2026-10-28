/**
 * dude — new project planning, with node-level SSE progress.
 */
(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════
     Auth — JWT token management (shared with Go AgentGateway)
     ═══════════════════════════════════════════════════════ */
  var AUTH_API = '/dude/api/v1';
  var LOGIN_URL = '/dude/auth/';
  var ADMIN_URL = '/dude/admin/';
  // Resolve under /dude/ in Portal and / in standalone development.
  var APP_API = new URL('api/', window.location.href || 'http://localhost/').pathname.replace(/\/$/, '');

  function getToken() { return localStorage.getItem('alfred_token'); }
  function getRefreshToken() { return localStorage.getItem('alfred_refresh'); }
  function authHeaders() {
    return { 'Authorization': 'Bearer ' + getToken() };
  }

  function clearAuthAndRedirect() {
    ['alfred_token', 'alfred_refresh', 'alfred_user'].forEach(function(key) { localStorage.removeItem(key); });
    window.location.href = LOGIN_URL;
    return null;
  }

  async function refreshAccessToken() {
    var rt = getRefreshToken();
    if (!rt) return false;
    var resp = await fetch(AUTH_API + '/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (resp.status === 401) return false;
    if (!resp.ok) throw new Error('登录服务暂时不可用，请稍后重试');
    var data = await resp.json();
    if (![data.access_token, data.refresh_token].every(function(value) { return typeof value === 'string' && value.trim(); })) {
      throw new Error('登录服务返回异常，请稍后重试');
    }
    localStorage.setItem('alfred_token', data.access_token);
    localStorage.setItem('alfred_refresh', data.refresh_token);
    return true;
  }

  async function checkAuth() {
    try {
      if (getToken()) {
        var resp = await fetch(AUTH_API + '/auth/me', { headers: authHeaders() });
        if (resp.ok) { var me = await resp.json(); setupUserUI(me); return me; }
        if (resp.status !== 401) throw new Error('auth_service_unavailable');
      }
      if (await refreshAccessToken()) {
        var retry = await fetch(AUTH_API + '/auth/me', { headers: authHeaders() });
        if (retry.ok) { var user = await retry.json(); setupUserUI(user); return user; }
        if (retry.status !== 401) throw new Error('auth_service_unavailable');
      }
      return clearAuthAndRedirect();
    } catch (_) {
      var area = document.getElementById('topbarUserArea');
      if (area) area.textContent = '登录服务暂时不可用，请稍后刷新重试';
      return null;
    }
  }

  function setupUserUI(me) {
    var el = document.getElementById('topbarUserArea');
    if (!el) return;
    var isAdmin = me.role === 'admin';
    el.innerHTML =
      '<span class="topbar-user">' + escapeHtml(me.username) + ' <span class="topbar-admin-badge">' + (isAdmin ? '管理员' : '普通用户') + '</span></span>' +
      (isAdmin ? '<a href="' + ADMIN_URL + '" class="topbar-link topbar-admin-link">管理后台</a>' : '') +
      '<button type="button" class="topbar-link" onclick="window.dudeLogout()">退出</button>';
  }

  window.dudeLogout = function () {
    var rt = getRefreshToken();
    var token = getToken();
    if (rt && token) {
      fetch(AUTH_API + '/auth/logout', {
        method: 'POST',
        headers: Object.assign(authHeaders(), { 'Content-Type': 'application/json' }),
        body: JSON.stringify({ refresh_token: rt }),
      }).catch(function () {});
    }
    clearAuthAndRedirect();
  };

  async function fetchWithAuth(url, options) {
    options = options || {};
    options.headers = Object.assign(options.headers || {}, authHeaders());
    var resp = await fetch(url, options);

    // 401 → try refresh once, then retry
    if (resp.status === 401) {
      var ok = await refreshAccessToken();
      if (ok) {
        options.headers = Object.assign(options.headers || {}, authHeaders());
        var retried = await fetch(url, options);
        if (retried.status !== 401) return retried;
      }
      // Refresh failed → redirect to login
      clearAuthAndRedirect();
      throw new Error('auth_expired');
    }
    return resp;
  }

  /* ═══════════════════════════════════════════════════════
     State
     ═══════════════════════════════════════════════════════ */
  var sessionId = null;
  var currentContract = null;
  var contractConfirmed = false;
  var hasStarted = false;
  var isBusy = false;
  var authReady = false;
  var summarySeen = false;
  var importedContext = '';
  var currentModule = 'auto';
  var clarifyRound = 0;
  var accumulatedDimensions = {};

  /* ═══════════════════════════════════════════════════════
     Init
     ═══════════════════════════════════════════════════════ */
  function init() {
    // Auth check — redirects to login if not authenticated
    checkAuth().then(function(user) {
      if (!user) return; // checkAuth handles redirect
      authReady = true;
      setSendDisabled(false);
      document.getElementById('chatArea').addEventListener('click', function(e) {
        if (e.target === this) document.getElementById('userInput').focus();
      });
    });
  }

  /* Panels use a drawer on mobile and an inline summary on desktop. */
  function syncDrawer() {
    var drawer = !document.getElementById('contractSidebar').hidden && window.innerWidth <= 1000;
    document.getElementById('panelBackdrop').hidden = !drawer;
    document.getElementById('workspace').inert = drawer;
    var panel = document.getElementById('contractSidebar');
    if (drawer) { panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); }
    else { panel.removeAttribute('role'); panel.removeAttribute('aria-modal'); }
    if (drawer && !panel.contains(document.activeElement)) panel.focus();
  }

  window.toggleSummary = function (open, auto) {
    var panel = document.getElementById('contractSidebar');
    open = typeof open === 'boolean' ? open : panel.hidden;
    if (open) window.toggleTurnNav(false, true);
    panel.hidden = !open;
    document.body.classList.toggle('summary-open', open);
    document.getElementById('summaryToggle').setAttribute('aria-expanded', String(open));
    syncDrawer();
    if (!auto) (open ? panel : document.getElementById('summaryToggle')).focus();
  };

  window.toggleTurnNav = function (open, quiet) {
    var panel = document.getElementById('turnNav');
    open = typeof open === 'boolean' ? open : panel.hidden;
    panel.hidden = !open;
    document.getElementById('navToggle').setAttribute('aria-expanded', String(open));
    if (!quiet) (open ? panel : document.getElementById('navToggle')).focus();
  };

  window.closePanels = function () {
    if (!document.getElementById('turnNav').hidden) window.toggleTurnNav(false);
    if (!document.getElementById('contractSidebar').hidden) window.toggleSummary(false);
  };

  window.startNewIdea = function () {
    if (isBusy) return;
    if (hasStarted && !window.confirm('开始新想法会清空当前页面的对话。请先复制或下载需要保留的内容。继续吗？')) return;
    window.location.reload();
  };

  window.addEventListener('resize', syncDrawer);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') window.closePanels();
    var panel = document.getElementById('contractSidebar');
    if (event.key !== 'Tab' || panel.hidden || window.innerWidth > 1000) return;
    var controls = Array.from(panel.querySelectorAll('button:not(:disabled), input, textarea, [tabindex="0"]')).filter(function(el) { return el.getClientRects().length; });
    if (!controls.length) { event.preventDefault(); return; }
    var first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  /* ═══════════════════════════════════════════════════════
     Turn Navigation (right sidebar)
     ═══════════════════════════════════════════════════════ */
  var turnCount = 0;
  var pendingUserMsg = null;
  var turnObserver = null;

  function initTurnObserver() {
    if (turnObserver) return;
    turnObserver = new IntersectionObserver(function(entries) {
      var best = null;
      entries.forEach(function(e) {
        if (e.isIntersecting && (!best || e.intersectionRatio > best.intersectionRatio)) {
          best = e;
        }
      });
      if (best) {
        var turnIdx = best.target.getAttribute('data-turn');
        if (turnIdx !== null) highlightTurnNode(parseInt(turnIdx));
      }
    }, { threshold: [0, 0.3, 0.6, 1] });
  }

  function addTurnNode(userText, afuText) {
    initTurnObserver();
    turnCount++;
    var idx = turnCount;
    var shortLabel = userLabel(userText);

    var list = document.getElementById('turnNavList');
    if (!list) return;
    var btn = document.createElement('button');
    btn.className = 'turn-node';
    btn.id = 'turnNode' + idx;
    btn.innerHTML =
      '<span class="turn-line-top"></span>' +
      '<span class="turn-line-bottom"></span>' +
      '<span class="turn-dot"></span>' +
      '<span class="turn-label">' + escapeHtml(shortLabel) + '</span>' +
      '<span class="turn-tooltip">第' + idx + '轮 · ' + escapeHtml(shortLabel) + '</span>';
    btn.onclick = function() { scrollToTurn(idx); };
    list.appendChild(btn);
    document.getElementById('navEmpty').hidden = true;

    var msgs = document.getElementById('messages');
    if (msgs) {
      var afuMsgs = msgs.querySelectorAll('.msg-afu');
      var lastAfu = afuMsgs[afuMsgs.length - 1];
      if (lastAfu) {
        lastAfu.setAttribute('data-turn', idx);
        turnObserver.observe(lastAfu);
      }
    }
    var userMsgs = document.getElementById('messages').querySelectorAll('.msg-user');
    var lastUser = userMsgs[userMsgs.length - 1];
    if (lastUser) lastUser.setAttribute('data-turn', idx);

    highlightTurnNode(idx);
  }

  function highlightTurnNode(idx) {
    document.querySelectorAll('.turn-node').forEach(function(n) {
      n.classList.remove('active');
    });
    var node = document.getElementById('turnNode' + idx);
    if (node) node.classList.add('active');
  }

  function scrollToTurn(idx) {
    var el = document.querySelector('.msg-afu[data-turn="' + idx + '"]');
    if (!el) el = document.querySelector('.msg-user[data-turn="' + idx + '"]');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      highlightTurnNode(idx);
      window.toggleTurnNav(false);
    }
  }

  function userLabel(text) {
    var t = (text || '').replace(/\s+/g, ' ').trim();
    if (t.length <= 12) return t;
    return t.substring(0, 10) + '…';
  }

  /* ═══════════════════════════════════════════════════════
     Contract Sidebar
     ═══════════════════════════════════════════════════════ */
  function renderContract(contract) {
    if (!contract || !contract.goal) return;
    currentContract = contract;
    contractConfirmed = Boolean(contract.confirmed_by_user);
    document.getElementById('summaryToggle').hidden = false;
    if (!summarySeen) {
      summarySeen = true;
      if (window.innerWidth > 1000) window.toggleSummary(true, true);
    }

    var empty = document.getElementById('contractEmpty');
    var card = document.getElementById('contractCard');
    if (empty) empty.style.display = 'none';
    if (card) card.style.display = 'flex';

    setText('ccGoal', contract.goal || '');
    var scope = contract.scope || {};
    setList('ccScopeIn', scope.in || scope.in_ || []);
    setList('ccScopeOut', scope.out || []);
    setList('ccConstraints', contract.constraints || []);
    toggleSection('ccConstraintsSection', contract.constraints);
    setListCheck('ccAcceptance', contract.acceptance || []);
    toggleSection('ccAcceptanceSection', contract.acceptance);
    setListWarn('ccRisks', contract.risks || []);
    toggleSection('ccRisksSection', contract.risks);

    var deliv = contract.deliverables || {};
    var parts = [];
    if (deliv.format) parts.push('格式: ' + deliv.format);
    if (deliv.artifacts && deliv.artifacts.length) parts.push('产物: ' + deliv.artifacts.join(', '));
    setText('ccDeliverables', parts.join(' · '));
    toggleSection('ccDeliverablesSection', parts.length > 0);

    var conf = contract.confidence || 0;
    var pct = Math.round(Math.max(0, Math.min(1, Number(conf) || 0)) * 100);
    setText('ccConfPct', pct + '%');
    var bar = document.getElementById('ccConfBar');
    if (bar) bar.style.width = pct + '%';

    var status = contract.status || (contract.confirmed_by_user ? 'confirmed' : 'draft');
    updateContractStatus(status);

    var actions = document.getElementById('ccActions');
    if (actions) {
      actions.style.display = (contract.confirmed_by_user || contractConfirmed) ? 'none' : 'flex';
    }
  }

  function updateContractStatus(status) {
    var el = document.getElementById('ccStatus');
    if (!el) return;
    var badge = el.querySelector('.cc-status-badge');
    if (!badge) { badge = document.createElement('span'); badge.className = 'cc-status-badge'; el.appendChild(badge); }
    badge.className = 'cc-status-badge ' + (status || 'draft');
    badge.textContent = status === 'confirmed' ? '已确认' : status === 'executing' ? '正在整理…' : status === 'completed' ? '方案已整理' : '待确认';
  }

  window.confirmContract = async function () {
    if (!currentContract || !sessionId) return;
    showInlineError('summaryError', '');
    try {
      var resp = await fetchWithAuth(APP_API + '/chat/' + encodeURIComponent(sessionId) + '/contract/confirm', { method: 'POST' });
      if (!resp.ok) throw new Error('确认未成功，请稍后重试。');
      if (resp.ok) {
        var data = await resp.json();
        contractConfirmed = true;
        currentContract = data.contract;
        updateContractStatus('confirmed');
        var actions = document.getElementById('ccActions');
        if (actions) actions.style.display = 'none';
        var bar = document.getElementById('ccConfBar');
        if (bar) bar.style.width = '100%';
        setText('ccConfPct', '100%');
      }
    } catch (e) {
      showInlineError('summaryError', '确认未成功，请检查连接后重试。');
    }
  };

  window.modifyContract = function () {
    showInlineError('summaryError', '');
    document.getElementById('ccBtnConfirm').disabled = true;
    makeEditable('ccGoal', 'goal', 'text');
    makeEditableList('ccScopeIn', 'scope.in');
    makeEditableList('ccScopeOut', 'scope.out');
    makeEditableList('ccConstraints', 'constraints');
    makeEditableList('ccAcceptance', 'acceptance');
    makeEditableList('ccRisks', 'risks');
    var btn = document.getElementById('ccBtnModify');
    if (btn) {
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"/></svg><span>保存修改</span>';
      btn.onclick = saveContractEdits;
    }
    updateContractStatus('draft');
    contractConfirmed = false;
  };

  function makeEditable(elId, field, type) {
    var el = document.getElementById(elId);
    if (!el || !currentContract) return;
    var value = type === 'text' ? (currentContract.goal || '') : '';
    el.innerHTML = '<input class="cc-edit" id="edit_' + field + '" value="' + escapeAttr(value) + '" aria-label="想做什么" placeholder="描述项目目标">';
  }

  function makeEditableList(elId, field) {
    var el = document.getElementById(elId);
    if (!el || !currentContract) return;
    var items = [];
    if (field === 'scope.in') items = (currentContract.scope || {}).in || (currentContract.scope || {}).in_ || [];
    else if (field === 'scope.out') items = (currentContract.scope || {}).out || [];
    else if (field === 'constraints') items = currentContract.constraints || [];
    else if (field === 'acceptance') items = currentContract.acceptance || [];
    else if (field === 'risks') items = currentContract.risks || [];
    var labels = {'scope.in': '先做这些', 'scope.out': '暂时不做', constraints: '需要注意的条件', acceptance: '怎样算做好', risks: '需要留意的问题'};
    var html = '<textarea class="cc-edit cc-edit-ta" id="edit_' + field + '" aria-label="' + labels[field] + '" placeholder="每行一项">' + escapeHtml(items.join('\n')) + '</textarea>';
    html += '<p class="cc-edit-hint">每行一项，修改后点"保存修改"</p>';
    el.innerHTML = html;
  }

  async function saveContractEdits() {
    if (!currentContract || !sessionId) return;
    var updates = {};
    var goalEl = document.getElementById('edit_goal');
    if (goalEl) updates.goal = goalEl.value.trim();
    var scopeInEl = document.getElementById('edit_scope.in');
    var scopeOutEl = document.getElementById('edit_scope.out');
    if (scopeInEl || scopeOutEl) {
      updates.scope = {};
      if (scopeInEl) updates.scope['in'] = scopeInEl.value.split('\n').filter(function(s) { return s.trim(); });
      if (scopeOutEl) updates.scope.out = scopeOutEl.value.split('\n').filter(function(s) { return s.trim(); });
    }
    ['constraints', 'acceptance', 'risks'].forEach(function(f) {
      var el = document.getElementById('edit_' + f);
      if (el) updates[f] = el.value.split('\n').filter(function(s) { return s.trim(); });
    });
    try {
      var resp = await fetchWithAuth(APP_API + '/chat/' + encodeURIComponent(sessionId) + '/contract/update', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updates)
      });
      if (!resp.ok) throw new Error('保存失败');
      var data = await resp.json(); currentContract = data.contract; renderContract(currentContract);
      showInlineError('summaryError', '');
      document.getElementById('ccBtnConfirm').disabled = false;
    } catch (e) {
      showInlineError('summaryError', '修改尚未保存，请检查连接后重试。');
      return;
    }
    var btn = document.getElementById('ccBtnModify');
    if (btn) {
      btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg><span>修改</span>';
      btn.onclick = window.modifyContract;
    }
  }

  function escapeAttr(s) { if (!s) return ''; return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  /* ═══════════════════════════════════════════════════════
     Send Message → SSE (progress events only, no tokens)
     ═══════════════════════════════════════════════════════ */
  window.sendMessage = async function () {
    if (isBusy || !authReady) return;
    var input = document.getElementById('userInput');
    var text = input.value.trim();
    if (!text) return;
    showInlineError('composerError', '');

    input.value = '';
    input.style.height = 'auto';

    if (!hasStarted) { hasStarted = true; hideEmptyState(); }

    appendUserMessage(text);
    setSendDisabled(true);
    isBusy = true;

    var thinkingEl = appendThinking();

    var body = JSON.stringify({
      message: text,
      session_id: sessionId || null,
      module: currentModule,
      background: '',
      extra_context: importedContext || '',
      clarify_round: clarifyRound,
      dimensions: accumulatedDimensions
    });

    importedContext = '';

    try {
      var response = await fetchWithAuth(APP_API + '/chat/message', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: body
      });
      if (!response.ok) throw new Error(response.status === 503 ? '服务还没有准备好，请稍后重试。' : '消息未能发送，请稍后重试。');
      await handleSSEProgress(response, thinkingEl);
    } catch (err) {
      console.error('[Chat] fetch failed:', err);
      removeThinking(thinkingEl);
      showInlineError('composerError', err.message === 'auth_expired' ? '登录已过期，正在返回登录页。' : '暂时未能完成回复。你的消息已保留，可以重试。');
      if (!input.value.trim()) { input.value = text; window.autoResize(input); }
    } finally {
      removeThinking(thinkingEl);
      isBusy = false;
      setSendDisabled(false);
    }
  };

  function setSendDisabled(disabled) {
    var btn = document.getElementById('sendBtn');
    if (btn) {
      btn.disabled = disabled || !authReady;
      btn.setAttribute('aria-label', disabled ? '正在等待回复' : '发送消息');
    }
  }

  /* ═══════════════════════════════════════════════════════
     Thinking Indicator
     ═══════════════════════════════════════════════════════ */
  function appendThinking() {
    var container = document.getElementById('messages');
    var div = document.createElement('div');
    div.className = 'msg msg-afu msg-thinking';
    div.id = 'msgThinking';
    var row = document.createElement('div');
    row.className = 'msg-row';
    row.innerHTML =
      '<div class="msg-body">' +
        '<div class="msg-sender">dude</div>' +
        '<div class="msg-content msg-content-thinking">' +
          '<span class="thinking-text">正在梳理你的想法</span>' +
          '<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>' +
        '</div>' +
      '</div>';
    div.appendChild(row);
    container.appendChild(div);
    scrollDown();
    return div;
  }

  function removeThinking(el) {
    if (el) el.remove();
  }

  /* ═══════════════════════════════════════════════════════
     SSE Progress Reader — node-level events only
     ═══════════════════════════════════════════════════════ */
  async function handleSSEProgress(response, thinkingEl) {
    if (!response.body) throw new Error('没有收到回复内容');
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var receivedReply = false;
    var finished = false;
    function consume(frame) {
      var lines = frame.split(/\r?\n/);
      var eventLine = lines.find(function(line) { return line.startsWith('event:'); });
      var dataLines = lines.filter(function(line) { return line.startsWith('data:'); });
      if (!dataLines.length) return; // SSE comments / heartbeat
      var eventData = JSON.parse(dataLines.map(function(line) { return line.slice(5).trimStart(); }).join('\n'));
      var type = eventData.event || (eventLine ? eventLine.slice(6).trim() : 'message');
      var payload = eventData.data !== undefined ? eventData.data : eventData;
      if (type === 'session') { sessionId = payload.session_id; currentModule = payload.module || 'auto'; }
      else if (type === 'progress') {
        var label = thinkingEl.querySelector('.thinking-text');
        if (label) label.textContent = payload.label || '正在整理方案';
      } else if (type === 'contract') renderContract(payload.contract);
      else if (type === 'clarify' || type === 'execute' || type === 'multi_agent_synthesis') {
        var reply = payload.message || payload.synthesis;
        if (typeof reply === 'string' && reply.trim()) {
          removeThinking(thinkingEl);
          appendAfuMessage(reply);
          receivedReply = true;
          clarifyRound = type === 'clarify' ? clarifyRound + 1 : 0;
        }
      } else if (type === 'error') throw new Error('回复生成失败');
      else if (type === 'done') finished = true;
    }
    try {
      while (!finished) {
        var chunk = await reader.read();
        buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
        var separator;
        while ((separator = /\r?\n\r?\n/.exec(buffer))) {
          var frame = buffer.slice(0, separator.index);
          buffer = buffer.slice(separator.index + separator[0].length);
          consume(frame);
        }
        if (chunk.done) {
          if (buffer.trim()) consume(buffer);
          break;
        }
      }
      if (!receivedReply) throw new Error('没有收到完整回复');
    } finally {
      await reader.cancel().catch(function() {});
      reader.releaseLock();
    }
  }

  /* ═══════════════════════════════════════════════════════
     DOM Builders
     ═══════════════════════════════════════════════════════ */
  function appendToolIndicator(name) {
    var container = document.getElementById('messages');
    var div = document.createElement('div');
    div.className = 'msg msg-tool tool-done';
    div.innerHTML = '<div class="tool-indicator"><span class="tool-name">' + escapeHtml(name) + '</span></div>';
    container.appendChild(div);
    scrollDown();
  }

  function appendUserMessage(text) {
    var container = document.getElementById('messages');
    var div = document.createElement('div');
    div.className = 'msg msg-user';
    div.innerHTML = '<div class="msg-bubble">' + escapeHtml(text) + '</div>';
    container.appendChild(div);
    pendingUserMsg = text;
    scrollDown();
  }

  function appendAfuMessage(text) {
    var container = document.getElementById('messages');
    var div = document.createElement('div');
    div.className = 'msg msg-afu';
    var row = document.createElement('div');
    row.className = 'msg-row';
    row.innerHTML =
      '<div class="msg-body">' +
        '<div class="msg-sender">dude</div>' +
        '<div class="msg-content">' + simpleMarkdown(text) + '</div>' +
      '</div>';
    div.appendChild(row);

    var copyRow = document.createElement('div');
    copyRow.className = 'copy-row';
    var copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>复制</span>';
    copyBtn.onclick = function () { window.copyMessage(copyBtn, text); };
    copyRow.appendChild(copyBtn);
    var dlBtn = document.createElement('button');
    dlBtn.className = 'copy-btn dl-btn';
    dlBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg><span>下载文案</span>';
    dlBtn.title = '下载为 Markdown 文件';
    dlBtn.onclick = function () { downloadMd(text); };
    copyRow.appendChild(dlBtn);
    div.appendChild(copyRow);

    container.appendChild(div);

    if (pendingUserMsg) {
      addTurnNode(pendingUserMsg, text);
      pendingUserMsg = null;
    }
    scrollDown();
  }

  /* ═══════════════════════════════════════════════════════
     Multi-Agent Perspective Cards
     ═══════════════════════════════════════════════════════ */
  function appendPerspectiveCard(data) {
    var container = document.getElementById('messages');
    var div = document.createElement('div');
    div.className = 'msg msg-afu msg-perspective';
    div.id = 'perspective-' + data.key;
    div.style.borderLeft = '2px solid ' + (data.color || '#555');
    var row = document.createElement('div');
    row.className = 'msg-row';
    row.innerHTML =
      '<div class="msg-avatar"><span style="font-size:1.5rem;line-height:40px;display:block;text-align:center">' + (data.icon || '🤖') + '</span></div>' +
      '<div class="msg-body">' +
        '<div class="msg-sender"><span style="color:' + (data.color || '') + '">' + (data.label || data.key) + '</span>' +
        ' <span class="msg-role">' + (data.elapsed_ms || 0) + 'ms</span></div>' +
        '<div class="msg-content msg-content-rich">' + simpleMarkdown(data.output || '') + '</div>' +
      '</div>';
    div.appendChild(row);
    container.appendChild(div);
    scrollDown();
  }

  /* ═══════════════════════════════════════════════════════
     Handover Card — Import
     ═══════════════════════════════════════════════════════ */
  var selectedFile = null;

  window.handleDragOver = function (e) { e.preventDefault(); e.stopPropagation(); };
  window.handleDrop = function (e) { e.preventDefault(); e.stopPropagation(); var files = e.dataTransfer.files; if (files.length > 0) setImportFile(files[0]); };
  window.handleFileSelect = function (e) { if (e.target.files.length > 0) setImportFile(e.target.files[0]); };

  function setImportFile(file) {
    selectedFile = file;
    var hint = document.getElementById('uploadHint');
    var btn = document.getElementById('btnDoImport');
    if (hint) hint.textContent = '已选择: ' + file.name + ' (' + formatSize(file.size) + ')';
    if (btn) btn.disabled = false;
    var area = document.getElementById('uploadArea');
    if (area) area.classList.add('has-file');
  }

  window.doImport = async function () {
    if (!selectedFile) return;
    var btn = document.getElementById('btnDoImport');
    if (btn) { btn.disabled = true; btn.textContent = '导入中…'; }
    try {
      var form = new FormData(); form.append('file', selectedFile);
      var resp = await fetchWithAuth(APP_API + '/sessions/import', { method: 'POST', body: form });
      if (!resp.ok) { var err = await resp.json().catch(function() { return {}; }); throw new Error(err.detail || 'HTTP ' + resp.status); }
      var result = await resp.json();
      closeModal('modalImport');
      if (result.context_text) {
        importedContext = result.context_text;
        var input = document.getElementById('userInput');
        if (input) { input.value = '继续上次的项目工作'; autoResize(input); }
        appendAfuMessage(
          '**已加载项目交接卡**\n\n' +
          (result.handover.current_goal ? '上次目标：' + result.handover.current_goal + '\n\n' : '') +
          '告诉我你想继续什么，我会基于上次的进度推进。'
        );
        if (!hasStarted) { hasStarted = true; hideEmptyState(); }
      }
    } catch (e) { alert('导入失败：' + e.message); }
    if (btn) { btn.disabled = false; btn.textContent = '导入'; }
  };

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  /* ═══════════════════════════════════════════════════════
     Helpers
     ═══════════════════════════════════════════════════════ */
  function hideEmptyState() {
    var es = document.getElementById('emptyState');
    var msgs = document.getElementById('messages');
    if (es) es.style.display = 'none';
    if (msgs) msgs.style.display = 'block';
    document.body.classList.add('is-chatting');
    document.getElementById('welcomeExtras').hidden = true;
    document.getElementById('pageFooter').hidden = true;
    document.getElementById('workspaceToolbar').hidden = false;
    var input = document.getElementById('userInput');
    input.rows = 1;
    input.placeholder = '补充你的想法，或回答 dude 的问题…';
  }

  function showInlineError(id, message) {
    var el = document.getElementById(id);
    if (el) { el.textContent = message; el.hidden = !message; }
  }

  function setText(id, text) { var el = document.getElementById(id); if (el) el.textContent = text || ''; }

  function setList(id, items) {
    var el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '';
    (items || []).forEach(function(item) { var li = document.createElement('li'); li.textContent = item; el.appendChild(li); });
  }

  function setListCheck(id, items) { setList(id, items); var el = document.getElementById(id); if (el) el.className = 'cc-list cc-list-check'; }
  function setListWarn(id, items) { setList(id, items); var el = document.getElementById(id); if (el) el.className = 'cc-list cc-list-warn'; }

  function toggleSection(id, items) {
    var el = document.getElementById(id);
    if (!el) return;
    el.style.display = (items === true || (items && items.length > 0)) ? '' : 'none';
  }

  /* ═══════════════════════════════════════════════════════
     Markdown rendering
     ═══════════════════════════════════════════════════════ */
  function simpleMarkdown(text) {
    if (!text) return '';
    // Render a small, escaped Markdown subset. Model output is never raw HTML.
    function inline(value) {
      var out = '', cursor = 0;
      var tokens = /`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:\/\/[^\s)]+|\/(?!\/)[^\s)]+)\)/g;
      var match;
      while ((match = tokens.exec(value))) {
        out += escapeHtml(value.slice(cursor, match.index));
        if (match[1] !== undefined) out += '<code>' + escapeHtml(match[1]) + '</code>';
        else if (match[2] !== undefined) out += '<strong>' + escapeHtml(match[2]) + '</strong>';
        else out += '<a href="' + escapeAttr(match[4]) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(match[3]) + '</a>';
        cursor = tokens.lastIndex;
      }
      return out + escapeHtml(value.slice(cursor));
    }
    var lines = text.replace(/\r\n/g, '\n').split('\n');
    var html = '', paragraph = [], list = '', code = null;
    function flushParagraph() { if (paragraph.length) { html += '<p>' + paragraph.map(inline).join('<br>') + '</p>'; paragraph = []; } }
    function closeList() { if (list) { html += '</' + list + '>'; list = ''; } }
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i], heading, item;
      if (/^\s*```/.test(line)) {
        flushParagraph(); closeList();
        if (code === null) code = [];
        else { html += '<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>'; code = null; }
        continue;
      }
      if (code !== null) { code.push(line); continue; }
      if (!line.trim()) { flushParagraph(); closeList(); continue; }
      if ((heading = /^(#{1,4})\s+(.+)$/.exec(line))) {
        flushParagraph(); closeList();
        var level = heading[1].length + 1;
        html += '<h' + level + '>' + inline(heading[2]) + '</h' + level + '>';
      } else if ((item = /^\s*(?:([-*])\s+|\d+[.)]\s+)(.+)$/.exec(line))) {
        flushParagraph(); var kind = item[1] ? 'ul' : 'ol';
        if (list !== kind) { closeList(); list = kind; html += '<' + kind + '>'; }
        html += '<li>' + inline(item[2]) + '</li>';
      } else if (/^\|.+\|\s*$/.test(line) && /^\|[\s:|\-]+\|\s*$/.test(lines[i + 1] || '')) {
        flushParagraph(); closeList();
        html += '<div class="table-scroll"><table class="msg-table">';
        var first = true;
        while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
          var row = lines[i++];
          if (/^\|[\s:|\-]+\|\s*$/.test(row)) continue;
          var tag = first ? 'th' : 'td'; first = false;
          html += '<tr>' + row.trim().slice(1, -1).split('|').map(function(cell) { return '<' + tag + '>' + inline(cell.trim()) + '</' + tag + '>'; }).join('') + '</tr>';
        }
        i--; html += '</table></div>';
      } else if (/^---+$/.test(line.trim())) { flushParagraph(); closeList(); html += '<hr>'; }
      else if (/^>\s?/.test(line)) { flushParagraph(); closeList(); html += '<blockquote>' + inline(line.replace(/^>\s?/, '')) + '</blockquote>'; }
      else { closeList(); paragraph.push(line); }
    }
    flushParagraph(); closeList();
    if (code !== null) html += '<pre><code>' + escapeHtml(code.join('\n')) + '</code></pre>';
    return html;
  }

  function scrollDown() {
    var area = document.getElementById('chatArea');
    if (area) area.scrollTop = area.scrollHeight;
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  /* ═══════════════════════════════════════════════════════
     Keyboard / Modal / Copy
     ═══════════════════════════════════════════════════════ */
  window.useExample = function (text) {
    var input = document.getElementById('userInput');
    input.value = text;
    input.focus();
    window.autoResize(input);
  };

  window.handleKey = function (e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      window.sendMessage();
    }
  };

  window.autoResize = function (el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 180) + 'px';
  };

  window.openModal = function (id) {
    if (id === 'modalImport') {
      selectedFile = null;
      var hint = document.getElementById('uploadHint');
      var btn = document.getElementById('btnDoImport');
      var area = document.getElementById('uploadArea');
      var fileInput = document.getElementById('fileInput');
      if (hint) hint.textContent = '支持 .md / .json 格式';
      if (btn) btn.disabled = true;
      if (area) area.classList.remove('has-file');
      if (fileInput) fileInput.value = '';
    }
    var el = document.getElementById(id);
    if (el) el.classList.add('active');
  };

  window.closeModal = function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('active');
  };

  window.closeModalBg = function (e) {
    if (e.target.classList.contains('modal-overlay')) {
      e.target.classList.remove('active');
    }
  };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.active').forEach(function (m) { m.classList.remove('active'); });
    }
  });

  window.copyMessage = function (btn, text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { showCopied(btn); }).catch(function () { fallbackCopy(btn, text); });
    } else { fallbackCopy(btn, text); }
  };

  function downloadMd(text) {
    var now = new Date();
    var ts = now.getFullYear() +
      ('0' + (now.getMonth() + 1)).slice(-2) +
      ('0' + now.getDate()).slice(-2) + '_' +
      ('0' + now.getHours()).slice(-2) +
      ('0' + now.getMinutes()).slice(-2) +
      ('0' + now.getSeconds()).slice(-2);
    var filename = 'dude_' + ts + '.md';
    var blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 200);
  }

  function fallbackCopy(btn, text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); showCopied(btn); } catch (e) {}
    document.body.removeChild(ta);
  }

  function showCopied(btn) {
    var orig = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg><span>已复制</span>';
    setTimeout(function () { btn.classList.remove('copied'); btn.innerHTML = orig; }, 1800);
  }

  init();
})();
