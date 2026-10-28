import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { fileURLToPath } from 'node:url';
import { SignJWT } from 'jose';
import { sql } from 'kysely';
import { connect } from '../src/db/database.js';
import { migrate, ready } from '../src/db/migrate.js';
import { Repository } from '../src/repository.js';
import { emptyBrief } from '../src/brief.js';
import { buildApp } from '../src/app.js';

const url = process.env.DUDE_TEST_DATABASE_URL;
// Deliberately no fallback to DUDE_ORCHESTRATOR_DATABASE_URL, DATABASE_URL or .env.
test('PostgreSQL persistence and authenticated HTTP boundaries', { skip: !url && 'set explicit DUDE_TEST_DATABASE_URL to an EMPTY disposable database' }, async t => {
  assert.ok(url);
  const parsed = new URL(url);
  assert.match(parsed.pathname, /^\/dude_orchestrator_test_[a-z0-9_]+$/);
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(parsed.hostname), 'test must target local disposable PostgreSQL');
  const db = connect(url);
  t.after(() => db.destroy());
  const tables = await sql<{ name: string }>`select tablename as name from pg_tables where schemaname = 'public'`.execute(db);
  assert.equal(tables.rows.length, 0, 'refusing to run on a nonempty database; create a fresh disposable DB');
  const owner = randomUUID(), other = randomUUID(), inactive = randomUUID();
  // Auth fixture only. Production auth schema remains owned by Go.
  await sql`create table public.admin_users (id uuid primary key, role text not null, is_active boolean not null)`.execute(db);
  await db.insertInto('admin_users').values([
    { id: owner, role: 'user', is_active: true }, { id: other, role: 'admin', is_active: true },
    { id: inactive, role: 'user', is_active: false },
  ]).execute();
  await sql`create table public.legacy_marker (id int primary key, value text not null)`.execute(db);
  await sql`insert into public.legacy_marker values (1, 'preserve me')`.execute(db);
  const repository = new Repository(db);

  await t.test('migration idempotency, readiness and legacy-table preservation', async () => {
    assert.equal(await ready(db), false);
    await Promise.all([migrate(db), migrate(db)]);
    assert.equal(await ready(db), true);
    const applied = await db.selectFrom('dude_orchestrator_migrations').selectAll().execute();
    assert.equal(applied.length, 1);
    await db.updateTable('dude_orchestrator_migrations').set({ checksum: 'tampered' }).execute();
    await assert.rejects(migrate(db), /history mismatch/);
    assert.equal(await ready(db), false);
    await db.updateTable('dude_orchestrator_migrations').set({ checksum: applied[0]!.checksum }).execute();
    assert.equal((await sql<{ value: string }>`select value from public.legacy_marker`.execute(db)).rows[0]!.value, 'preserve me');
    assert.equal((await db.selectFrom('admin_users').selectAll().execute()).length, 3);
  });

  const project = await repository.create(owner, '读书清单');
  const otherProject = await repository.create(other, '另一个人的项目');
  let revision = 1;
  const brief = emptyBrief();
  brief.idea = { value: '记下读过的书', source: 'user_stated' };
  brief.demo_action = { value: '输入书名并保存', source: 'user_stated' };
  brief.demo_result = { value: '在列表里看到新书', source: 'defaulted' };
  await t.test('empty Demo is rejected; optimistic draft writes have one winner', async () => {
    await assert.rejects(repository.startGeneration(owner, project.id, 1, 'empty', { kind: 'none' }), /demo_not_ready/);
    const results = await Promise.allSettled([
      repository.updateDraft(owner, project.id, 1, brief), repository.updateDraft(owner, project.id, 1, brief),
    ]);
    assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
    assert.match((results.find(r => r.status === 'rejected') as PromiseRejectedResult).reason.message, /draft_conflict/);
    revision = (await repository.detail(owner, project.id)).revision;
    await assert.rejects(repository.updateDraft(other, project.id, revision, brief), /project_not_found/);
  });

  const run = await repository.startGeneration(owner, project.id, revision, 'first', { kind: 'seed', version: 'seed-1' });
  const pair = { technical_plan: '# 技术方案\n实现读书清单。', demo_guide: '# 体验 Demo\n打开页面，输入书名并保存。' };
  await t.test('freeze, idempotent retries and single active run', async () => {
    const retry = await repository.startGeneration(owner, project.id, revision, 'first', { kind: 'seed', version: 'seed-1' });
    assert.equal(retry.id, run.id);
    await assert.rejects(repository.startGeneration(owner, project.id, revision, 'first', { kind: 'none' }), /idempotency_conflict/);
    await assert.rejects(repository.startGeneration(owner, project.id, revision, 'other-key', { kind: 'none' }), /generation_in_progress/);
    brief.idea.value = '后来改变的想法';
    await repository.updateDraft(owner, project.id, revision++, brief);
    const frozen = await repository.version(owner, project.id, 1);
    assert.equal(frozen.content.idea.value, '记下读过的书');
    assert.equal(frozen.technical_plan, null);
    await assert.rejects(db.updateTable('dude_brief_versions').set({ content: brief }).where('id', '=', run.brief_version_id).execute(), /immutable/);
  });

  await t.test('paired documents publish atomically and completed versions cannot be rewritten', async () => {
    await assert.rejects(repository.completeGeneration(owner, project.id, run.id, { ...pair, demo_guide: '' }));
    // Deliberate second-write failure rolls back status as well as artifacts.
    await assert.rejects(db.transaction().execute(async trx => {
      await trx.updateTable('dude_generation_runs').set({ status: 'succeeded', finished_at: new Date() }).where('id', '=', run.id).execute();
      await trx.insertInto('dude_artifact_versions').values({ id: randomUUID(), project_id: project.id, brief_version_id: run.brief_version_id,
        run_id: run.id, technical_plan: 'partial', demo_guide: '' }).execute();
    }));
    assert.equal((await repository.versions(owner, project.id))[0]!.status, 'running');
    // Even raw SQL cannot commit a successful run without its pair.
    await assert.rejects(db.updateTable('dude_generation_runs').set({ status: 'succeeded', finished_at: new Date() }).where('id', '=', run.id).execute(), /complete delivery/);
    const artifact = await repository.completeGeneration(owner, project.id, run.id, pair);
    assert.equal((await repository.completeGeneration(owner, project.id, run.id, pair)).id, artifact.id);
    await assert.rejects(repository.completeGeneration(owner, project.id, run.id, { ...pair, demo_guide: 'different' }), /delivery_conflict/);
    await assert.rejects(repository.failGeneration(owner, project.id, run.id, 'model_error'), /run_finished/);
    await assert.rejects(db.updateTable('dude_artifact_versions').set({ demo_guide: 'modified' }).where('id', '=', artifact.id).execute(), /immutable/);
    await assert.rejects(db.deleteFrom('dude_artifact_versions').where('id', '=', artifact.id).execute(), /complete delivery/);
    assert.equal((await repository.version(owner, project.id, 1)).demo_guide, pair.demo_guide);
  });

  await t.test('failed generation leaves previous pair readable and versions remain linear', async () => {
    const results = await Promise.allSettled([
      repository.startGeneration(owner, project.id, revision, 'second-a', { kind: 'none' }),
      repository.startGeneration(owner, project.id, revision, 'second-b', { kind: 'none' }),
    ]);
    assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
    const next = results.find(r => r.status === 'fulfilled') as PromiseFulfilledResult<typeof run>;
    await assert.rejects(repository.completeGeneration(other, project.id, next.value.id, pair), /project_not_found/);
    await repository.failGeneration(owner, project.id, next.value.id, 'invalid_output');
    await repository.failGeneration(owner, project.id, next.value.id, 'invalid_output');
    await assert.rejects(repository.completeGeneration(owner, project.id, next.value.id, pair), /run_finished/);
    assert.equal((await repository.version(owner, project.id, 2)).demo_guide, null);
    assert.equal((await repository.version(owner, project.id, 1)).demo_guide, pair.demo_guide);
    const third = await repository.startGeneration(owner, project.id, revision, 'third', { kind: 'none' });
    // Foreign keys prevent pairing a run with another snapshot, even in the same project.
    await assert.rejects(db.insertInto('dude_artifact_versions').values({ id: randomUUID(), project_id: project.id,
      run_id: third.id, brief_version_id: run.brief_version_id, ...pair }).execute());
    await repository.failGeneration(owner, project.id, third.id, 'interrupted');
    assert.deepEqual((await repository.versions(owner, project.id)).map(v => v.version), [3, 2, 1]);
  });

  await t.test('HTTP: auth, ownership, validation, read-only versions and cascaded deletion', async () => {
    const secret = 'isolated-http-test-secret-never-deploy';
    const app = buildApp(db, secret, false);
    t.after(() => app.close());
    async function headers(id: string, role = 'user', issuer = 'alfred-admin') {
      const jwt = await new SignJWT({ user_id: id, username: 'fixture', role }).setSubject(id).setIssuer(issuer)
        .setProtectedHeader({ alg: 'HS256' }).setIssuedAt().setExpirationTime('5m').sign(new TextEncoder().encode(secret));
      return { authorization: `Bearer ${jwt}` };
    }
    const user = await headers(owner), admin = await headers(other, 'admin');
    assert.equal((await app.inject('/health/ready')).statusCode, 200);
    assert.equal((await app.inject('/api/v2/projects')).statusCode, 401);
    assert.equal((await app.inject({ url: '/api/v2/projects', headers: await headers(inactive) })).statusCode, 401);
    assert.equal((await app.inject({ url: '/api/v2/projects', headers: await headers(owner, 'user', 'wrong') })).statusCode, 401);
    assert.equal((await app.inject({ url: '/api/v2/projects', headers: user })).json().items.length, 1);
    assert.equal((await app.inject({ url: '/api/v2/projects?limit=999', headers: user })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/v2/projects', headers: user, payload: { title: 'x', owner_id: other } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/v2/projects', headers: user, payload: { title: '  ' } })).statusCode, 400);
    assert.equal((await app.inject({ method: 'POST', url: '/api/v2/projects', headers: user, payload: { title: 'x'.repeat(20000) } })).statusCode, 413);
    const created = await app.inject({ method: 'POST', url: '/api/v2/projects', headers: user, payload: { title: '  API 项目  ' } });
    assert.equal(created.statusCode, 201);
    assert.equal(created.json().owner_id, owner);
    assert.equal(created.json().title, 'API 项目');
    await repository.remove(owner, created.json().id);
    for (const suffix of ['', '/versions', '/versions/1']) {
      const response = await app.inject({ url: `/api/v2/projects/${project.id}${suffix}`, headers: admin });
      assert.equal(response.statusCode, 404);
      assert.equal(response.headers['cache-control'], 'no-store');
    }
    const version = await app.inject({ url: `/api/v2/projects/${project.id}/versions/1`, headers: user });
    assert.equal(version.statusCode, 200);
    assert.equal(version.json().technical_plan, pair.technical_plan);
    assert.equal((await app.inject({ method: 'PATCH', url: `/api/v2/projects/${project.id}`, headers: user, payload: { content: brief } })).statusCode, 404);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/v2/projects/${project.id}`, headers: admin })).statusCode, 404);
    assert.equal((await app.inject({ method: 'DELETE', url: `/api/v2/projects/${project.id}`, headers: user })).statusCode, 204);
    for (const table of ['dude_brief_drafts', 'dude_brief_versions', 'dude_generation_runs', 'dude_artifact_versions'] as const) {
      assert.equal((await db.selectFrom(table).selectAll().where('project_id', '=', project.id).execute()).length, 0);
    }
    assert.equal((await repository.detail(other, otherProject.id)).title, '另一个人的项目');
    await assert.rejects(repository.detail(owner, project.id), /project_not_found/);
  });

  await t.test('real server process starts, serves HTTP, stops cleanly and fails closed without config', async () => {
    const probe = createServer();
    await new Promise<void>(resolve => probe.listen(0, '127.0.0.1', resolve));
    const address = probe.address();
    assert.ok(address && typeof address !== 'string');
    const port = address.port;
    await new Promise<void>(resolve => probe.close(() => resolve()));
    const entry = fileURLToPath(new URL('../src/server.js', import.meta.url));
    const secret = 'local-subprocess-test-secret-not-for-production';
    const child = spawn(process.execPath, [entry], {
      env: { ...process.env, DUDE_ORCHESTRATOR_DATABASE_URL: url, JWT_SECRET: secret,
        DUDE_ORCHESTRATOR_HOST: '127.0.0.1', DUDE_ORCHESTRATOR_PORT: String(port) },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let logs = '';
    child.stdout.on('data', data => { logs += data; });
    child.stderr.on('data', data => { logs += data; });
    const exited = new Promise<void>(resolve => child.once('exit', () => resolve()));
    t.after(async () => { if (child.exitCode === null) { child.kill(); await exited; } });
    const base = `http://127.0.0.1:${port}`;
    let responding = false;
    for (let i = 0; i < 60; i++) {
      if (child.exitCode !== null) throw new Error('server exited before becoming ready');
      try {
        const response = await fetch(`${base}/health/ready`, { signal: AbortSignal.timeout(500) });
        if (response.status === 200) { responding = true; break; }
      } catch { /* startup race */ }
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.equal(responding, true);
    assert.equal((await fetch(`${base}/api/v2/projects`)).status, 401);
    const jwt = await new SignJWT({ user_id: other, username: 'other', role: 'admin' }).setSubject(other)
      .setIssuer('alfred-admin').setProtectedHeader({ alg: 'HS256' }).setIssuedAt().setExpirationTime('5m')
      .sign(new TextEncoder().encode(secret));
    const headers = { authorization: `Bearer ${jwt}`, 'content-type': 'application/json' };
    const created = await fetch(`${base}/api/v2/projects`, { method: 'POST', headers, body: JSON.stringify({ title: 'real-http-private-marker' }) });
    assert.equal(created.status, 201);
    const body = await created.json() as { id: string };
    assert.equal((await fetch(`${base}/api/v2/projects/${body.id}`, { method: 'DELETE', headers: { authorization: `Bearer ${jwt}` } })).status, 204);
    child.kill('SIGTERM');
    await exited;
    // Windows terminates processes directly; POSIX handler exits normally.
    if (process.platform !== 'win32') assert.equal(child.exitCode, 0);
    assert.equal(logs.includes('real-http-private-marker'), false);
    assert.equal(logs.includes(jwt), false);
    assert.equal(logs.includes(url), false);
    const invalid = spawn(process.execPath, [entry], {
      env: { ...process.env, DUDE_ORCHESTRATOR_DATABASE_URL: '', JWT_SECRET: '' }, stdio: 'ignore',
    });
    const code = await new Promise<number | null>(resolve => invalid.once('exit', resolve));
    assert.equal(code, 1);
  });
});
