// dude Admin: server-authorized account directory and recorded usage.
const API_BASE = '/dude/api/v1';
const CHAT_URL = '/dude/';
const LOGIN_URL = '/dude/auth/';
const el = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
const number = value => Number(value || 0).toLocaleString('zh-CN');
const date = value => value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '暂无记录';
function getToken() { return localStorage.getItem('alfred_token'); }
function authHeaders() { return {Authorization: 'Bearer ' + getToken(), 'Content-Type': 'application/json'}; }
let authorized = false;
let refreshPending = null;
let userPage = 1;
let userRequest = 0;
let cachedModels = [];
let modalTrigger = null;

function error(message, id = 'page-error') {
  el(id).textContent = message;
  el(id).hidden = !message;
}
function clearAuthAndRedirect() {
  authorized = false;
  el('admin-content').hidden = true;
  ['alfred_token', 'alfred_refresh', 'alfred_user'].forEach(key => localStorage.removeItem(key));
  window.location.href = LOGIN_URL;
  return null;
}
async function refreshToken() {
  if (refreshPending) return refreshPending;
  refreshPending = (async () => {
    const rt = localStorage.getItem('alfred_refresh');
    if (!rt) return false;
    const res = await fetch(API_BASE + '/auth/refresh', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh_token:rt})});
    if (res.status === 401) return false;
    if (!res.ok) throw Error('登录服务暂时不可用，请稍后重试');
    const data = await res.json();
    if (![data.access_token, data.refresh_token].every(token => typeof token === 'string' && token.trim())) throw Error('登录服务返回异常');
    localStorage.setItem('alfred_token', data.access_token);
    localStorage.setItem('alfred_refresh', data.refresh_token);
    return true;
  })();
  try { return await refreshPending; } finally { refreshPending = null; }
}
async function checkAuth(hasRefreshed = false) {
  if (!getToken() && !localStorage.getItem('alfred_refresh')) return clearAuthAndRedirect();
  try {
    if (getToken()) {
      const res = await fetch(API_BASE + '/auth/me', {headers:authHeaders()});
      if (res.ok) {
        const me = await res.json();
        el('admin-user').textContent = me.username + (me.role === 'admin' ? ' · 管理员' : '');
        if (me.role !== 'admin') { window.location.href = CHAT_URL; return null; }
        authorized = true;
        el('admin-content').hidden = false;
        return me;
      }
      if (res.status !== 401) throw Error('auth_service_unavailable');
    }
    if (!hasRefreshed && await refreshToken()) return checkAuth(true);
    return clearAuthAndRedirect();
  } catch (_) {
    el('admin-user').textContent = '登录服务暂时不可用，请稍后刷新重试';
    return null;
  }
}
async function adminFetch(path, options = {}) {
  if (!authorized) throw Error('请先使用管理员账号登录');
  let res = await fetch(API_BASE + '/admin' + path, {...options, headers:authHeaders()});
  if (res.status === 401) {
    if (await refreshToken()) res = await fetch(API_BASE + '/admin' + path, {...options, headers:authHeaders()});
    if (res.status === 401) { clearAuthAndRedirect(); throw Error('登录已过期'); }
  }
  if (res.status === 403) {
    authorized = false;
    el('admin-content').hidden = true;
    window.location.href = CHAT_URL;
    throw Error('此功能仅限管理员使用');
  }
  if (res.status === 204) return {};
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Error(res.status >= 500 ? '服务暂时不可用，请重试' : data?.error?.message || '操作失败，请重试');
  return data;
}

document.querySelectorAll('.nav-item').forEach(item => item.addEventListener('click', event => {
  event.preventDefault();
  if (!authorized) return;
  document.querySelectorAll('.nav-item').forEach(node => { node.classList.remove('active'); node.removeAttribute('aria-current'); });
  item.classList.add('active'); item.setAttribute('aria-current', 'page');
  document.querySelectorAll('.panel').forEach(node => node.classList.remove('active'));
  el('panel-' + item.dataset.panel).classList.add('active');
  error('');
  if (item.dataset.panel === 'dashboard') loadDashboard();
  if (item.dataset.panel === 'users') loadUsers();
  if (item.dataset.panel === 'models') loadModels();
}));

