// Alfred Admin — dashboard / model management / user management

const API_BASE = '/alfred/api/v1';
const CHAT_URL = '/alfred/';
const LOGIN_URL = '/alfred/auth/';

function getToken() { return localStorage.getItem('alfred_token'); }
function authHeaders() {
  return { 'Authorization': 'Bearer ' + getToken(), 'Content-Type': 'application/json' };
}

// ── Auth guard ──
async function checkAuth() {
  const token = getToken();
  if (!token) { window.location.href = LOGIN_URL; return null; }
  try {
    const res = await fetch(API_BASE + '/auth/me', { headers: { 'Authorization': 'Bearer ' + token } });
    if (!res.ok) throw new Error('unauthorized');
    const me = await res.json();
    document.getElementById('admin-user').textContent = me.username + (me.role === 'admin' ? ' (admin)' : '');
    if (me.role !== 'admin') { window.location.href = CHAT_URL; return null; }
    return me;
  } catch (_) {
    // Try refresh
    const rt = localStorage.getItem('alfred_refresh');
    if (rt) {
      try {
        const r = await fetch(API_BASE + '/auth/refresh', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (r.ok) {
          const d = await r.json();
          localStorage.setItem('alfred_token', d.access_token);
          localStorage.setItem('alfred_refresh', d.refresh_token);
          return checkAuth();
        }
      } catch (_) {}
    }
    window.location.href = LOGIN_URL;
    return null;
  }
}

// ── Navigation ──
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    item.classList.add('active');
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById('panel-' + item.dataset.panel).classList.add('active');
    if (item.dataset.panel === 'dashboard') loadDashboard();
    if (item.dataset.panel === 'models') loadModels();
    if (item.dataset.panel === 'users') loadUsers();
  });
});

