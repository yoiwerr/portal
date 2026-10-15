// Run with: node --test MakeItSpecific/AlfredAdmin/tests/auth.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const sources = Object.fromEntries(Object.entries({
  auth: '../static/js/auth.js', admin: '../static/js/admin.js', chat: '../../static/js/chat.js',
}).map(([key, filename]) => [key, fs.readFileSync(path.join(__dirname, filename), 'utf8')]));

async function browser({ initial = {}, responses = [], script = 'auth' } = {}) {
  const store = new Map(Object.entries(initial));
  const calls = [];
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', textContent: '', disabled: false, handlers: {}, innerHTML: '',
      focus() {},
      addEventListener(event, handler) { this.handlers[event] = handler; },
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: {
      getElementById: element,
      querySelectorAll: () => [],
      querySelector: () => ({ click() {} }),
      addEventListener() {},
      createTextNode: text => ({ text }),
      createElement: () => ({ innerHTML: '', appendChild(node) { this.innerHTML = node.text; } }),
    },
    localStorage: {
      getItem: key => store.get(key) || null,
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: key => store.delete(key),
    },
    window: { location: { href: '' } },
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      assert.ok(responses.length, 'unexpected fetch: ' + url);
      const response = responses.shift();
      if (response.networkError) throw new Error('offline');
      return {
        status: response.status, ok: response.status >= 200 && response.status < 300,
        json: async () => {
          if (response.html) throw new SyntaxError('not JSON');
          return response.body;
        },
      };
    },
  });
  vm.runInContext(sources[script], context);
  await new Promise(resolve => setImmediate(resolve));
  return {
    context, store, calls, element,
    async submit(id) {
      await element(id).handlers.submit({ preventDefault() {} });
    },
  };
}

test('login uses the canonical URL, saves tokens and loads the user', async () => {
  const app = await browser({ responses: [
    { status: 200, body: { access_token: 'access', refresh_token: 'refresh' } },
    { status: 200, body: { user_id: 'id', username: 'tester', role: 'admin' } },
  ] });
  app.element('login-username').value = 'tester';
  app.element('login-password').value = 'test-password';
  await app.submit('login-form');
  assert.deepEqual(app.calls.map(call => call.url), [
    '/alfred/api/v1/auth/login', '/alfred/api/v1/auth/me',
  ]);
  assert.equal(app.store.get('alfred_token'), 'access');
  assert.equal(JSON.parse(app.store.get('alfred_user')).role, 'admin');
  assert.equal(app.context.window.location.href, '/alfred/');
});

for (const [status, message] of [
  [401, '密码错误'], [404, '登录接口不存在'], [429, '操作太频繁'], [502, '登录服务暂时不可用'],
]) {
  test('login explains HTTP ' + status + ' without redirecting', async () => {
    const app = await browser({ responses: [{
      status, html: status >= 500, body: { error: { message: '密码错误' } },
    }] });
    app.element('login-username').value = 'tester';
    app.element('login-password').value = 'wrong';
    await app.submit('login-form');
    assert.ok(app.element('login-error').textContent.includes(message));
    assert.equal(app.element('login-btn').disabled, false);
    assert.equal(app.context.window.location.href, '');
  });
}

test('malformed successful responses never store undefined tokens', async () => {
  const app = await browser({ responses: [{ status: 200, body: {} }] });
  app.element('login-username').value = 'tester';
  app.element('login-password').value = 'test-password';
  await app.submit('login-form');
  assert.equal(app.store.has('alfred_token'), false);
  assert.match(app.element('login-error').textContent, /返回异常/);
});

test('registration logs in using the same canonical route', async () => {
  const app = await browser({ responses: [
    { status: 201, body: {} },
    { status: 200, body: { access_token: 'access', refresh_token: 'refresh' } },
  ] });
  app.element('reg-username').value = 'tester';
  app.element('reg-password').value = 'test-password';
  await app.submit('register-form');
  assert.deepEqual(app.calls.map(call => call.url), [
    '/alfred/api/v1/auth/register', '/alfred/api/v1/auth/login',
  ]);
  assert.equal(app.context.window.location.href, '/alfred/');
});

test('expired access tokens do not block silent refresh', async () => {
  const expired = 'header.' + Buffer.from(JSON.stringify({ exp: 1 })).toString('base64url') + '.signature';
  const app = await browser({
    initial: { alfred_token: expired, alfred_refresh: 'old-refresh' },
    responses: [{ status: 200, body: { access_token: 'new-access', refresh_token: 'new-refresh' } }],
  });
  assert.equal(app.calls[0].url, '/alfred/api/v1/auth/refresh');
  assert.equal(app.store.get('alfred_token'), 'new-access');
  assert.equal(app.store.get('alfred_refresh'), 'new-refresh');
  assert.equal(app.context.window.location.href, '/alfred/');
});

