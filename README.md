# Meu Condomínio

SaaS multi-condomínio para reserva de espaços: agenda no celular, Pix com comprovante, análise do síndico e confirmação com check-in.

**Status:** reservas com Pix manual e Pix dinâmico (AbacatePay por condomínio), análise do síndico, onboarding self-service com trial de 14 dias, painel da plataforma, comprovantes em armazenamento privado e instalação como aplicativo no celular.

## O que já existe

- Django 5.2 com usuário customizado desde a primeira migração.
- Isolamento multi-tenant por `condominio_id` com `TenantMiddleware`, `TenantManager` e testes de vazamento.
- Modelos: `Condominio`, `ConfiguracaoCondominio`, `Usuario`, `Unidade`, `VinculoUnidade`, `Convite`, `Local` e `Reserva`.
- Login, convite por link com cadastro do morador e vínculo automático à unidade.
- Reserva com antecedência configurável, limite mensal por unidade, hold de 2 horas e bloqueio de conflito.
- Pix manual com BR Code (QR e copia e cola), envio de comprovante e prazo de análise do síndico.
- Painel do síndico com fila de análise, confirmação com código de check-in, recusa com motivo e e-mails automáticos.
- Painel do morador com calendário de papel (seleção de mês) e marcações manuscritas das reservas por dia.
- Onboarding self-service em `/criar/`: condomínio novo, primeira unidade e conta de síndico, com 14 dias de teste.
- Painel da plataforma para o dono do SaaS criar condomínios e acompanhar trial, unidades, espaços e reservas.
- Gestão do condomínio: identidade (logo e cores), CRUD de locais com foto, unidades e convites.
- Comprovantes em storage privado (fora da `MEDIA_URL`), servidos só por view com permissão.
- Pix dinâmico com AbacatePay: cada condomínio usa a própria conta, credenciais criptografadas no banco e webhook idempotente que confirma a reserva na hora.
- Planos por tamanho do condomínio (Essencial, Conforto, Pro e Rede), com sugestão automática pela quantidade de unidades.
- Endurecimento de segurança: rate limit de login, verificação de assinatura real dos comprovantes, cookies `HttpOnly`/`SameSite`, admin em URL configurável e auditoria (bandit + pip-audit) no CI.
- Configuração por condomínio com prazos padrão de 48 h (antecedência) e 24 h (análise), além do interruptor do Pix automático.
- Landing page e agenda em mobile-first, com a paleta Lagoa.
- Tailwind 4 + Vite, fontes self-hosted, Alpine.js, HTMX, Anime.js e Three.js (carregado só em telas grandes).
- Seed de demonstração, testes, lint e CI no GitHub Actions.

## Stack

| Camada | Escolha |
|---|---|
| Backend | Django 5.2, PostgreSQL (Neon) ou SQLite local |
| Frontend | Templates Django, HTMX 2, Alpine.js 3 |
| Estilo | Tailwind CSS 4 + Vite |
| Movimento | Anime.js e Three.js (desktop, com `prefers-reduced-motion`) |
| Deploy | Render + Neon |
| Qualidade | Ruff, testes Django, GitHub Actions |

## Requisitos

- Python 3.12
- Node.js 20+
- Git

## Rodando localmente

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
npm install
npm run build
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

### Linux/macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm install
npm run build
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Acesse:

- Landing: http://127.0.0.1:8000/
- Agenda demo: http://127.0.0.1:8000/c/bela-vista/agenda/
- Admin: http://127.0.0.1:8000/admin/ (crie um superusuário com `python manage.py createsuperuser`)

Se a página não abrir, confirme que o servidor está rodando. No Windows, o atalho é:

```powershell
.\run.ps1
```

O servidor encerra quando o terminal fecha. Ele precisa estar ativo para o navegador acessar
`127.0.0.1:8000`.

### Assets em desenvolvimento

Para editar CSS/JS com recarga automática, rode o Vite em outro terminal:

```bash
npm run dev
```

E defina no `.env`:

```env
VITE_DEV_SERVER=http://localhost:5173
```

Sem o Vite, rode `npm run build` sempre que alterar `assets/`.

## Testes e qualidade

