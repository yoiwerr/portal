import { randomUUID } from 'node:crypto';
import type { Kysely } from 'kysely';
import { z } from 'zod';
import { briefSchema, canGenerate, emptyBrief, wikiSchema, type Brief, type WikiReference } from './brief.js';
import type { Database } from './db/database.js';
import { DomainError } from './errors.js';

const documentsSchema = z.object({
  technical_plan: z.string().trim().min(1).max(200000),
  demo_guide: z.string().trim().min(1).max(200000),
}).strict();
const keySchema = z.string().trim().min(1).max(128);
const revisionSchema = z.number().int().positive();
const failureSchema = z.enum(['model_error', 'invalid_output', 'cancelled', 'interrupted']);

/** Owner IDs originate from verified auth or a trusted worker, never request content. */
export class Repository {
  constructor(private readonly db: Kysely<Database>) {}

  private async project(db: Kysely<Database>, owner: string, id: string, lock = false) {
    let q = db.selectFrom('dude_projects').selectAll().where('id', '=', id).where('owner_id', '=', owner);
    if (lock) q = q.forUpdate();
    const row = await q.executeTakeFirst();
    if (!row) throw new DomainError('project_not_found', 404);
    return row;
  }

  async create(owner: string, title: string) {
    const safeTitle = z.string().trim().min(1).max(120).parse(title);
    return this.db.transaction().execute(async trx => {
      const project = await trx.insertInto('dude_projects').values({ id: randomUUID(), owner_id: owner, title: safeTitle })
        .returningAll().executeTakeFirstOrThrow();
      await trx.insertInto('dude_brief_drafts').values({ project_id: project.id, revision: 1, content: emptyBrief() }).execute();
      return project;
    });
  }

  list(owner: string, limit = 30, offset = 0) {
    return this.db.selectFrom('dude_projects').selectAll().where('owner_id', '=', owner)
      .orderBy('created_at', 'desc').orderBy('id', 'desc').limit(limit).offset(offset).execute();
  }

  async detail(owner: string, id: string) {
    // One statement keeps ownership and draft read in a single snapshot.
    const row = await this.db.selectFrom('dude_projects as p')
      .innerJoin('dude_brief_drafts as d', 'd.project_id', 'p.id')
      .select(['p.id', 'p.title', 'p.created_at', 'd.revision', 'd.content', 'd.updated_at'])
      .where('p.id', '=', id).where('p.owner_id', '=', owner).executeTakeFirst();
    if (!row) throw new DomainError('project_not_found', 404);
    return row;
  }

  async remove(owner: string, id: string) {
    const result = await this.db.deleteFrom('dude_projects').where('id', '=', id).where('owner_id', '=', owner).executeTakeFirst();
    if (result.numDeletedRows === 0n) throw new DomainError('project_not_found', 404);
  }

  // Internal coordinator API only: no HTTP route for raw Brief writes.
  async updateDraft(owner: string, id: string, expectedRevision: number, content: Brief) {
    const safe = briefSchema.parse(content);
    revisionSchema.parse(expectedRevision);
    return this.db.transaction().execute(async trx => {
      await this.project(trx, owner, id, true);
      const row = await trx.updateTable('dude_brief_drafts').set({ content: safe, revision: expectedRevision + 1, updated_at: new Date() })
        .where('project_id', '=', id).where('revision', '=', expectedRevision).returningAll().executeTakeFirst();
      if (!row) throw new DomainError('draft_conflict', 409);
      return row;
    });
  }

  // Call only on explicit user generation. Pi/runtime wiring comes in the next slice.
  async startGeneration(owner: string, id: string, expectedRevision: number, key: string, wiki: WikiReference) {
    const safeKey = keySchema.parse(key);
    const safeWiki = wikiSchema.parse(wiki);
    revisionSchema.parse(expectedRevision);
    return this.db.transaction().execute(async trx => {
      await this.project(trx, owner, id, true);
      const existing = await trx.selectFrom('dude_generation_runs as r')
        .innerJoin('dude_brief_versions as v', 'v.id', 'r.brief_version_id')
        .selectAll('r').select(['v.draft_revision', 'v.wiki'])
        .where('r.project_id', '=', id).where('r.idempotency_key', '=', safeKey).executeTakeFirst();
      if (existing) {
        if (existing.draft_revision !== expectedRevision || JSON.stringify(wikiSchema.parse(existing.wiki)) !== JSON.stringify(safeWiki)) {
          throw new DomainError('idempotency_conflict', 409);
        }
        return existing;
      }
      const active = await trx.selectFrom('dude_generation_runs').select('id').where('project_id', '=', id)
        .where('status', '=', 'running').executeTakeFirst();
      if (active) throw new DomainError('generation_in_progress', 409);
      const draft = await trx.selectFrom('dude_brief_drafts').selectAll().where('project_id', '=', id).executeTakeFirstOrThrow();
      if (draft.revision !== expectedRevision) throw new DomainError('draft_conflict', 409);
      const content = briefSchema.parse(draft.content);
      if (!canGenerate(content)) throw new DomainError('demo_not_ready', 409);
      const last = await trx.selectFrom('dude_brief_versions').select('version').where('project_id', '=', id)
        .orderBy('version', 'desc').executeTakeFirst();
      const versionId = randomUUID();
      await trx.insertInto('dude_brief_versions').values({
        id: versionId, project_id: id, version: (last?.version || 0) + 1,
        draft_revision: expectedRevision, schema_version: content.schema_version, content, wiki: safeWiki,
      }).execute();
      return trx.insertInto('dude_generation_runs').values({
        id: randomUUID(), project_id: id, brief_version_id: versionId, idempotency_key: safeKey,
        status: 'running', error_code: null, finished_at: null,
      }).returningAll().executeTakeFirstOrThrow();
    });
  }

