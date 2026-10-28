import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { SignJWT } from 'jose';
import { authenticate } from '../src/auth.js';
import { config, databaseUrl } from '../src/config.js';
import { briefSchema, canGenerate, emptyBrief } from '../src/brief.js';

const secret = 'isolated-unit-test-key-not-for-deployment';
const owner = randomUUID();
async function token(payload: Record<string, unknown> = {}, issuer = 'alfred-admin') {
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ sub: owner, user_id: owner, username: 'test', role: 'user', iat: now, exp: now + 300, ...payload })
    .setProtectedHeader({ alg: 'HS256' }).setIssuer(issuer).sign(new TextEncoder().encode(secret));
}

test('Go JWT compatibility and invalid identity/expiry/issuer rejection', async () => {
  assert.equal(await authenticate(`Bearer ${await token()}`, secret), owner);
  for (const header of [undefined, 'Basic abc', `Bearer ${await token({ user_id: randomUUID() })}`,
    `Bearer ${await token({ exp: 1 })}`, `Bearer ${await token({}, 'other')}`,
    `Bearer ${await token({ iat: undefined })}`, `Bearer ${await token({ iat: Date.now() })}`,
    `Bearer ${await token({ role: 'superuser' })}`]) {
    await assert.rejects(authenticate(header, secret), /unauthorized/);
  }
  await assert.rejects(authenticate(`Bearer ${await token()}`, 'different-key'), /unauthorized/);
});

test('Brief generation gate is action/result, not user profile or technology', () => {
  const brief = emptyBrief();
  assert.equal(canGenerate(brief), false);
  brief.demo_action = { value: '输入一本书的名字', source: 'user_stated' };
  brief.demo_result = { value: '在书单里看到它', source: 'defaulted', reason: '最小 Demo 默认值' };
  assert.equal(canGenerate(briefSchema.parse(brief)), true);
  brief.demo_result.source = 'agent_suggested';
  assert.equal(canGenerate(brief), false);
  assert.equal(briefSchema.safeParse({ ...brief, model_key: 'bad' }).success, false);
});

test('configuration never falls back to business database or weak secrets', () => {
  assert.throws(() => databaseUrl({ DATABASE_URL: 'postgresql://localhost/production' }), /required/);
  assert.throws(() => databaseUrl({ DUDE_ORCHESTRATOR_DATABASE_URL: 'https://example.com' }), /PostgreSQL/);
  assert.throws(() => databaseUrl({ DUDE_ORCHESTRATOR_DATABASE_URL: 'postgresql://localhost/test' }), /explicit user, password/);
  assert.throws(() => config({ JWT_SECRET: 'short' }), /32 bytes/);
  assert.throws(() => config({ JWT_SECRET: secret, DUDE_ORCHESTRATOR_DATABASE_URL: 'postgresql://test:local@localhost/test', DUDE_ORCHESTRATOR_PORT: '-1' }));
  assert.equal(config({ JWT_SECRET: secret, DUDE_ORCHESTRATOR_DATABASE_URL: 'postgresql://test:local@localhost/test' }).host, '127.0.0.1');
});
