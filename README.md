# Meu Condomínio

SaaS multi-condomínio para reserva de espaços: agenda no celular, Pix com comprovante, análise do síndico e confirmação com check-in.

**Status:** Fase 2 em andamento — Fase 1 concluída (reservas, Pix manual, painel), onboarding self-service com trial de 14 dias, painel da plataforma, comprovantes em storage privado e agora Pix dinâmico com AbacatePay por condomínio.

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
- Configuração por condomínio com prazos padrão de 48 h (antecedência) e 24 h (análise), além do interruptor do Pix automático.
- Landing page e prévia da agenda em mobile-first, com a paleta Lagoa.
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
```

O CI roda os mesmos passos, além de `npm ci` e `npm run build`.

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
| `VITE_DEV_SERVER` | servidor do Vite em desenvolvimento |

No Neon, use o host com `-pooler` e mantenha `DB_DISABLE_SERVER_SIDE_CURSORS=True` (padrão).

## Deploy (Render + Neon)

1. Crie o banco no Neon e copie a URL com `-pooler` e `sslmode=require`.
2. Crie um Web Service no Render apontando para este repositório.
3. Configure `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` e `SECRET_KEY`.
4. O `render.yaml` já define build (`./build.sh`), migrações e `gunicorn`.

O plano free do Render hiberna; o primeiro acesso após inatividade pode demorar.

## Próximas fases

1. Conciliação diária de cobranças Pix (consulta à API) para eventos perdidos.
2. Pix dinâmico com Asaas atrás do mesmo interruptor.
3. OCR de comprovante com Tesseract, regras de validação e fila de revisão.
4. Notificações push PWA, Telegram ativo por padrão no painel e link de WhatsApp ao morador.
5. Bloqueios por inadimplência, políticas automáticas, relatórios e assinatura do SaaS.

## Segurança

- Nunca comite `.env`, credenciais de gateway ou comprovantes reais.
- Credenciais de gateway ficam criptografadas no banco (Fernet) e nunca são exibidas de volta.
- O webhook do Pix confere o segredo por condomínio e a assinatura HMAC-SHA256 do corpo bruto antes de confirmar qualquer reserva.
- Comprovantes devem ir para armazenamento privado em produção, com URL assinada.
- O repositório permanece público durante o desenvolvimento; antes do lançamento comercial, torne-o privado e ative branch protection.
