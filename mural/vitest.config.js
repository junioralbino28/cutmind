// Os testes rodam dentro do runtime dos Workers (Miniflare), com o banco D1 local criado pelas
// migrações. Os segredos aqui são de TESTE: o do Turnstile é o que sempre passa e o sal é qualquer um.
import path from 'node:path';
import { cloudflareTest, readD1Migrations } from '@cloudflare/vitest-plugin';
import { defineConfig } from 'vitest/config';

export default defineConfig(async () => {
  const migrations = await readD1Migrations(path.join(import.meta.dirname, 'migrations'));
  return {
    plugins: [
      cloudflareTest({
        wrangler: { configPath: './wrangler.jsonc' },
        miniflare: {
          bindings: {
            TEST_MIGRATIONS: migrations,
            TURNSTILE_SECRET: '1x0000000000000000000000000000000AA',
            SAL_IP: 'sal-dos-testes',
            ADMIN_LOCAL: '1',
            PUBLICAR_POR_DIA: '2',
          },
        },
      }),
    ],
    test: { setupFiles: ['./test/migracoes.js'] },
  };
});
