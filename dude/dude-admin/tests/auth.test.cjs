// Run with: node --test dude/dude-admin/tests/auth.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const sources = Object.fromEntries(Object.entries({
  auth: '../static/js/auth.js', admin: '../static/js/admin.js', chat: '../../static/js/chat.js',
}).map(([key, filename]) => [key, fs.readFileSync(path.join(__dirname, filename), 'utf8')]));

async function browser({ initial = {}, responses = [], script = 'auth', href = '', width = 1440 } = {}) {
  const store = new Map(Object.entries(initial));
  const calls = [];
  const elements = new Map();
  function makeElement(id = '') {
    const attrs = {};
    const node = {
      id, value: '', textContent: '', disabled: false, handlers: {}, innerHTML: '',
      style: {}, hidden: true, className: '', children: [], scrollHeight: 60,
      focus() {}, setAttribute(key, value) { attrs[key] = value; },
      contains(child) { return this.children.includes(child); },
      getAttribute: key => attrs[key], removeAttribute(key) { delete attrs[key]; },
      addEventListener(event, handler) { this.handlers[event] = handler; },
      appendChild(child) { this.children.push(child); child.parent = this; if (child.text !== undefined) this.innerHTML = child.text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); },
      remove() { if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this); },
      querySelectorAll(selector) { return this.children.flatMap(child => [child, ...child.querySelectorAll(selector)]).filter(child => selector.startsWith('.') && child.className.split(' ').includes(selector.slice(1))); },
      querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
      scrollIntoView() {}, getClientRects() { return [1]; },
    };
    node.classList = {
      add(name) { if (!node.className.split(' ').includes(name)) node.className += ' ' + name; },
      remove(name) { node.className = node.className.split(' ').filter(x => x !== name).join(' '); },
      toggle(name, on) { this[on ? 'add' : 'remove'](name); },
      contains(name) { return node.className.split(' ').includes(name); },
    };
    return node;
  }
  function element(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
  }
  const context = vm.createContext({
    document: {
      body: makeElement('body'),
      getElementById: element,
      querySelectorAll: () => [],
      querySelector: () => ({ click() {} }),
      addEventListener() {},
      createTextNode: text => ({ text }),
      createElement: () => makeElement(),
    },
    localStorage: {
      getItem: key => store.get(key) || null,
      setItem: (key, value) => store.set(key, String(value)),
      removeItem: key => store.delete(key),
    },
    window: { location: { href }, innerWidth: width, addEventListener() {} },
    URL, TextDecoder, Uint8Array, console,
    IntersectionObserver: class { observe() {} },
    atob: value => Buffer.from(value, 'base64').toString('binary'),
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      assert.ok(responses.length, 'unexpected fetch: ' + url);
      const response = responses.shift();
      if (response.networkError) throw new Error('offline');
      return {
        status: response.status, ok: response.status >= 200 && response.status < 300,
        body: response.stream === undefined ? null : new ReadableStream({
          start(controller) {
            for (const part of response.stream) controller.enqueue(Buffer.from(part));
            controller.close();
          },
        }),
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
    '/dude/api/v1/auth/login', '/dude/api/v1/auth/me',
  ]);
  assert.equal(app.store.get('alfred_token'), 'access');
  assert.equal(JSON.parse(app.store.get('alfred_user')).role, 'admin');
  assert.equal(app.context.window.location.href, '/dude/');
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
    '/dude/api/v1/auth/register', '/dude/api/v1/auth/login',
  ]);
  assert.equal(app.context.window.location.href, '/dude/');
});

test('expired access tokens do not block silent refresh', async () => {
  const expired = 'header.' + Buffer.from(JSON.stringify({ exp: 1 })).toString('base64url') + '.signature';
  const app = await browser({
    initial: { alfred_token: expired, alfred_refresh: 'old-refresh' },
    responses: [{ status: 200, body: { access_token: 'new-access', refresh_token: 'new-refresh' } }],
  });
  assert.equal(app.calls[0].url, '/dude/api/v1/auth/refresh');
  assert.equal(app.store.get('alfred_token'), 'new-access');
  assert.equal(app.store.get('alfred_refresh'), 'new-refresh');
  assert.equal(app.context.window.location.href, '/dude/');
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
  assert.equal(app.context.window.location.href, '/dude/');
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
    assert.equal(app.context.window.location.href, '/dude/auth/');
    assert.equal(app.calls.length, 2);
  });

  test(`${script}: missing credentials redirect without calling the server`, async () => {
    const app = await browser({ script });
    assert.equal(app.calls.length, 0);
    assert.equal(app.context.window.location.href, '/dude/auth/');
  });

  test(`${script}: a second 401 stops refresh and redirect loops`, async () => {
    const app = await browser({ script, initial, responses: [{ status: 401 }, renewed, { status: 401 }] });
    assert.equal(app.calls.length, 3);
    assert.equal(app.store.size, 0);
    assert.equal(app.context.window.location.href, '/dude/auth/');
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
  assert.equal(app.context.window.location.href, '/dude/');
});

