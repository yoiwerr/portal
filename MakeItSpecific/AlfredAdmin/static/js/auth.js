// Alfred Auth — login / register / token management

const API_BASE = '/alfred/api/v1';
const CHAT_URL = '/alfred/';

// ── Tab switching ──
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const target = tab.dataset.tab;
    document.getElementById('login-form').classList.toggle('active', target === 'login');
    document.getElementById('register-form').classList.toggle('active', target === 'register');
    document.querySelectorAll('.error').forEach(e => e.textContent = '');
  });
});

// ── Helpers ──
function showError(formId, msg) {
  document.getElementById(formId + '-error').textContent = msg;
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  btn.disabled = loading;
  btn.textContent = loading ? '...' : (btnId === 'login-btn' ? '登 录' : '注 册');
}

function saveAuth(data) {
  localStorage.setItem('alfred_token', data.access_token);
  localStorage.setItem('alfred_refresh', data.refresh_token);
  localStorage.setItem('alfred_user', JSON.stringify({
    user_id: data.user?.user_id || '',
    username: data.user?.username || '',
    role: data.user?.role || 'user',
  }));
}

// ── Login ──
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  showError('login', '');
  setLoading('login-btn', true);

  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;

  if (!username || !password) {
    showError('login', '请填写用户名和密码');
    setLoading('login-btn', false);
    return;
  }

  try {
    const res = await fetch(API_BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      const err = await res.json();
      showError('login', err.error?.message || '登录失败');
      setLoading('login-btn', false);
      return;
    }

    const data = await res.json();
    saveAuth({ ...data, user: { username, role: 'user' } });

    // Fetch /me to get full user info
    try {
      const meRes = await fetch(API_BASE + '/auth/me', {
        headers: { 'Authorization': 'Bearer ' + data.access_token },
      });
      if (meRes.ok) {
        const me = await meRes.json();
        saveAuth({ ...data, user: me });
      }
    } catch (_) {}

    window.location.href = CHAT_URL;
  } catch (err) {
    showError('login', '网络错误，请重试');
  }
  setLoading('login-btn', false);
});

// ── Register ──
document.getElementById('register-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  showError('reg', '');
  setLoading('reg-btn', true);

  const username = document.getElementById('reg-username').value.trim();
  const password = document.getElementById('reg-password').value;

  if (!username || !password) {
    showError('reg', '请填写用户名和密码');
    setLoading('reg-btn', false);
    return;
  }
  if (username.length < 3) {
    showError('reg', '用户名至少 3 个字符');
    setLoading('reg-btn', false);
    return;
  }
  if (password.length < 6) {
    showError('reg', '密码至少 6 个字符');
    setLoading('reg-btn', false);
    return;
  }

  try {
    const res = await fetch(API_BASE + '/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!res.ok) {
      const err = await res.json();
      showError('reg', err.error?.message || '注册失败');
      setLoading('reg-btn', false);
      return;
    }

    // Auto-login after register
    const loginRes = await fetch(API_BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!loginRes.ok) {
      showError('reg', '注册成功但自动登录失败，请手动登录');
      document.querySelector('.tab[data-tab="login"]').click();
      setLoading('reg-btn', false);
      return;
    }

    const data = await loginRes.json();
    saveAuth({ ...data, user: { username, role: 'user' } });
    window.location.href = CHAT_URL;
  } catch (err) {
    showError('reg', '网络错误，请重试');
  }
  setLoading('reg-btn', false);
});

// ── Refresh token on page load ──
async function trySilentRefresh() {
  const refreshToken = localStorage.getItem('alfred_refresh');
  const accessToken = localStorage.getItem('alfred_token');
  if (!refreshToken || accessToken) return; // only refresh if we have no access token

  try {
    const res = await fetch(API_BASE + '/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('alfred_token', data.access_token);
      localStorage.setItem('alfred_refresh', data.refresh_token);
      window.location.href = CHAT_URL;
    }
  } catch (_) {}
}

trySilentRefresh();
