# Habblive Profile API

Consulta por nome com login automático da conta dedicada em `GET /api/perfil?user=Michael`. Veja [VERCEL.md](VERCEL.md) para subir na Vercel e configurar as três variáveis privadas. O endpoint de parsing descrito abaixo continua disponível na execução local.

API para transformar HTML de perfis Habblive em JSON. Python 3.10 ou superior, sem dependências externas.

## Executar

```sh
python app.py
```

Endereço padrão: `http://127.0.0.1:8000`. Configure `HOST` e `PORT` por variáveis de ambiente. Para hospedagem pública, use um servidor proxy com HTTPS e limites de requisição na frente deste serviço.

## Integrar no site

`POST /v1/profile/parse`, com `Content-Type: application/json`:

```js
// html é o conteúdo de um arquivo de perfil salvo/importado pelo usuário.
const resposta = await fetch('/v1/profile/parse', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ html })
});
const resultado = await resposta.json();
if (!resposta.ok) throw new Error(resultado.message || resultado.error);
console.log(resultado.data);
```

Esse exemplo pressupõe que seu servidor encaminhe `/v1/` para esta API. Se a API estiver em outro domínio, use sua URL completa e configure `CORS_ORIGIN` com a origem exata do site, por exemplo `https://meusite.com`. Aceita várias origens separadas por vírgula, sem espaços. CORS não é autenticação.

Para reunir emblemas de várias páginas do mesmo perfil:

```js
body: JSON.stringify({ pages: [htmlPagina1, htmlPagina2] })
```

Os emblemas são deduplicados por código. Máximo de 20 páginas e 5 MiB por requisição. A API inclui apenas emblemas presentes nos HTMLs enviados; não presume uma lista completa. `pagination.other_pages` contém números das páginas apontadas pelos links encontrados, não páginas faltantes nem total de páginas.

## Resposta

Envelope `{ "data": { ... } }`, contendo `username`, `id`, `motto`, `created_at`, `last_login`, `achievement_score`, `pixels`, `diamonds`, `duckets`, `gems`, `games`, `promo_coins`, `slices`, `promotion_points`, `event_points`, `avatar_url`, `figure`, `badges`, `pagination`, `pages_parsed` e `badges_scope`.

Campos ausentes no HTML não são inventados. Datas permanecem no formato original do Habblive, pois o fuso não foi confirmado. As URLs de imagens retornadas são limitadas aos serviços observados. Exiba strings como texto no site, sem inseri-las com `innerHTML`.

`GET /health` retorna `{ "status": "ok" }`. Erros: `404` rota inexistente, `413` corpo vazio ou acima do limite, `415` tipo incorreto e `422` JSON/HTML inválido ou páginas de usuários diferentes.

## Escopo de acesso

O endpoint `/v1/profile/parse` funciona com HTML salvo e não faz login nem executa scripts do HTML. O endpoint `/api/perfil` usa a conta dedicada configurada pelo operador e gerencia sua sessão apenas em memória, conforme VERCEL.md. Não envie cookies, tokens ou arquivos HAR. O serviço não guarda HTML e não registra corpos nem cabeçalhos; configure o mesmo cuidado no seu proxy.

## Testes

```sh
python -m unittest -v
```
