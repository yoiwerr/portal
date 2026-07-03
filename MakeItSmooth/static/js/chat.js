// MakeItSmooth Chat Client
let currentModule = null;
let sessionId = null;
let clarifyRound = 0;
let dimensions = {};
let isProcessing = false;

// ── Module Selection ──
function selectModule(name, el) {
  currentModule = name;
  document.querySelectorAll('.card').forEach(c => c.classList.remove('active'));
  el.classList.add('active');

  const labels = { prompt_refiner: '提示词工程', work_arranger: '工作安排交流', info_retention: '信息留存' };
  document.getElementById('selectedHint').textContent = '已选择：' + labels[name] + ' — 在下方输入你的需求';
  document.getElementById('bgWrapper').style.display = 'block';
  document.getElementById('inputArea').style.display = 'block';
  document.getElementById('userInput').focus();
  setStatus('●', '就绪 — ' + labels[name], 'var(--green)');
}

// ── Send Message ──
async function sendMessage() {
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

  // Add user message
  appendMessage('user', msg);
  setStatus('◉', '处理中...', 'var(--amber)');

  // Add typing indicator
  const typingEl = appendTyping();

  const bgText = document.getElementById('bgInput').value.trim();
  const extraCtx = '';

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
        extra_context: extraCtx,
      }),
    });

    if (!resp.ok) {
      removeTyping(typingEl);
      appendMessage('assistant', '请求失败 HTTP ' + resp.status + ': ' + resp.statusText);
      setStatus('◉', '错误', 'var(--red)');
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullContent = '';
    let eventType = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventType = line.slice(6).trim();
          continue;
        }
        if (line.startsWith('data:') && eventType) {
          try {
            const data = JSON.parse(line.slice(5).trim());
            handleSSEEvent(eventType, data);
            if (eventType === 'clarify' || eventType === 'execute') {
              fullContent = data.message || '';
            }
          } catch (e) {
            // ignore parse errors on partial chunks
          }
          eventType = '';
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
    appendMessage('assistant', '连接失败: ' + e.message);
    setStatus('◉', '连接错误', 'var(--red)');
  } finally {
    isProcessing = false;
    sendBtn.disabled = false;
    document.getElementById('userInput').focus();
  }
}

function handleSSEEvent(evt, data) {
  switch (evt) {
    case 'session':
      sessionId = data.session_id;
      break;
    case 'clarify':
      clarifyRound += 1;
      setStatus('◉', '追问中 — 信息完整度: ' + Math.round((data.progress || 0) * 100) + '%', 'var(--amber)');
      break;
    case 'execute':
      clarifyRound = 0;
      dimensions = {};
      setStatus('●', '执行完成', 'var(--green)');
      break;
    case 'done':
      setStatus('●', '就绪', 'var(--green)');
      break;
    case 'error':
      appendMessage('assistant', '⚠ ' + (data.detail || '未知错误'));
      setStatus('◉', '错误', 'var(--red)');
      break;
  }
}

// ── New Session ──
function newSession() {
  sessionId = null;
  clarifyRound = 0;
  dimensions = {};
  document.getElementById('chatWindow').innerHTML =
    '<div class="empty-state" id="emptyState"><p>新会话已开始</p><p class="sub">描述你的需求，AI 会通过追问帮你补全信息</p></div>';
  setStatus('●', '新会话', 'var(--green)');
  document.getElementById('userInput').focus();
}

// ── Keyboard shortcut ──
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ── DOM Helpers ──
function appendMessage(role, content) {
  const win = document.getElementById('chatWindow');
  const div = document.createElement('div');
  div.className = 'msg msg-' + role;

  const labelText = role === 'user' ? '你' : 'MakeItSmooth';
  div.innerHTML =
    '<div class="msg-label">' + labelText + '</div>' +
    '<div class="msg-content">' + (role === 'user' ? escapeHtml(content) : simpleMarkdown(content)) + '</div>';
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
  return div;
}

function appendTyping() {
  const win = document.getElementById('chatWindow');
  const div = document.createElement('div');
  div.className = 'typing';
  div.innerHTML = '思考中<span>.</span><span>.</span><span>.</span>';
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

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Simple markdown → HTML
function simpleMarkdown(s) {
  if (!s) return '';
  return s
    // code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // hr
    .replace(/^---$/gm, '<hr>')
    // simple tables (pipe format)
    .replace(/^\|(.+)\|$/gm, (match) => {
      const cells = match.split('|').filter(c => c.trim());
      if (match.includes('---')) return '<tr>' + cells.map(() => '<th></th>').join('') + '</tr>';
      const tag = match.includes('---') ? 'th' : 'td';
      return '<tr>' + cells.map(c => '<' + tag + '>' + c.trim() + '</' + tag + '>').join('') + '</tr>';
    })
    // line breaks
    .replace(/\n/g, '<br>');
}
