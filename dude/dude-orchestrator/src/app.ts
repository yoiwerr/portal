import Fastify, { LogController } from 'fastify';
import { z } from 'zod';
import type { Kysely } from 'kysely';
import type { Database } from './db/database.js';
import { ready } from './db/migrate.js';
import { authenticate } from './auth.js';
import { Repository } from './repository.js';
import { DomainError } from './errors.js';

declare module 'fastify' { interface FastifyRequest { ownerId: string } }

export function buildApp(db: Kysely<Database>, secret: string, logging = true) {
  const app = Fastify({ logger: logging, logController: new LogController({ disableRequestLogging: true }), bodyLimit: 16384, trustProxy: false,
    requestTimeout: 15000, connectionTimeout: 15000 });
  const repository = new Repository(db);
  app.decorateRequest('ownerId', '');
  app.addHook('onSend', async (_request, reply) => {
    reply.header('Cache-Control', 'no-store').header('X-Content-Type-Options', 'nosniff');
  });
  app.addHook('onResponse', async (request, reply) => {
    request.log.info({ requestId: request.id, route: request.routeOptions.url, status: reply.statusCode,
      durationMs: reply.elapsedTime }, 'request completed');
  });
  app.setErrorHandler((error, request, reply) => {
    if (error instanceof DomainError) return reply.code(error.status).send({ error: error.code });
    if (error instanceof z.ZodError) return reply.code(400).send({ error: 'invalid_request' });
    // Fastify's parser/size errors must not become misleading internal errors.
    if (error instanceof Error && 'statusCode' in error && typeof error.statusCode === 'number' && error.statusCode >= 400 && error.statusCode < 500) {
      return reply.code(error.statusCode).send({ error: 'invalid_request' });
    }
    request.log.error({ requestId: request.id, category: 'internal_error' }, 'request failed');
    return reply.code(500).send({ error: 'internal_error' });
  });
  app.get('/health/live', async () => ({ status: 'ok' }));
  app.get('/health/ready', async (_request, reply) => {
    if (!(await ready(db))) return reply.code(503).send({ status: 'unavailable' });
    return { status: 'ready' };
  });

  app.register(async api => {
    api.addHook('onRequest', async request => {
      request.ownerId = await authenticate(request.headers.authorization, secret);
      if (!(await repository.activeUser(request.ownerId))) throw new DomainError('unauthorized', 401);
    });
    const projectParams = z.object({ projectId: z.uuid() });
    const pagination = z.object({
      limit: z.coerce.number().int().min(1).max(100).default(30),
      offset: z.coerce.number().int().min(0).max(1000000).default(0),
    }).strict();
    api.post('/projects', async (request, reply) => {
      const { title } = z.object({ title: z.string().trim().min(1).max(120) }).strict().parse(request.body);
      const project = await repository.create(request.ownerId, title);
      return reply.code(201).send(project);
    });
    api.get('/projects', async request => {
      const { limit, offset } = pagination.parse(request.query);
      return { items: await repository.list(request.ownerId, limit, offset) };
    });
    api.get('/projects/:projectId', async request => {
      const { projectId } = projectParams.parse(request.params);
      return repository.detail(request.ownerId, projectId);
    });
    api.delete('/projects/:projectId', async (request, reply) => {
      const { projectId } = projectParams.parse(request.params);
      await repository.remove(request.ownerId, projectId);
      return reply.code(204).send();
    });
    api.get('/projects/:projectId/versions', async request => {
      const { projectId } = projectParams.parse(request.params);
      const { limit, offset } = pagination.parse(request.query);
      return { items: await repository.versions(request.ownerId, projectId, limit, offset) };
    });
    api.get('/projects/:projectId/versions/:version', async request => {
      const { projectId, version } = projectParams.extend({ version: z.coerce.number().int().positive() }).parse(request.params);
      return repository.version(request.ownerId, projectId, version);
    });
  }, { prefix: '/api/v2' });
  return app;
}