  async completeGeneration(owner: string, projectId: string, runId: string, documents: z.infer<typeof documentsSchema>) {
    const pair = documentsSchema.parse(documents);
    return this.db.transaction().execute(async trx => {
      await this.project(trx, owner, projectId, true);
      const run = await trx.selectFrom('dude_generation_runs').selectAll()
        .where('id', '=', runId).where('project_id', '=', projectId).forUpdate().executeTakeFirst();
      if (!run) throw new DomainError('run_not_found', 404);
      if (run.status === 'succeeded') {
        const prior = await trx.selectFrom('dude_artifact_versions').selectAll().where('run_id', '=', run.id).executeTakeFirstOrThrow();
        if (prior.technical_plan !== pair.technical_plan || prior.demo_guide !== pair.demo_guide) {
          throw new DomainError('delivery_conflict', 409);
        }
        return prior;
      }
      if (run.status !== 'running') throw new DomainError('run_finished', 409);
      await trx.updateTable('dude_generation_runs').set({ status: 'succeeded', finished_at: new Date() })
        .where('id', '=', run.id).execute();
      return trx.insertInto('dude_artifact_versions').values({
        id: randomUUID(), project_id: projectId, brief_version_id: run.brief_version_id, run_id: run.id, ...pair,
      }).returningAll().executeTakeFirstOrThrow();
    });
  }

  async failGeneration(owner: string, projectId: string, runId: string, reason: z.infer<typeof failureSchema>) {
    const safe = failureSchema.parse(reason);
    return this.db.transaction().execute(async trx => {
      await this.project(trx, owner, projectId, true);
      const run = await trx.selectFrom('dude_generation_runs').selectAll().where('id', '=', runId)
        .where('project_id', '=', projectId).forUpdate().executeTakeFirst();
      if (!run) throw new DomainError('run_not_found', 404);
      if (run.status === 'failed' && run.error_code === safe) return;
      if (run.status !== 'running') throw new DomainError('run_finished', 409);
      await trx.updateTable('dude_generation_runs').set({ status: 'failed', error_code: safe, finished_at: new Date() })
        .where('id', '=', run.id).execute();
    });
  }

  async versions(owner: string, projectId: string, limit = 30, offset = 0) {
    await this.project(this.db, owner, projectId);
    return this.db.selectFrom('dude_brief_versions as v').innerJoin('dude_projects as p', 'p.id', 'v.project_id')
      .innerJoin('dude_generation_runs as r', join => join.onRef('r.brief_version_id', '=', 'v.id').onRef('r.project_id', '=', 'v.project_id'))
      .select(['v.id', 'v.version', 'v.draft_revision', 'v.wiki', 'v.created_at', 'r.status', 'r.error_code'])
      .where('p.id', '=', projectId).where('p.owner_id', '=', owner)
      .orderBy('v.version', 'desc').limit(limit).offset(offset).execute();
  }

  async version(owner: string, projectId: string, version: number) {
    const row = await this.db.selectFrom('dude_brief_versions as v').innerJoin('dude_projects as p', 'p.id', 'v.project_id')
      .leftJoin('dude_artifact_versions as a', 'a.brief_version_id', 'v.id')
      .selectAll('v').select(['a.technical_plan', 'a.demo_guide'])
      .where('p.id', '=', projectId).where('p.owner_id', '=', owner).where('v.version', '=', version).executeTakeFirst();
    if (!row) throw new DomainError('version_not_found', 404);
    return row;
  }

  async activeUser(id: string): Promise<boolean> {
    const row = await this.db.selectFrom('admin_users').select('id').where('id', '=', id).where('is_active', '=', true).executeTakeFirst();
    return Boolean(row);
  }
}