const adminMe = { status: 200, body: { username: 'administrator', role: 'admin' } };
const overview = { status: 200, body: { total_users: 2, admin_users: 1, active_users: 2, calls: 0, total_tokens: 0, input_tokens: 0, output_tokens: 0, period_start: '2026-09-19T00:00:00Z', as_of: '2026-10-19T00:00:00Z' } };

test('admin renders zero usage and escapes account HTML', async () => {
  const app = await browser({script:'admin', initial:{alfred_token:'access'}, responses:[adminMe, overview]});
  assert.match(app.element('stats-summary').innerHTML, /模型调用/);
  const html = vm.runInContext('renderUsers([{username:"<img src=x onerror=alert(1)>",id:"account",role:"user",is_active:true,calls:0}])',app.context);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /普通用户/);
  assert.match(html, /暂无记录/);
});

test('admin search encodes filters and handles empty results', async () => {
  const app = await browser({script:'admin', initial:{alfred_token:'access'}, responses:[adminMe, overview,
    {status:200,body:{users:[],total:0,page:1,page_size:20}}]});
  app.element('user-search').value='name&role=admin';
  app.element('user-role').value='user';
  await vm.runInContext('loadUsers(1)',app.context);
  assert.match(app.calls.at(-1).url,/q=name%26role%3Dadmin&role=user/);
  assert.match(app.element('users-list').innerHTML,/没有符合条件/);
  assert.equal(app.element('users-next').disabled,true);
});

test('admin API refreshes an expired token once before loading users', async () => {
  const app = await browser({script:'admin', initial:{alfred_token:'access',alfred_refresh:'refresh'}, responses:[adminMe,overview,
    {status:401}, {status:200,body:{access_token:'renewed',refresh_token:'rotated'}},
    {status:200,body:{users:[],total:0,page:1,page_size:20}}]});
  await vm.runInContext('loadUsers(1)',app.context);
  assert.equal(app.calls.at(-1).options.headers.Authorization,'Bearer renewed');
  assert.equal(app.store.get('alfred_refresh'),'rotated');
});

test('admin user-load failure is visible and never masquerades as an empty list', async () => {
  const app = await browser({script:'admin', initial:{alfred_token:'access'}, responses:[adminMe,overview,{status:503}]});
  await vm.runInContext('loadUsers(1)',app.context);
  assert.equal(app.element('page-error').hidden,false);
  assert.match(app.element('users-list').textContent,/加载失败/);
  assert.equal(app.store.get('alfred_token'),'access');
});

test('admin API 403 hides the page and returns to chat', async () => {
  const app = await browser({script:'admin', initial:{alfred_token:'access'}, responses:[adminMe,overview,{status:403}]});
  await vm.runInContext('loadUsers(1)',app.context);
  assert.equal(app.element('admin-content').hidden,true);
  assert.equal(app.context.window.location.href,'/dude/');
});

test('chat only exposes the admin entry for a server-confirmed administrator', async () => {
  for (const role of ['admin','user']) {
    const app = await browser({script:'chat',initial:{alfred_token:'access',alfred_user:'{"role":"admin"}'},responses:[{status:200,body:{username:'tester',role}}]});
    assert.equal(app.element('topbarUserArea').innerHTML.includes('href="/dude/admin/"'),role==='admin');
    assert.match(app.element('topbarUserArea').innerHTML,role==='admin' ? /管理员/ : /普通用户/);
  }
});

