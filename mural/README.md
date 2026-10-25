# Mural de modelos do CutMind

Página pública onde as pessoas compartilham **modelos de montagem** feitos no CutMind: o ritmo dos
cortes, os textos, as transições e o formato. Quem usa o modelo troca só as fotos, os vídeos e a música.

O mural **nunca recebe mídia**: nem foto, nem vídeo, nem música. A prévia de como a montagem ficou é o
post da própria pessoa (Instagram, TikTok ou YouTube), embutido na página, o que também leva quem vê
até o perfil dela.

É um Cloudflare Worker com banco D1:

| Arquivo | O que faz |
|---|---|
| `src/index.js` | as rotas: grade, página do modelo, publicar, denunciar |
| `src/modelo.js` | confere o modelo como o kit confere (só campos conhecidos, nos mesmos limites) |
| `src/post.js` | lê o link do post e monta o endereço do player a partir do código dele |
| `src/html.js` | as páginas, a política de segurança (CSP) e a capa do ritmo |
| `src/admin.js` | o painel do dono: tirar, devolver e editar modelos |
| `public/static/` | CSS e JS das páginas (nada de script ou estilo em linha) |
| `migrations/` | as tabelas do banco |

## Proteções

- **Publicação direta, com denúncia.** Qualquer modelo publicado aparece na hora; cada pessoa denuncia
  um modelo uma vez, e o painel mostra os denunciados primeiro.
- **Anti-robô:** Cloudflare Turnstile na publicação, conferido no servidor.
- **Limites:** rajada por minuto (binding de rate limiting) e teto por dia contado no banco.
- **Sem IP guardado:** o banco guarda só o SHA-256 do IP com um sal secreto.
- **Só links conhecidos:** o mural aceita post do Instagram, do TikTok e do YouTube em formato
  conhecido e remonta os endereços; nunca devolve o texto colado.
- **Painel do dono** atrás do Cloudflare Access, e o Worker confere o token do Access de novo antes de
  qualquer ação (assinatura, emissor, público e e-mail na lista).

## Rodar no computador

```bash
npm install
cp .dev.vars.example .dev.vars        # valores de TESTE (o Turnstile que sempre passa)
npm run banco:local                   # cria as tabelas no banco local
npm run dev                           # http://127.0.0.1:8787
```

No teste local o painel abre em `http://127.0.0.1:8787/admin` sem login (`ADMIN_LOCAL=1`, que só vale
para `127.0.0.1` e `localhost` e é ignorado quando o Access está configurado).

Para publicar um modelo pelo navegador, abra `/publicar#m=<modelo em base64url>`: é o endereço que o
botão Compartilhar do editor monta.

## Testes

```bash
npm test
```

Rodam dentro do runtime dos Workers (Miniflare), com o banco local e a rede falsa para o Turnstile e
para as chaves do Access.

## Publicar na Cloudflare

Nada de conta, domínio ou segredo entra neste repositório. Para publicar:

1. Crie o banco: `npx wrangler d1 create cutmind-mural`.
2. Copie `wrangler.jsonc` para **fora do repositório** (por exemplo `../mural-producao.jsonc`) e, na
   cópia, troque o `database_id`, a `TURNSTILE_SITEKEY` pela chave real, e preencha `TEAM_DOMAIN`
   (`https://<equipe>.cloudflareaccess.com`), `POLICY_AUD` e `ADMIN_EMAILS`. Se for usar domínio
   próprio, acrescente as `routes`.
3. Aplique as migrações no banco de verdade:
   `npx wrangler d1 migrations apply cutmind-mural --remote --config ../mural-producao.jsonc`.
4. Guarde os segredos (nunca no arquivo):
   `npx wrangler secret put TURNSTILE_SECRET --config ../mural-producao.jsonc` e o mesmo para `SAL_IP`
   (um texto aleatório longo).
5. Crie no Cloudflare Zero Trust um aplicativo do Access para o caminho `/admin` do mural, com a
   política liberando só o seu e-mail. O `POLICY_AUD` é o "Application Audience (AUD) Tag" dele.
6. `npx wrangler deploy --config ../mural-producao.jsonc`.

`ADMIN_LOCAL` não vai para a produção.