```bash
ruff check .
python manage.py check
python manage.py test
bandit -r apps config -ll -q
pip-audit -r requirements.txt
```

O CI roda os mesmos passos (incluindo `check --deploy`, `bandit` e `pip-audit`), além de `npm ci` e `npm run build`.

## Estrutura

```text
apps/
  core/        condomínio, configuração, tenant, landing e agenda
  usuarios/    usuário, unidade, vínculo e convite
  reservas/    local, reserva, formulários e views do fluxo
  pagamentos/  BR Code Pix (payload EMV + QR), cliente AbacatePay e webhook
assets/        entrada do Vite (CSS/JS, hero 3D)
config/        settings, URLs, WSGI/ASGI
templates/     base, landing, agenda, login, convites, configurações e reservas
static/        arquivos estáticos e build do Vite
```

## Configuração

Variáveis principais (veja `.env.example`):

| Variável | Uso |
|---|---|
| `DEBUG` | `False` em produção |
| `SECRET_KEY` | obrigatória em produção |
| `ALLOWED_HOSTS` | domínios separados por vírgula |
| `DATABASE_URL` | Neon/PostgreSQL; vazio usa SQLite |
| `DB_SSLMODE` | `require` para Neon |
| `CSRF_TRUSTED_ORIGINS` | origem completa do deploy |
| `CHAVE_CRIPTOGRAFIA` | opcional; chave estável para criptografar credenciais de gateway (sem ela, deriva da `SECRET_KEY`) |
| `ADMIN_URL` | caminho do Django admin (padrão `admin/`; use algo difícil de adivinhar em produção) |
| `CONFIAR_NO_PROXY` | usa o IP do `X-Forwarded-For` no rate limit (padrão `True` fora do `DEBUG`) |
| `DJANGO_SUPERUSER_USERNAME` | usuário do superusuário criado no deploy |
| `DJANGO_SUPERUSER_EMAIL` | e-mail do superusuário (opcional) |
| `DJANGO_SUPERUSER_PASSWORD` | senha do superusuário (mínimo 12 caracteres) |
| `VITE_DEV_SERVER` | servidor do Vite em desenvolvimento |

### Superusuário sem código

O deploy roda `python manage.py garantir_superusuario` (em `build.sh` localmente e no `Dockerfile` do Render). Ele lê apenas `DJANGO_SUPERUSER_USERNAME` e `DJANGO_SUPERUSER_PASSWORD` do ambiente: se as variáveis não existirem, não faz nada; se o usuário já existir, não altera a senha. Para redefinir depois, rode `python manage.py garantir_superusuario --atualizar-senha` com a nova senha no ambiente. Nada de usuário ou senha no repositório.

No Neon, use o host com `-pooler` e mantenha `DB_DISABLE_SERVER_SIDE_CURSORS=True` (padrão).

## Deploy (Render)

1. Suba o repositório no GitHub e, no Render, use **New > Blueprint** apontando para ele (o `render.yaml` cria o Web Service e o Postgres free).
2. Configure as variáveis `sync: false` no painel: `ALLOWED_HOSTS` (ex.: `meu-condominio.onrender.com`), `CSRF_TRUSTED_ORIGINS` (ex.: `https://meu-condominio.onrender.com`) e as `DJANGO_SUPERUSER_*`.
3. O `Dockerfile` compila o Vite (Node 20), coleta os estáticos, roda migrações/cache e sobe o `gunicorn`; `RENDER_EXTERNAL_HOSTNAME` já entra em `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` automaticamente.
4. `SECURE_SSL_REDIRECT` fica `False` no blueprint porque o Render encerra o TLS na borda; os cookies continuam `Secure` e o HSTS ativo.

O plano free do Render hiberna; o primeiro acesso após inatividade pode demorar. O disco também é efêmero: logos e comprovantes enviados somem a cada deploy. Para produção real, troque `MEDIA` por S3/R2 (ou um disco persistente pago).

Para rodar exatamente como no Render localmente:

```bash
docker build -t meu-condominio .
docker run --rm -p 8000:8000 --env-file .env meu-condominio
```

## Mídia persistente (Cloudflare R2)

No Render free o disco é efêmero: logos, fotos de espaços e comprovantes somem a cada deploy. O app já suporta qualquer storage S3 (R2 incluso):