async function loadDashboard() {
  el('refresh-dashboard').disabled = true;
  el('stats-summary').textContent = '正在读取用量…';
  error('');
  try {
    const data = await adminFetch('/overview');
    const cards = [
      ['用户总数', data.total_users, '启用 ' + number(data.active_users) + ' 个账号'],
      ['管理员', data.admin_users, '其余为普通用户'],
      ['模型调用 · 近 30 天', data.calls, '一次对话可产生多次调用'],
      ['Token · 近 30 天', data.total_tokens, '输入 ' + number(data.input_tokens) + ' / 输出 ' + number(data.output_tokens)],
    ];
    el('stats-summary').innerHTML = cards.map(([label, value, sub]) => '<div class="stat-card"><div class="label">' + label + '</div><div class="value">' + number(value) + '</div><div class="sub">' + sub + '</div></div>').join('');
    el('overview-updated').textContent = '统计区间：' + date(data.period_start) + ' — ' + date(data.as_of);
  } catch (exc) { el('stats-summary').textContent = '暂时无法读取用量'; error(exc.message); }
  finally { el('refresh-dashboard').disabled = false; }
}
el('refresh-dashboard').addEventListener('click', loadDashboard);

function renderUsers(users) {
  if (!users.length) return '<p class="empty-state">没有符合条件的用户。</p>';
  const headers = ['用户 / ID','身份','状态','注册时间','模型调用','输入 Token','输出 Token','总 Token','最近调用'];
  return '<table class="users-table"><thead><tr>' + headers.map(label => '<th scope="col">' + label + '</th>').join('') + '</tr></thead><tbody>' + users.map(user => {
    const cells = [
      '<span class="user-name">' + escapeHtml(user.username) + '</span><span class="user-id">' + escapeHtml(user.id) + '</span>',
      '<span class="badge ' + (user.role === 'admin' ? 'badge-admin' : '') + '">' + (user.role === 'admin' ? '管理员' : '普通用户') + '</span>',
      '<span class="badge ' + (user.is_active ? '' : 'badge-disabled') + '">' + (user.is_active ? '启用' : '停用') + '</span>',
      escapeHtml(date(user.created_at)), number(user.calls), number(user.input_tokens), number(user.output_tokens), number(user.total_tokens), escapeHtml(date(user.last_used_at)),
    ];
    return '<tr>' + cells.map((value, index) => '<td data-label="' + headers[index] + '">' + value + '</td>').join('') + '</tr>';
  }).join('') + '</tbody></table>';
}
async function loadUsers(page = userPage) {
  const request = ++userRequest;
  const query = '?page=' + page + '&page_size=20&q=' + encodeURIComponent(el('user-search').value.trim()) + '&role=' + encodeURIComponent(el('user-role').value);
  el('users-list').textContent = '正在读取用户…';
  el('users-prev').disabled = el('users-next').disabled = true;
  error('');
  try {
    const data = await adminFetch('/users' + query);
    if (request !== userRequest) return;
    userPage = data.page;
    el('users-list').innerHTML = renderUsers(data.users || []);
    el('users-count').textContent = '共 ' + number(data.total) + ' 个用户';
    el('users-page').textContent = data.total ? data.page + ' / ' + Math.ceil(data.total / data.page_size) : '0 / 0';
    el('users-prev').disabled = data.page <= 1;
    el('users-next').disabled = data.page * data.page_size >= data.total;
  } catch (exc) {
    if (request !== userRequest) return;
    el('users-list').textContent = '用户信息加载失败，请重新查询。';
    el('users-count').textContent = el('users-page').textContent = '';
    error(exc.message);
  }
}
el('users-filter').addEventListener('submit', event => { event.preventDefault(); loadUsers(1); });
el('users-prev').addEventListener('click', () => loadUsers(userPage - 1));
el('users-next').addEventListener('click', () => loadUsers(userPage + 1));

