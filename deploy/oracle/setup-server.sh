#!/usr/bin/env bash
# Provisiona o servidor (Ubuntu 22.04/24.04) para o Meu Condomínio.
# Roda UMA vez, como root (ou com sudo), antes do primeiro deploy.
#
# Uso:
#   sudo bash deploy/oracle/setup-server.sh meucondominio.com.br
#
set -euo pipefail

DOMINIO="${1:-}"
APP_USER="meucond"
APP_DIR="/srv/meu-condominio"
DB_NAME="meucondominio"
DB_USER="meucond"

if [[ -z "$DOMINIO" ]]; then
  echo "Uso: sudo bash $0 <dominio>" >&2
  exit 1
fi

echo "==> Pacotes base"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-dev build-essential \
  libpq-dev postgresql postgresql-contrib curl git unzip ufw \
  debian-keyring debian-archive-keyring apt-transport-https

echo "==> Node 22 (build do Vite)"
if ! command -v node >/dev/null || [[ "$(node -v | cut -d. -f1)" < "v20" ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

echo "==> Caddy (HTTPS automático)"
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -y
  apt-get install -y caddy
fi

echo "==> Usuário da aplicação: ${APP_USER}"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_DIR" --shell /bin/bash "$APP_USER"
fi
mkdir -p "$APP_DIR" /var/log/meu-condominio
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" /var/log/meu-condominio

echo "==> PostgreSQL"
systemctl enable --now postgresql
DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\gexec
SQL

echo "==> Firewall"
ufw allow OpenSSH >/dev/null || true
ufw allow 80/tcp >/dev/null || true
ufw allow 443/tcp >/dev/null || true
ufw --force enable >/dev/null || true

echo "==> systemd + Caddy"
install -m 644 "$(dirname "$0")/meu-condominio.service" /etc/systemd/system/meu-condominio.service
sed "s|__DOMINIO__|${DOMINIO}|g; s|__APP_DIR__|${APP_DIR}|g" \
  "$(dirname "$0")/Caddyfile" > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable meu-condominio
systemctl reload-or-restart caddy

echo "==> Backup diário (03:10)"
install -m 755 "$(dirname "$0")/backup.sh" "${APP_DIR}/backup.sh"
( crontab -u "$APP_USER" -l 2>/dev/null | grep -v 'meu-condominio/backup.sh' || true
  echo "10 3 * * * ${APP_DIR}/backup.sh >> /var/log/meu-condominio/backup.log 2>&1" ) \
  | crontab -u "$APP_USER" -

echo
echo "==> Pronto. Configure o .env e faça o primeiro deploy:"
echo "  1. sudo -u ${APP_USER} cp ${APP_DIR}/.env.production ${APP_DIR}/.env  (e edite)"
echo "  2. DATABASE_URL=postgres://${DB_USER}:${DB_PASS}@127.0.0.1:5432/${DB_NAME}"
echo "  3. sudo -u ${APP_USER} bash ${APP_DIR}/deploy/oracle/deploy.sh"
echo
echo "Guarde a senha do banco (não será exibida novamente): ${DB_PASS}"
