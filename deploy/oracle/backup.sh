#!/usr/bin/env bash
# Backup diário: banco (pg_dump) + uploads (media).
# Instalado pelo setup-server.sh no crontab do usuário da aplicação.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${APP_DIR}/backups"
RETENCAO_DIAS=14

mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"

# Banco: usa a DATABASE_URL do .env
set -a; source "${APP_DIR}/.env"; set +a
if [[ "${DATABASE_URL:-}" == postgres* ]]; then
  pg_dump "$DATABASE_URL" --no-owner --no-acl -Fc -f "${DEST}/db-${STAMP}.dump"
fi

# Uploads (comprovantes)
if [[ -d "${APP_DIR}/media" ]]; then
  tar -czf "${DEST}/media-${STAMP}.tar.gz" -C "${APP_DIR}" media
fi

# Limpeza
find "$DEST" -type f -mtime +${RETENCAO_DIAS} -name 'db-*.dump' -delete
find "$DEST" -type f -mtime +${RETENCAO_DIAS} -name 'media-*.tar.gz' -delete

echo "[$(date -Is)] backup ok: ${DEST}"
