import { createHash } from 'node:crypto';
import { readdir, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { sql, type Kysely } from 'kysely';
import { connect, type Database } from './database.js';
import { databaseUrl } from '../config.js';

export async function migrationFiles(directory = new URL('../../../migrations/', import.meta.url)) {
  const names = (await readdir(directory)).filter(n => /^\d{3}_[a-z0-9_]+\.sql$/.test(n)).sort();
  if (!names.length) throw new Error('No migrations found');
  return Promise.all(names.map(async name => {
    const body = await readFile(new URL(name, directory), 'utf8');
    return { name, body, checksum: createHash('sha256').update(body).digest('hex') };
  }));
}

export async function migrate(db: Kysely<Database>) {
  const files = await migrationFiles();
  await db.transaction().execute(async trx => {
    await sql`select pg_advisory_xact_lock(1928467, 1001)`.execute(trx);
    await sql`set local search_path = public`.execute(trx);
    // Auth owns this table. Never create or alter it in the application migration.
    await sql`select id, is_active from public.admin_users limit 0`.execute(trx);
    await sql`create table if not exists public.dude_orchestrator_migrations (
      name text primary key, checksum text not null, applied_at timestamptz not null default now()
    )`.execute(trx);
    const applied = await trx.selectFrom('dude_orchestrator_migrations').selectAll().execute();
    for (const row of applied) {
      if (!files.some(f => f.name === row.name && f.checksum === row.checksum)) {
        throw new Error('Migration history mismatch; inspect before continuing');
      }
    }
    // Reject holes rather than applying an older migration after newer ones.
    if (applied.length && files.slice(0, applied.length).some(f => !applied.some(a => a.name === f.name))) {
      throw new Error('Migration order mismatch');
    }
    for (const file of files) {
      if (applied.some(a => a.name === file.name)) continue;
      await sql.raw(file.body).execute(trx);
      await trx.insertInto('dude_orchestrator_migrations').values({ name: file.name, checksum: file.checksum }).execute();
    }
  });
}

export async function ready(db: Kysely<Database>): Promise<boolean> {
  try {
    const files = await migrationFiles();
    const rows = await db.selectFrom('dude_orchestrator_migrations').selectAll().execute();
    await sql`select id, is_active from public.admin_users limit 0`.execute(db);
    return rows.length === files.length && files.every(f => rows.some(r => r.name === f.name && r.checksum === f.checksum));
  } catch { return false; }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  let db: Kysely<Database> | undefined;
  try {
    db = connect(databaseUrl());
    await migrate(db);
    console.log('dude-orchestrator migrations applied');
  } catch {
    console.error('Migration failed. Check database access, admin migrations and migration history. No credentials logged.');
    process.exitCode = 1;
  } finally { await db?.destroy(); }
}
