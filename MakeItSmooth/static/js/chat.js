/**
 * MakeItSmooth Chat Client
 * SSE streaming · Module selection · Markdown rendering
 */
(function () {
  'use strict';

  let currentModule = null;
  let sessionId = null;
  let clarifyRound = 0;
  let dimensions = {};
  let isProcessing = false;

  const MODULE_LABELS = {
    prompt_refiner: '提示词工程',
    work_arranger: '工作安排交流',
    info_retention: '信息留存',
  };

  /* ═══════════════════════════════════════════════════════
     Module Selection
     ═══════════════════════════════════════════════════════ */
  window.selectModule = function (name, el) {
    if (isProcessing) return;
    currentModule = name;
    document.querySelectorAll('.card').forEach(c => c.classList.remove('active'));
    el.classList.add('active');

    const hint = document.getElementById('selectedHint');
    hint.textContent = '已选择：' + MODULE_LABELS[name] + ' — 在下方输入你的需求';
    hint.classList.add('ready');

    document.getElementById('bgWrapper').style.display = 'block';
    document.getElementById('inputArea').style.display = 'block';
    document.getElementById('userInput').focus();
    setStatus('●', '就绪 — ' + MODULE_LABELS[name], 'var(--green)');
  };

  /* ═══════════════════════════════════════════════════════
     Send Message
     ═══════════════════════════════════════════════════════ */
  window.sendMessage = async function () {
    const input = document.getElementById('userInput');
    const msg = input.value.trim();
    if (!msg || !currentModule || isProcessing) return;

    isProcessing = true;
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    input.value = '';

    // Hide empty state
    const emptyState = document.getElementById('emptyState');
    if (emptyState) emptyState.style.display = 'none';

    // User bubble
    appendMessage('user', msg);
    setStatus('◉', '思考中...', 'var(--amber)');

    // Typing indicator
    const typingEl = appendTyping();

    const bgText = document.getElementById('bgInput').value.trim();

    try {
      const resp = await fetch('api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          module: currentModule,
          session_id: sessionId,
          background: bgText,
          clarify_round: clarifyRound,
          dimensions: dimensions,
          extra_context: '',
        }),
      });

      if (!resp.ok) {
        removeTyping(typingEl);
        const errText = await resp.text().catch(() => resp.statusText);
        appendMessage('assistant', '❌ 请求失败 HTTP ' + resp.status + ': ' + errText);
        setStatus('●', '请求失败', 'var(--red)');
        return;
      }

      // Read SSE stream
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';
      let lastEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            lastEvent = line.slice(6).trim();
            continue;
          }
          if (line.startsWith('data:') && lastEvent) {
            try {
              const data = JSON.parse(line.slice(5).trim());
              handleSSEEvent(lastEvent, data);
              if (lastEvent === 'clarify' || lastEvent === 'execute') {
                fullContent = data.message || '';
              }
            } catch (e) {
              // Skip partial JSON chunks
            }
            lastEvent = '';
          }
        }
      }

      removeTyping(typingEl);

      if (fullContent) {
        appendMessage('assistant', fullContent);
        setStatus('●', '就绪', 'var(--green)');
      }

    } catch (e) {
      removeTyping(typingEl);
      appendMessage('assistant', '❌ 连接失败: ' + e.message);
      setStatus('●', '连接错误 — 请重试', 'var(--red)');
    } finally {
      isProcessing = false;
      sendBtn.disabled = false;
      document.getElementById('userInput').focus();
    }
  };

  /* ═══════════════════════════════════════════════════════
     SSE Event Handler
     ═══════════════════════════════════════════════════════ */
  function handleSSEEvent(evt, data) {
    switch (evt) {
      case 'session':
        sessionId = data.session_id;
        break;
      case 'thinking':
        setStatusRight(data.content || '分析中...');
        break;
      case 'clarify':
        clarifyRound += 1;
        setStatus('◉', '追问中 — 完整度 ' + Math.round((data.progress || 0) * 100) + '%', 'var(--amber)');
        break;
      case 'execute':
        clarifyRound = 0;
        dimensions = {};
        setStatusRight('执行完成');
        break;
      case 'done':
        setStatusRight('');
        break;
      case 'error':
        appendMessage('assistant', '⚠ ' + (data.detail || '未知错误'));
        setStatus('●', '出错了', 'var(--red)');
        break;
    }
  }

  /* ═══════════════════════════════════════════════════════
     New Session
     ═══════════════════════════════════════════════════════ */
  window.newSession = function () {
    sessionId = null;
    clarifyRound = 0;
    dimensions = {};
    document.getElementById('chatWindow').innerHTML =
      '<div class="empty-state" id="emptyState">' +
      '<div class="empty-icon">🔄</div>' +
      '<p>新会话已开始</p>' +
      '<p class="sub">描述你的需求，AI 会通过追问帮你补全信息</p>' +
      '</div>';
    setStatus('●', '新会话', 'var(--green)');
    setStatusRight('');
    document.getElementById('userInput').focus();
  };

  /* ═══════════════════════════════════════════════════════
     Keyboard
     ═══════════════════════════════════════════════════════ */
  window.handleKey = function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      window.sendMessage();
    }
  };

  /* ═══════════════════════════════════════════════════════
     DOM Helpers
     ═══════════════════════════════════════════════════════ */
  function appendMessage(role, content) {
    const win = document.getElementById('chatWindow');
    const div = document.createElement('div');
    div.className = 'msg msg-' + role;

    const labelText = role === 'user' ? '你' : 'MakeItSmooth';
    div.innerHTML =
      '<div class="msg-label">' + labelText + '</div>' +
      '<div class="msg-content">' + (role === 'user' ? escapeHtml(content) : renderMarkdown(content)) + '</div>';
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
    return div;
  }

  function appendTyping() {
    const win = document.getElementById('chatWindow');
    const div = document.createElement('div');
    div.className = 'typing';
    div.innerHTML = '思考中<div class="typing-dots"><span></span><span></span><span></span></div>';
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
    return div;
  }

  function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  function setStatus(icon, text, color) {
    const iconEl = document.getElementById('statusIcon');
    const textEl = document.getElementById('statusText');
    if (iconEl) { iconEl.textContent = icon; iconEl.style.color = color || 'var(--fg-muted)'; }
    if (textEl) textEl.textContent = text;
  }

  function setStatusRight(text) {
    const el = document.getElementById('statusRight');
    if (el) el.textContent = text;
  }

  function escapeHtml(s) {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  /* ═══════════════════════════════════════════════════════
     Markdown Rendering (safe, no XSS)
     ═══════════════════════════════════════════════════════ */
  function renderMarkdown(text) {
    if (!text) return '';

    var html = text;

    // Fenced code blocks (with optional language)
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function (_, lang, code) {
      return '<pre><code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code></pre>';
    });

    // Inline code
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic
    html = html.replace(/\B\*(.+?)\*\B/g, '<em>$1</em>');

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Horizontal rule
    html = html.replace(/^---+$/gm, '<hr>');

    // Blockquote
    html = html.replace(/^&gt; ?(.+)$/gm, '<blockquote>$1</blockquote>');

    // Unordered list
    html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Ordered list
    html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
    // Clean up nested uls created by ordered list
    html = html.replace(/<\/ul>\s*<ul>/g, '\n');

    // Paragraphs — wrap text between block elements
    // Convert double newlines to paragraph breaks
    html = '<p>' + html.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>') + '</p>';
    // Clean up paragraphs wrapping block elements
    html = html.replace(/<p><(h[123]|ul|ol|pre|blockquote|hr)/g, '<$1');
    html = html.replace(/<\/(h[123]|ul|ol|pre|blockquote)>(\s*)<\/p>/g, '</$1>');
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>\s*<\/p>/g, '');
    html = html.replace(/<br>\s*<\/(h[123]|ul|ol|pre|blockquote)>/g, '</$1>');
    html = html.replace(/<(h[123]|ul|ol|pre|blockquote)>([\s\S]*?)<\/\1>/g, function (match, tag, inner) {
      return '<' + tag + '>' + inner.replace(/<\/?p>/g, '') + '</' + tag + '>';
    });

    return html;
  }

})();
