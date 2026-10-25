// Roda antes de cada arquivo de teste: cria as tabelas no banco local (só as migrações que faltam).
import { applyD1Migrations } from 'cloudflare:test';
import { env } from 'cloudflare:workers';

await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