async function loadModels() {
  error('');
  try {
    const data = await adminFetch('/models');
    cachedModels = data.models || [];
    el('models-list').innerHTML = cachedModels.length ? '<table><thead><tr><th>名称</th><th>服务商 / 模型</th><th>密钥变量名</th><th>状态</th><th>操作</th></tr></thead><tbody>' + cachedModels.map(model => {
      const button = (action, text, style = '') => '<button type="button" class="btn-sm ' + style + '" data-action="' + action + '" data-id="' + escapeHtml(model.id) + '">' + text + '</button>';
      return '<tr><td>' + escapeHtml(model.alias) + '</td><td>' + escapeHtml(model.provider) + '<br>' + escapeHtml(model.model_name) + '</td><td>' + escapeHtml(model.api_key_env_var) + '</td><td>' + (model.is_enabled ? '启用' : '禁用') + (model.is_default ? ' · 默认' : '') + '</td><td><div class="table-actions">' + button('edit','编辑') + button('toggle', model.is_enabled ? '禁用' : '启用') + (!model.is_default ? button('default','设为默认') + button('delete','删除','btn-danger') : '') + '</div></td></tr>';
    }).join('') + '</tbody></table>' : '<p class="empty-state">暂无模型配置。</p>';
  } catch (exc) { el('models-list').textContent = '模型配置加载失败'; error(exc.message); }
}
function openModel(model = {}) {
  modalTrigger = document.activeElement;
  el('modal-title').textContent = model.id ? '编辑模型' : '添加模型';
  for (const [id, value] of Object.entries({'model-id':model.id,'m-alias':model.alias,'m-provider':model.provider || 'deepseek','m-model':model.model_name,'m-url':model.base_url,'m-keyenv':model.api_key_env_var})) el(id).value = value || '';
  error('', 'model-error');
  el('model-modal').hidden = false;
  document.querySelector('.admin-layout').inert = true;
  el('m-alias').focus();
}
function closeModel() {
  el('model-modal').hidden = true;
  document.querySelector('.admin-layout').inert = false;
  if (modalTrigger?.focus) modalTrigger.focus();
}
el('btn-add-model').addEventListener('click', () => openModel());
el('btn-modal-cancel').addEventListener('click', closeModel);
el('model-modal').addEventListener('keydown', event => {
  if (event.key === 'Escape' && !el('model-save').disabled) closeModel();
  if (event.key !== 'Tab') return;
  const items = Array.from(el('model-modal').querySelectorAll('input:not([type=hidden]),select,button')).filter(node => !node.disabled);
  if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
  else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
});
el('models-list').addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const model = cachedModels.find(row => row.id === button.dataset.id);
  if (!model) return;
  const action = button.dataset.action;
  if (action === 'edit') { openModel(model); return; }
  if (action === 'delete' && !confirm('确定删除这个模型配置？')) return;
  button.disabled = true;
  try {
    const path = '/models/' + encodeURIComponent(model.id);
    await adminFetch(path + (action === 'delete' ? '' : '/' + action), {method:action === 'delete' ? 'DELETE' : 'PUT', ...(action === 'toggle' ? {body:JSON.stringify({enabled:!model.is_enabled})} : {})});
    await loadModels();
  } catch (exc) { error(exc.message); button.disabled = false; }
});
el('model-form').addEventListener('submit', async event => {
  event.preventDefault();
  const id = el('model-id').value;
  const body = {alias:el('m-alias').value, provider:el('m-provider').value, model_name:el('m-model').value, base_url:el('m-url').value, api_key_env_var:el('m-keyenv').value};
  el('model-save').disabled = el('btn-modal-cancel').disabled = true;
  try {
    await adminFetch('/models' + (id ? '/' + encodeURIComponent(id) : ''), {method:id ? 'PUT' : 'POST', body:JSON.stringify(body)});
    closeModel(); await loadModels();
  } catch (exc) { error(exc.message, 'model-error'); }
  finally { el('model-save').disabled = el('btn-modal-cancel').disabled = false; }
});
el('logout').addEventListener('click', () => {
  fetch(API_BASE + '/auth/logout', {method:'POST', headers:authHeaders(), body:JSON.stringify({refresh_token:localStorage.getItem('alfred_refresh')})}).catch(() => {});
  clearAuthAndRedirect();
});
checkAuth().then(user => { if (user) loadDashboard(); });
