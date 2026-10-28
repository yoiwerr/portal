import { z } from 'zod';

export function databaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  const value = env.DUDE_ORCHESTRATOR_DATABASE_URL;
  if (!value) throw new Error('DUDE_ORCHESTRATOR_DATABASE_URL is required');
  try {
    const url = new URL(value);
    if (!['postgres:', 'postgresql:'].includes(url.protocol) || !url.hostname || !url.username || !url.password || url.pathname.length < 2) {
      throw new Error();
    }
  } catch {
    throw new Error('DUDE_ORCHESTRATOR_DATABASE_URL must be a PostgreSQL URL with explicit user, password and database');
  }
  return value;
}

export function config(env: NodeJS.ProcessEnv = process.env) {
  const secret = env.JWT_SECRET;
  if (!secret || Buffer.byteLength(secret, 'utf8') < 32) {
    throw new Error('JWT_SECRET must match dude-admin and contain at least 32 bytes');
  }
  return {
    databaseUrl: databaseUrl(env), secret,
    host: env.DUDE_ORCHESTRATOR_HOST || '127.0.0.1',
    port: z.coerce.number().int().min(1).max(65535).parse(env.DUDE_ORCHESTRATOR_PORT || '8010'),
  };
}
