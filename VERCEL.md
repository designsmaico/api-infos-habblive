# Consulta automática com conta dedicada

## Pacote com configuração privada

O pacote configurado inclui `.env.vercel.local`, com a conta dedicada fornecida pelo usuário e uma chave de integração gerada para este projeto. Esse arquivo é ignorado pelo Git. No painel da Vercel, importe as variáveis desse arquivo (ou preencha as três variáveis manualmente) e faça um novo deploy. Apenas enviar o arquivo no repositório não configura as variáveis do projeto. Mantenha este pacote privado e não coloque o arquivo em pastas públicas do site. Quando mudar a senha no Habblive, atualize `HABBLIVE_PASSWORD` na Vercel e publique novamente.

## Configurar na Vercel

1. Suba o conteúdo desta pasta em um repositório privado, sem arquivos `.env` nem credenciais.
2. Importe na Vercel. Use Framework Preset **Other**, com esta pasta como Root Directory. Não é necessário comando de build ou instalação.
3. Em Settings → Environment Variables, configure `HABBLIVE_USERNAME`, `HABBLIVE_PASSWORD` e `INTEGRATION_API_KEY`. Use a conta dedicada e uma chave longa, aleatória, criada por você para proteger a integração. Não use prefixos que exponham variáveis ao navegador.
4. Faça o deploy. A função é `GET /api/perfil?user=Michael&badge_page=1`.

Não forneça cookies. O serviço tenta primeiro uma consulta sem autenticação; quando recebe o formulário de login, envia o formulário normal usando a conta configurada. Cookies e eventuais campos ocultos são gerenciados internamente, somente na memória do servidor. Não são retornados, gravados em disco ou registrados pela aplicação.

## Integração no backend do seu site

```js
// Executar SOMENTE no servidor do seu site.
const url = new URL('/api/perfil', process.env.HABBLIVE_API_URL);
url.searchParams.set('user', 'Michael');
url.searchParams.set('badge_page', '1');
const response = await fetch(url, {
  headers: { Authorization: `Bearer ${process.env.INTEGRATION_API_KEY}` },
  cache: 'no-store'
});
const resultado = await response.json();
if (!response.ok) throw new Error(resultado.error);
// Retorne ao frontend apenas os campos que o site deve exibir.
```

`HABBLIVE_API_URL` é a URL do seu projeto Vercel, por exemplo `https://seu-projeto.vercel.app`. O frontend chama seu próprio backend. Não coloque a chave de integração nem a senha do Habblive em JavaScript público. A rota do seu site deve impor limites de uso adequados ao público que você escolher.

## Limites e comportamento

- O login é feito por HTTP normal, sem navegador persistente. Isso permite tentar executar na Vercel sem VPS. Compatibilidade efetiva depende de o Habblive aceitar esse fluxo a partir da hospedagem.
- Cada instância mantém sua sessão e até 64 resultados por até 60 segundos. Reinícios e instâncias adicionais exigem novos logins; o cache e o intervalo entre tentativas não são globais. Comece com pouco tráfego e limite as chamadas na borda da hospedagem.
- Não é feito login a cada consulta na mesma instância. A sessão em memória é renovada após 15 minutos ou quando a página exige login novamente. Uma falha impõe intervalo de 60 segundos nessa instância.
- CAPTCHA, Cloudflare ou verificação adicional fazem a API parar com erro. Não há tentativa de resolver ou contornar esses desafios. `INTERACTIVE_VERIFICATION_REQUIRED` ou `UPSTREAM_BLOCKED_OR_RATE_LIMITED` podem exigir outra forma de integração.
- `badge_page` vai de 1 a 100. Cada chamada retorna somente os emblemas da página solicitada, com links de paginação em `pagination.other_pages`. Não apresenta a primeira página como coleção completa.
- Datas e campos vêm do perfil retornado. A API impede que uma resposta com outro nome seja apresentada como se fosse o usuário pedido.
- Esta função consulta perfis com as permissões da conta dedicada. Ela não elimina a exigência de autenticação do Habblive e não prova que esses dados sejam públicos sem login.

## Diagnóstico seguro

`401 UNAUTHORIZED`: chave da integração ausente ou incorreta.

`503 HABBLIVE_CREDENTIALS_NOT_CONFIGURED`: usuário ou senha não configurados.

`503 HABBLIVE_LOGIN_FAILED`: o site devolveu o formulário depois da tentativa; confira as variáveis diretamente no painel.

`503 LOGIN_COOLDOWN`: aguarde antes de tentar novamente.

`502 LOGIN_FORM_CHANGED`: a estrutura do formulário mudou.

`502 PROFILE_NOT_FOUND_OR_PAGE_CHANGED`: perfil não encontrado ou HTML diferente do esperado.

## Validação realizada

O formulário público foi inspecionado: POST na página inicial, com `username` e `password`. O parser foi testado com HTML real fornecido pelo usuário. Os 10 testes locais passaram. Além disso, o login real da conta dedicada e a consulta do próprio perfil funcionaram a partir deste computador, sem registrar senha ou cookies. O deploy e a consulta a partir da Vercel ainda não foram testados. Não existe garantia de que o Habblive aceite requisições de IPs da Vercel.

Documentação de hospedagem: https://vercel.com/docs/functions/runtimes/python/api-directory
