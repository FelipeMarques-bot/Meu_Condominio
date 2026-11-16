#!/usr/bin/env bash
# Deploy/atualização do Meu Condomínio.
# Roda como o usuário da aplicação (meucond), na raiz do projeto.
#
#   sudo -u meucond bash deploy/oracle/deploy.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$APP_DIR"

echo "==> Código"
if [[ -d .git ]]; then
  git fetch --prune
  git reset --hard origin/main
fi

echo "==> Python"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip wheel
.venv/bin/pip install -r requirements.txt

echo "==> Frontend (Vite)"
if [[ -f package-lock.json ]]; then
  npm ci
  npm run build
fi

echo "==> Django"
set -a; source .env; set +a
.venv/bin/python manage.py check --deploy
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py createcachetable
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py garantir_superusuario

echo "==> Reiniciando serviço"
sudo systemctl restart meu-condominio
sudo systemctl --no-pager --lines=0 status meu-condominio || true

echo "==> Deploy concluído"