// ── Dashboard ──
async function loadDashboard() {
  try {
    const res = await fetch(API_BASE + '/admin/stats/tokens', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const s = data.summary;
    document.getElementById('stats-summary').innerHTML = [
      { label: '总调用', value: s.total_calls },
      { label: '总 Token', value: (s.total_tokens / 1000).toFixed(1) + 'K' },
      { label: '输入 Token', value: (s.input_tokens / 1000).toFixed(1) + 'K' },
      { label: '输出 Token', value: (s.output_tokens / 1000).toFixed(1) + 'K' },
      { label: '成功率', value: s.success_rate.toFixed(1) + '%' },
      { label: '平均延迟', value: (s.avg_duration_ms / 1000).toFixed(2) + 's' },
    ].map(c => `<div class="stat-card"><div class="label">${c.label}</div><div class="value">${c.value}</div></div>`).join('');

    if (data.by_model?.length) {
      document.getElementById('stats-by-model').innerHTML =
        '<table><thead><tr><th>模型</th><th>调用次数</th><th>总 Token</th><th>输入</th><th>输出</th><th>平均延迟</th></tr></thead><tbody>' +
        data.by_model.map(m => `<tr><td>${m.model_name}</td><td>${m.total_calls}</td><td>${m.total_tokens}</td><td>${m.input_tokens}</td><td>${m.output_tokens}</td><td>${(m.avg_duration_ms/1000).toFixed(2)}s</td></tr>`).join('') +
        '</tbody></table>';
    }

    if (data.recent?.length) {
      document.getElementById('stats-recent').innerHTML =
        '<table><thead><tr><th>时间</th><th>模型</th><th>Token</th><th>延迟</th><th>状态</th></tr></thead><tbody>' +
        data.recent.slice(0, 20).map(r => `<tr><td>${new Date(r.created_at).toLocaleString()}</td><td>${r.model_name}</td><td>${r.total_tokens}</td><td>${(r.duration_ms/1000).toFixed(2)}s</td><td><span class="badge ${r.success ? 'badge-success' : 'badge-danger'}">${r.success ? 'OK' : 'FAIL'}</span></td></tr>`).join('') +
        '</tbody></table>';
    }
  } catch (e) { console.error('loadDashboard', e); }
}

// ── Models ──
async function loadModels() {
  try {
    const res = await fetch(API_BASE + '/admin/models', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const models = data.models || [];
    document.getElementById('models-list').innerHTML =
      '<table><thead><tr><th>Alias</th><th>Provider</th><th>Model</th><th>Key Env Var</th><th>默认</th><th>启用</th><th>操作</th></tr></thead><tbody>' +
      models.map(m => `<tr>
        <td>${m.alias}</td><td>${m.provider}</td><td>${m.model_name}</td><td><code>${m.api_key_env_var}</code></td>
        <td>${m.is_default ? '<span class="badge badge-info">默认</span>' : ''}</td>
        <td><span class="badge ${m.is_enabled ? 'badge-success' : 'badge-warn'}">${m.is_enabled ? '启用' : '禁用'}</span></td>
        <td>
          <button class="btn-sm" onclick="editModel('${m.id}')">编辑</button>
          ${!m.is_default ? `<button class="btn-danger" onclick="deleteModel('${m.id}')">删除</button>` : ''}
          <button class="btn-sm" onclick="toggleModel('${m.id}', ${!m.is_enabled})">${m.is_enabled ? '禁用' : '启用'}</button>
          ${!m.is_default ? `<button class="btn-sm" onclick="setDefault('${m.id}')">设默认</button>` : ''}
        </td>
      </tr>`).join('') +
      '</tbody></table>';
  } catch (e) { console.error('loadModels', e); }
}

document.getElementById('btn-add-model').addEventListener('click', () => {
  document.getElementById('modal-title').textContent = '添加模型';
  document.getElementById('model-id').value = '';
  ['m-alias','m-model','m-url','m-keyenv'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('m-provider').value = 'deepseek';
  document.getElementById('model-modal').classList.add('open');
});

async function editModel(id) {
  try {
    const res = await fetch(API_BASE + '/admin/models', { headers: authHeaders() });
    const data = await res.json();
    const m = data.models.find(x => x.id === id);
    if (!m) return;
    document.getElementById('modal-title').textContent = '编辑模型';
    document.getElementById('model-id').value = m.id;
    document.getElementById('m-alias').value = m.alias;
    document.getElementById('m-provider').value = m.provider;
    document.getElementById('m-model').value = m.model_name;
    document.getElementById('m-url').value = m.base_url;
    document.getElementById('m-keyenv').value = m.api_key_env_var;
    document.getElementById('model-modal').classList.add('open');
  } catch (e) { console.error(e); }
}

async function deleteModel(id) {
  if (!confirm('确定删除？')) return;
  await fetch(API_BASE + '/admin/models/' + id, { method: 'DELETE', headers: authHeaders() });
  loadModels();
}

async function toggleModel(id, enable) {
  await fetch(API_BASE + '/admin/models/' + id + '/toggle', {
    method: 'PUT', headers: authHeaders(),
    body: JSON.stringify({ enabled: enable }),
  });
  loadModels();
}

async function setDefault(id) {
  await fetch(API_BASE + '/admin/models/' + id + '/default', { method: 'PUT', headers: authHeaders() });
  loadModels();
}

document.getElementById('model-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = document.getElementById('model-id').value;
  const body = {
    alias: document.getElementById('m-alias').value,
    provider: document.getElementById('m-provider').value,
    model_name: document.getElementById('m-model').value,
    base_url: document.getElementById('m-url').value,
    api_key_env_var: document.getElementById('m-keyenv').value,
  };
  const method = id ? 'PUT' : 'POST';
  const url = id ? API_BASE + '/admin/models/' + id : API_BASE + '/admin/models';
  await fetch(url, { method, headers: authHeaders(), body: JSON.stringify(body) });
  document.getElementById('model-modal').classList.remove('open');
  loadModels();
});

document.getElementById('btn-modal-cancel').addEventListener('click', () => {
  document.getElementById('model-modal').classList.remove('open');
});

// ── Users ──
async function loadUsers() {
  document.getElementById('users-list').innerHTML = '<p style="color:#666">用户管理功能开发中。当前仅支持 admin 账户。</p>';
}

// ── Init ──
checkAuth().then(() => loadDashboard());
