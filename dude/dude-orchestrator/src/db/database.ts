import { Kysely, PostgresDialect, type Generated, type ColumnType } from 'kysely';
import pg from 'pg';
import type { Brief, WikiReference } from '../brief.js';

type Time = ColumnType<Date, Date | string | undefined, never>;
interface Projects {
  id: string; owner_id: string; title: string; created_at: Time;
}
interface Drafts {
  project_id: string; revision: number; content: Brief;
  updated_at: ColumnType<Date, Date | undefined, Date>;
}
interface Versions {
  id: string; project_id: string; version: number; draft_revision: number;
  schema_version: number; content: Brief; wiki: WikiReference; created_at: Time;
}
interface Runs {
  id: string; project_id: string; brief_version_id: string; idempotency_key: string;
  status: 'running' | 'succeeded' | 'failed'; error_code: string | null;
  created_at: Time; finished_at: Date | null;
}
interface Artifacts {
  id: string; project_id: string; brief_version_id: string; run_id: string;
  technical_plan: string; demo_guide: string; created_at: Time;
}
export interface Database {
  admin_users: { id: string; is_active: boolean; role: string };
  dude_projects: Projects;
  dude_brief_drafts: Drafts;
  dude_brief_versions: Versions;
  dude_generation_runs: Runs;
  dude_artifact_versions: Artifacts;
  dude_orchestrator_migrations: { name: string; checksum: string; applied_at: Generated<Date> };
}

export function connect(connectionString: string) {
  const pool = new pg.Pool({ connectionString, max: 8, connectionTimeoutMillis: 5000,
    statement_timeout: 15000, idle_in_transaction_session_timeout: 15000,
    application_name: 'dude-orchestrator' });
  // Never print a pg error: it may contain a connection string or query values.
  pool.on('error', () => process.stderr.write('dude-orchestrator: database connection error\n'));
  return new Kysely<Database>({ dialect: new PostgresDialect({ pool }) }).withSchema('public');
}