test('missing access token is restored from refresh token', async () => {
  const app = await browser({
    initial: { alfred_refresh: 'old-refresh' },
    responses: [{ status: 200, body: { access_token: 'new-access', refresh_token: 'new-refresh' } }],
  });
  assert.equal(app.store.get('alfred_token'), 'new-access');
});

test('invalid refresh clears stale state; temporary outages do not', async () => {
  for (const status of [401, 503]) {
    const app = await browser({
      initial: { alfred_token: 'expired', alfred_refresh: 'old', alfred_user: '{}' },
      responses: [{ status, body: {} }],
    });
    assert.equal(app.store.has('alfred_refresh'), status !== 401);
    assert.equal(app.context.window.location.href, '');
  }
});

test('corrupt cached user info does not discard successfully refreshed tokens', async () => {
  const app = await browser({
    initial: { alfred_refresh: 'old', alfred_user: '{broken' },
    responses: [{ status: 200, body: { access_token: 'new', refresh_token: 'new-refresh' } }],
  });
  assert.equal(app.store.get('alfred_token'), 'new');
  assert.equal(app.context.window.location.href, '/alfred/');
});

test('registration auto-login failure displays a message in the login tab', async () => {
  const app = await browser({ responses: [{ status: 201 }, { status: 503 }] });
  app.element('reg-username').value = 'tester';
  app.element('reg-password').value = 'test-password';
  await app.submit('register-form');
  assert.match(app.element('login-error').textContent, /注册成功但自动登录失败/);
  assert.equal(app.context.window.location.href, '');
});

for (const script of ['admin', 'chat']) {
  const initial = { alfred_token: 'expired', alfred_refresh: 'refresh', alfred_user: '{}' };
  const renewed = { status: 200, body: { access_token: 'new-access', refresh_token: 'new-refresh' } };
  const me = { status: 200, body: { username: 'tester', role: 'admin', user_id: 'id' } };

  for (const missing of [false, true]) {
    test(`${script}: ${missing ? 'missing' : 'expired'} access token refreshes once`, async () => {
      const app = await browser({ script,
        initial: missing ? { alfred_refresh: 'refresh' } : initial,
        responses: [...(missing ? [] : [{ status: 401 }]), renewed, me, { status: 503 }],
      });
      assert.equal(app.store.get('alfred_token'), 'new-access');
      assert.equal(app.calls.filter(call => call.url.endsWith('/refresh')).length, 1);
      assert.equal(app.calls.findLast(call => call.url.endsWith('/me')).options.headers.Authorization, 'Bearer new-access');
      assert.equal(app.context.window.location.href, '');
    });
  }

  test(`${script}: invalid refresh clears all stale auth state`, async () => {
    const app = await browser({ script, initial, responses: [{ status: 401 }, { status: 401 }] });
    assert.equal(app.store.size, 0);
    assert.equal(app.context.window.location.href, '/alfred/auth/');
    assert.equal(app.calls.length, 2);
  });

  test(`${script}: missing credentials redirect without calling the server`, async () => {
    const app = await browser({ script });
    assert.equal(app.calls.length, 0);
    assert.equal(app.context.window.location.href, '/alfred/auth/');
  });

  test(`${script}: a second 401 stops refresh and redirect loops`, async () => {
    const app = await browser({ script, initial, responses: [{ status: 401 }, renewed, { status: 401 }] });
    assert.equal(app.calls.length, 3);
    assert.equal(app.store.size, 0);
    assert.equal(app.context.window.location.href, '/alfred/auth/');
  });

  for (const failure of [{ status: 404 }, { status: 503 }, { networkError: true }]) {
    test(`${script}: user lookup ${failure.status || 'offline'} preserves the session without refresh`, async () => {
      const app = await browser({ script, initial, responses: [failure] });
      assert.equal(app.calls.length, 1);
      assert.equal(app.store.get('alfred_refresh'), 'refresh');
      assert.equal(app.context.window.location.href, '');
      assert.match(app.element(script === 'admin' ? 'admin-user' : 'topbarUserArea').textContent, /暂时不可用/);
    });
  }

  for (const failure of [{ status: 503 }, { status: 200, body: {} }, { status: 200, body: { access_token: {}, refresh_token: 'x' } }]) {
    test(`${script}: refresh failure ${JSON.stringify(failure)} never writes invalid tokens`, async () => {
      const app = await browser({ script, initial, responses: [{ status: 401 }, failure] });
      assert.equal(app.calls.length, 2);
      assert.equal(app.store.get('alfred_token'), 'expired');
      assert.equal(app.store.get('alfred_refresh'), 'refresh');
      assert.equal(app.context.window.location.href, '');
    });
  }
}

test('admin: regular users return to chat without loading the dashboard', async () => {
  const app = await browser({ script: 'admin', initial: { alfred_token: 'access' },
    responses: [{ status: 200, body: { username: 'tester', role: 'user' } }],
  });
  assert.equal(app.calls.length, 1);
  assert.equal(app.context.window.location.href, '/alfred/');
});