1. No Cloudflare, abra **R2** e crie dois buckets: `meu-condominio-media` (leitura pública) e `meu-condominio-privado` (sem acesso público).
2. No bucket público, ative **Public access** (r2.dev) ou conecte um domínio próprio e copie o endereço `pub-xxxx.r2.dev`.
3. Em **Manage R2 API Tokens**, crie um token com **Object Read & Write** nos dois buckets e guarde o Access Key ID e o Secret Access Key.
4. No Render, adicione as variáveis e faça redeploy:

| Variável | Exemplo |
|---|---|
| `STORAGE_S3_BUCKET` | `meu-condominio-media` |
| `STORAGE_S3_PRIVATE_BUCKET` | `meu-condominio-privado` |
| `STORAGE_S3_ACCESS_KEY` | token do R2 |
| `STORAGE_S3_SECRET_KEY` | secret do token |
| `STORAGE_S3_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
| `STORAGE_S3_REGION` | `auto` |
| `STORAGE_S3_PUBLIC_DOMAIN` | `pub-xxxx.r2.dev` |

Com isso, logos e fotos usam o bucket público (`media/`), e comprovantes vão para o bucket privado (`privado/`) com URL assinada. Sem essas variáveis, tudo continua no disco local.

**Cloudinary (opcional, já plugado):** se `CLOUDINARY_CLOUD_NAME` estiver definido e o R2 não estiver, logos e fotos passam a ir para o Cloudinary. A prioridade é **R2 > Cloudinary > disco local**.

1. No dashboard do Cloudinary, copie **Cloud name**, **API Key** e **API Secret**.
2. No Render, defina `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY` e `CLOUDINARY_API_SECRET` e faça redeploy.

Comprovantes continuam no disco local (ou no R2, se configurado), porque o Cloudinary entrega arquivos publicamente e não serve para documentos privados.

## Planos

| Plano | Preço/mês | Unidades | Espaços |
|---|---|---|---|
| Essencial | R$ 29,90 | até 20 | até 3 |
| Conforto | R$ 59,90 | até 50 | até 6 |
| Pro | R$ 99,90 | até 120 | até 12 |
| Rede | R$ 189,90 | ilimitadas | ilimitados |

Os planos ficam no banco (`Plano`), editáveis no admin, e a landing lista só os ativos. O onboarding coloca o condomínio no Essencial; o painel da plataforma mostra o plano atual, o preço e o plano sugerido pela quantidade de unidades.

## Próximas fases

1. Conciliação diária de cobranças Pix (consulta à API) para eventos perdidos.
2. Pix dinâmico com Asaas atrás do mesmo interruptor.
3. OCR de comprovante com Tesseract, regras de validação e fila de revisão.
4. Notificações push PWA, Telegram ativo por padrão no painel e link de WhatsApp ao morador.
5. Bloqueios por inadimplência, políticas automáticas, relatórios e assinatura do SaaS.

## Segurança

- Nunca comite `.env`, credenciais de gateway ou comprovantes reais; o superusuário vem de variáveis de ambiente.
- Credenciais de gateway ficam criptografadas no banco (Fernet) e nunca são exibidas de volta.
- O webhook do Pix confere o segredo por condomínio e a assinatura HMAC-SHA256 do corpo bruto antes de confirmar qualquer reserva, com limite de 64 KB e idempotência.
- Login tem limite de 5 tentativas por IP + usuário em 15 minutos, com cache compartilhado no banco em produção.
- Cookies de sessão e CSRF são `HttpOnly` e `SameSite=Lax`; em produção são `Secure`, com HSTS, `X-Frame-Options: DENY` e `nosniff`.
- Uploads de comprovante checam extensão, MIME declarado, tamanho e assinatura real do arquivo (magic bytes).
- O admin usa `ADMIN_URL` configurável; em produção use um caminho fora do óbvio.
- CI roda `manage.py check --deploy`, `bandit` (médio+) e `pip-audit`, além dos testes.
- Comprovantes devem ir para armazenamento privado em produção, com URL assinada.
- O repositório permanece público durante o desenvolvimento; antes do lançamento comercial, torne-o privado e ative branch protection.
