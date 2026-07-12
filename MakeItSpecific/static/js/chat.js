/**
 * MakeItSpecific — 纯对话 Agent
 * SSE token 流式 · module=auto 自动路由 · 反馈收集
 */
(function () {
  'use strict';

  let sessionId = null;
  let clarifyRound = 0;
  let dimensions = {};
  let isProcessing = false;

  /* ═══════════════════════════════════════════════════════
     Init
     ═══════════════════════════════════════════════════════ */
  function init() {
    document.getElementById('userInput').focus();
    document.getElementById('chatWindow').addEventListener('click', function(e) {
      if (e.target === this) document.getElementById('userInput').focus();
    });
  }

  /* ═══════════════════════════════════════════════════════
     Send Message
     ═══════════════════════════════════════════════════════ */
  window.sendMessage = async function () {
    var input = document.getElementById('userInput');
    var msg = input.value.trim();
    if (!msg || isProcessing) return;

    isProcessing = true;
    var sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    // Hide landing
    var landing = document.getElementById('landing');
    if (landing) landing.style.display = 'none';

    // User bubble
    appendMessage('user', msg);
    setStatus('思考中…');

    // Typing
    var typingEl = appendTyping();

    try {
      var resp = await fetch('api/chat/stream?v=2', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: msg,
          module: 'auto',
          session_id: sessionId,
          background: '',
          clarify_round: clarifyRound,
          dimensions: dimensions,
          extra_context: '',
        }),
      });

      if (!resp.ok) {
        removeTyping(typingEl);
        var errText = await resp.text().catch(function() { return resp.statusText; });
        appendMessage('assistant', '请求失败 HTTP ' + resp.status + ': ' + errText);
        setStatus('请求失败');
        return;
      }

      // SSE reader
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      var lastEvent = '';
      var streamBubble = null;
      var streamContent = '';
      var toolCalls = [];

      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        var value = chunk.value;

        buffer += decoder.decode(value, { stream: true });
        var lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.startsWith('event:')) {
            lastEvent = line.slice(6).trim();
            continue;
          }
          if (line.startsWith('data:') && lastEvent) {
            try {
              var data = JSON.parse(line.slice(5).trim());
              handleSSEEvent(lastEvent, data);
            } catch (e) {
              // skip partial
            }
            lastEvent = '';
          }
        }
      }

      removeTyping(typingEl);

      if (streamBubble && streamContent) {
        finalizeBubble(streamBubble, streamContent);
      }

      setStatus('就绪');

    } catch (e) {
      removeTyping(typingEl);
      appendMessage('assistant', '连接失败: ' + e.message);
      setStatus('连接错误');
    } finally {
      isProcessing = false;
      sendBtn.disabled = false;
      document.getElementById('userInput').focus();
    }

    /* ── SSE handler ── */
    function handleSSEEvent(evt, data) {
      switch (evt) {
        case 'session':
          sessionId = data.session_id;
          setMeta(data.model || '');
          break;

        case 'token':
          streamContent += data.content;
          if (!streamBubble) {
            removeTyping(typingEl);
            streamBubble = appendStreamBubble();
          }
          updateStreamBubble(streamBubble, streamContent, toolCalls);
          break;

        case 'tool_start':
          toolCalls.push({ name: data.tool_name, status: 'running' });
          setStatus('调用工具: ' + data.tool_name);
          if (streamBubble) updateStreamBubble(streamBubble, streamContent, toolCalls);
          break;

        case 'tool_end':
          for (var j = toolCalls.length - 1; j >= 0; j--) {
            if (toolCalls[j].name === data.tool_name && toolCalls[j].status === 'running') {
              toolCalls[j].status = 'done';
              break;
            }
          }
          setStatus('就绪');
          if (streamBubble) updateStreamBubble(streamBubble, streamContent, toolCalls);
          break;

        case 'clarify':
          clarifyRound += 1;
          setStatus('追问中 — ' + Math.round((data.progress || 0) * 100) + '%');
          if (!streamContent) {
            removeTyping(typingEl);
            appendMessage('assistant', data.message || '');
          }
          break;

        case 'execute':
          clarifyRound = 0;
          dimensions = {};
          if (data.intent && data.intent.label) {
            setMeta(data.intent.label);
          }
          break;

        case 'done':
          setStatus('就绪');
          break;

        case 'error':
          appendMessage('assistant', data.detail || '未知错误');
          setStatus('出错');
          break;
      }
    }
  };

  /* ═══════════════════════════════════════════════════════
     New Session
     ═══════════════════════════════════════════════════════ */
  window.newSession = function () {
    sessionId = null;
    clarifyRound = 0;
    dimensions = {};
    var win = document.getElementById('chatWindow');
    win.innerHTML =
      '<div class="landing" id="landing">' +
      '<h1>MakeItSpecific</h1>' +
      '<p class="subtitle">AI 工作流增强助手 — 直接对话，无需选模块</p>' +
      '<div class="feature-cards">' +
      '<div class="feature-card">' +
      '<div class="feature-num">01</div>' +
      '<h3>提示词工程</h3>' +
      '<p>大白话进来，追问补全后输出 2-3 个优化版提示词，匹配最佳模型。</p>' +
      '<div class="feature-example"><span>试试看：</span>' +
      '<code>帮我写一个生成产品文案的提示词，面向年轻人的潮牌服饰</code></div>' +
      '</div>' +
      '<div class="feature-card">' +
      '<div class="feature-num">02</div>' +
      '<h3>工作安排</h3>' +
      '<p>模糊想法 → 追问目的/范围/时间 → 结构化工作计划 + 任务拆解 + 时间线。</p>' +
      '<div class="feature-example"><span>试试看：</span>' +
      '<code>我想用 React 写一个管理后台，大概 50 人使用，三个月搞定</code></div>' +
      '</div>' +
      '<div class="feature-card">' +
      '<div class="feature-num">03</div>' +
      '<h3>信息留存</h3>' +
      '<p>对话 + 文件 → 追问格式/用途 → 结构化 Markdown 文档，下次可加载继续。</p>' +
      '<div class="feature-example"><span>试试看：</span>' +
      '<code>帮我把这次讨论的技术选型决策整理成文档，方便下次回顾</code></div>' +
      '</div>' +
      '</div>' +
      '</div>';
    setStatus('新会话');
    setMeta('');
    document.getElementById('userInput').focus();
  };

  /* ═══════════════════════════════════════════════════════
     Feedback
     ═══════════════════════════════════════════════════════ */
  window.sendFeedback = function (msgEl, rating) {
    var btns = msgEl.querySelectorAll('.feedback-btn');
    for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
    var activeBtn = msgEl.querySelector('.feedback-btn[data-rating="' + rating + '"]');
    if (activeBtn) activeBtn.classList.add('active');

    if (rating === 'negative') {
      var existing = msgEl.querySelector('.feedback-tag');
      if (!existing) {
        var tag = document.createElement('span');
        tag.className = 'feedback-tag';
        tag.textContent = 'Badcase';
        tag.onclick = function() { window.sendFeedback(msgEl, 'negative'); };
        var fbRow = msgEl.querySelector('.feedback-row');
        if (fbRow) fbRow.appendChild(tag);
      }
    }

    fetch('api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId || '',
        message_id: 0,
        rating: rating,
        skill: '',
        comment: '',
      }),
    }).catch(function() {});
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

  window.autoResize = function (el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  };

  /* ═══════════════════════════════════════════════════════
     Status / Meta
     ═══════════════════════════════════════════════════════ */
  function setStatus(text) {
    var el = document.getElementById('statusLine');
    if (el) el.textContent = text;
  }

  function setMeta(text) {
    var el = document.getElementById('metaLine');
    if (el) el.textContent = text || '';
  }

  /* ═══════════════════════════════════════════════════════
     DOM — Messages
     ═══════════════════════════════════════════════════════ */
  function appendMessage(role, content) {
    var win = document.getElementById('chatWindow');
    var div = document.createElement('div');
    div.className = 'msg msg-' + role;

    var label = role === 'user' ? '你' : 'MakeItSpecific';
    var body = role === 'user' ? escapeHtml(content) : renderMd(content);

    div.innerHTML =
      '<div class="msg-label">' + label + '</div>' +
      '<div class="msg-content">' + body + '</div>';

    if (role === 'assistant') {
      var fb = document.createElement('div');
      fb.className = 'feedback-row';
      fb.innerHTML =
        '<button class="feedback-btn" data-rating="positive" title="有用">👍</button>' +
        '<button class="feedback-btn" data-rating="negative" title="没用">👎</button>';
      fb.children[0].onclick = function() { window.sendFeedback(div, 'positive'); };
      fb.children[1].onclick = function() { window.sendFeedback(div, 'negative'); };
      div.appendChild(fb);
    }

    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
    return div;
  }

  function appendStreamBubble() {
    var win = document.getElementById('chatWindow');
    var div = document.createElement('div');
    div.className = 'msg msg-assistant streaming';
    div.innerHTML =
      '<div class="msg-label">MakeItSpecific</div>' +
      '<div class="msg-content"><span class="cursor-blink">▌</span></div>';
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
    return div;
  }

  function updateStreamBubble(el, content, toolCalls) {
    var contentEl = el.querySelector('.msg-content');
    if (!contentEl) return;

    var html = renderMd(content);

    if (toolCalls && toolCalls.length > 0) {
      html += '<div class="tool-indicators">';
      for (var i = 0; i < toolCalls.length; i++) {
        var tc = toolCalls[i];
        html += '<span class="tool-chip' + (tc.status === 'running' ? ' running' : '') + '">' +
          (tc.status === 'running' ? '· ' : '') + escapeHtml(tc.name) + '</span>';
      }
      html += '</div>';
    }

    html += '<span class="cursor-blink">▌</span>';
    contentEl.innerHTML = html;
    el.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }

  function finalizeBubble(el, content) {
    el.classList.remove('streaming');
    var contentEl = el.querySelector('.msg-content');
    if (contentEl) {
      contentEl.innerHTML = renderMd(content);
      var cursor = contentEl.querySelector('.cursor-blink');
      if (cursor) cursor.remove();
    }
    // Feedback
    var fb = document.createElement('div');
    fb.className = 'feedback-row';
    fb.innerHTML =
      '<button class="feedback-btn" data-rating="positive" title="有用">👍</button>' +
      '<button class="feedback-btn" data-rating="negative" title="没用">👎</button>';
    fb.children[0].onclick = function() { window.sendFeedback(el, 'positive'); };
    fb.children[1].onclick = function() { window.sendFeedback(el, 'negative'); };
    el.appendChild(fb);
    el.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }

  function appendTyping() {
    var win = document.getElementById('chatWindow');
    var div = document.createElement('div');
    div.className = 'typing';
    div.innerHTML = '思考中<div class="typing-dots"><span></span><span></span><span></span></div>';
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
    return div;
  }

  function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
  }

  /* ═══════════════════════════════════════════════════════
     Helpers
     ═══════════════════════════════════════════════════════ */
  function escapeHtml(s) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  function renderMd(text) {
    if (!text) return '';

    var html = text;

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
      return '<pre><code>' + code.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</code></pre>';
    });

    // Inline code
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // Bold / italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\B\*(.+?)\*\B/g, '<em>$1</em>');

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // HR
    html = html.replace(/^---+$/gm, '<hr>');

    // Blockquote
    html = html.replace(/^&gt; ?(.+)$/gm, '<blockquote>$1</blockquote>');

    // Lists
    html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

    // Paragraphs
    html = '<p>' + html.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>') + '</p>';
    html = html.replace(/<p><(h[123]|ul|ol|pre|blockquote|hr)/g, '<$1');
    html = html.replace(/<\/(h[123]|ul|ol|pre|blockquote)>(\s*)<\/p>/g, '</$1>');
    html = html.replace(/<p><\/p>/g, '');
    html = html.replace(/<p>\s*<\/p>/g, '');
    html = html.replace(/<br>\s*<\/(h[123]|ul|ol|pre|blockquote)>/g, '</$1>');

    return html;
  }

  init();
})();