const meResponse = { status: 200, body: { username: 'tester', role: 'user' } };
const frame = (event, data) => `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
const contract = { goal: '阅读记录工具', scope: { in: ['添加书籍'], out: ['社区'] }, confidence: 0.6, status: 'draft' };
const replyStream = [frame('session', { session_id: 'test-session' }), frame('contract', { contract }), frame('clarify', { message: '你想记录哪些内容？' }), frame('done', {})];

test('chat uses the dude prefix and handles arbitrarily split SSE frames', async () => {
  const stream = replyStream.join('');
  const app = await browser({ script: 'chat', href: 'https://example.test/dude/', initial: { alfred_token: 'access' },
    responses: [meResponse, { status: 200, stream: Array.from(stream) }],
  });
  app.element('userInput').value = '做一个阅读记录工具';
  await app.context.window.sendMessage();
  assert.equal(app.calls[1].url, '/dude/api/chat/message');
  assert.equal(app.calls[1].options.headers.Authorization, 'Bearer access');
  assert.equal(app.element('ccGoal').textContent, contract.goal);
  assert.equal(app.element('contractSidebar').hidden, false);
  assert.equal(app.element('composerError').hidden, true);
  assert.equal(app.element('sendBtn').disabled, false);
  assert.equal(app.element('messages').querySelectorAll('.msg-thinking').length, 0);
});

test('mobile receives a summary without opening a drawer over the conversation', async () => {
  const app = await browser({ script: 'chat', width: 390, initial: { alfred_token: 'access' }, responses: [meResponse, { status: 200, stream: replyStream }] });
  app.element('userInput').value = '想法';
  await app.context.window.sendMessage();
  assert.equal(app.element('summaryToggle').hidden, false);
  assert.equal(app.element('contractSidebar').hidden, true);
  app.context.window.toggleSummary(true);
  assert.equal(app.element('workspace').inert, true);
  assert.equal(app.element('panelBackdrop').hidden, false);
  app.context.window.toggleSummary(false);
  assert.equal(app.element('workspace').inert, false);
});

for (const failure of [{ status: 503 }, { networkError: true }, { status: 200, stream: [frame('done', {})] }, { status: 200, stream: [frame('error', { detail: 'failed' })] }]) {
  test('chat failures keep the draft and remove waiting state: ' + JSON.stringify(failure), async () => {
    const app = await browser({ script: 'chat', initial: { alfred_token: 'access' }, responses: [meResponse, failure] });
    app.element('userInput').value = '保留这个想法';
    await app.context.window.sendMessage();
    assert.equal(app.element('userInput').value, '保留这个想法');
    assert.equal(app.element('composerError').hidden, false);
    assert.equal(app.element('messages').querySelectorAll('.msg-thinking').length, 0);
    assert.equal(app.element('sendBtn').disabled, false);
  });
}

test('examples fill a draft without spending a model request', async () => {
  const app = await browser({ script: 'chat', initial: { alfred_token: 'access' }, responses: [meResponse] });
  app.context.window.useExample('一个个人网站');
  assert.equal(app.element('userInput').value, '一个个人网站');
  assert.equal(app.calls.length, 1);
});

test('Chinese IME Enter and Shift+Enter do not send', async () => {
  const app = await browser({ script: 'chat' });
  let sends = 0;
  app.context.window.sendMessage = () => sends++;
  for (const options of [{ isComposing: true }, { keyCode: 229 }, { shiftKey: true }]) {
    app.context.window.handleKey({ key: 'Enter', preventDefault() { throw Error('must preserve input'); }, ...options });
  }
  assert.equal(sends, 0);
  app.context.window.handleKey({ key: 'Enter', preventDefault() {} });
  assert.equal(sends, 1);
});

test('failed summary confirmation never marks it confirmed', async () => {
  const app = await browser({ script: 'chat', href: 'https://example.test/dude/', initial: { alfred_token: 'access' }, responses: [meResponse, { status: 200, stream: replyStream }, { status: 503 }] });
  app.element('userInput').value = '想法';
  await app.context.window.sendMessage();
  await app.context.window.confirmContract();
  assert.equal(app.calls[2].url, '/dude/api/chat/test-session/contract/confirm');
  assert.equal(app.element('summaryError').hidden, false);
  assert.equal(app.element('ccActions').style.display, 'flex');
  assert.equal(app.element('ccStatus').children[0].textContent, '待确认');
});

test('formatted plans render headings and lists but escape embedded HTML', async () => {
  const app = await browser({ script: 'chat', initial: { alfred_token: 'access' }, responses: [meResponse, { status: 200, stream: [frame('execute', { message: '# 项目方案\n\n- 功能一\n- 功能二\n\n<script>alert(1)</script>' }), frame('done', {})] }] });
  app.element('userInput').value = '想法';
  await app.context.window.sendMessage();
  const html = app.element('messages').querySelectorAll('.msg-row')[0].innerHTML;
  assert.match(html, /<h2>项目方案<\/h2>/);
  assert.match(html, /<ul><li>功能一<\/li><li>功能二<\/li><\/ul>/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
});

test('failed summary edits remain editable instead of pretending to save', async () => {
  const app = await browser({ script: 'chat', initial: { alfred_token: 'access' }, responses: [meResponse, { status: 200, stream: replyStream }, { status: 503 }] });
  app.element('userInput').value = '想法';
  await app.context.window.sendMessage();
  app.context.window.modifyContract();
  app.element('edit_goal').value = '尚未保存的修改';
  await app.element('ccBtnModify').onclick();
  assert.match(app.element('summaryError').textContent, /尚未保存/);
  assert.equal(app.element('edit_goal').value, '尚未保存的修改');
  assert.equal(app.element('ccBtnConfirm').disabled, true);
});

test('Markdown preserves safe links and blocks HTML or script URLs', async () => {
  const app = await browser({ script: 'chat', initial: { alfred_token: 'access' }, responses: [meResponse, { status: 200, stream: [frame('execute', { message: '[参考](https://example.com/) [旧文档](/docs) [危险](javascript:alert(1)) [<img src=x onerror=alert(1)>](https://example.com/)' }), frame('done', {})] }] });
  app.element('userInput').value = '想法';
  await app.context.window.sendMessage();
  const html = app.element('messages').querySelectorAll('.msg-row')[0].innerHTML;
  assert.match(html, /href="https:\/\/example.com\/"/);
  assert.match(html, /href="\/docs"/);
  assert.doesNotMatch(html, /href="javascript:|<img/);
});
