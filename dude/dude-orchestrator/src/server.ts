import { config } from './config.js';
import { connect } from './db/database.js';
import { ready } from './db/migrate.js';
import { buildApp } from './app.js';

async function main() {
  const settings = config();
  const db = connect(settings.databaseUrl);
  const app = buildApp(db, settings.secret);
  app.addHook('onClose', () => db.destroy());
  try {
    if (!(await ready(db))) throw new Error('database_not_ready');
    await app.listen({ port: settings.port, host: settings.host });
  } catch {
    await app.close();
    throw new Error('startup_failed');
  }
  const stop = () => { void app.close().catch(() => { process.exitCode = 1; }); };
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
}
main().catch(() => {
  console.error('dude-orchestrator startup failed: check explicit database URL, JWT_SECRET, migrations and port.');
  process.exitCode = 1;
});
