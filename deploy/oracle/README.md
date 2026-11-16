# Deploy do Meu Condomínio na Oracle Cloud (Always Free)

Kit para rodar o Django no mesmo servidor dos agentes Hermes ou em instância própria.
Stack: Ubuntu 24.04 (ARM) + Postgres 16 + gunicorn + Caddy (HTTPS automático) + systemd.

## Arquivos

| Arquivo | Função |
|---|---|
| `setup-server.sh` | provisiona pacotes, usuário, Postgres, Caddy, systemd e cron de backup |
| `deploy.sh` | git pull, venv, pip, Vite build, check, migrate, collectstatic, restart |
| `meu-condominio.service` | unit do gunicorn (127.0.0.1:8000, 3 workers, 2 threads) |
| `Caddyfile` | reverse proxy + `/media` + `/static` + HSTS |
| `backup.sh` | `pg_dump` + tar de `media`, retenção de 14 dias |
| `env.production.example` | variáveis de produção |

## 1. Criar a instância

1. Oracle Cloud → Compute → Instances → **Create instance**.
2. Image: **Ubuntu 24.04** (aarch64).
3. Shape: **VM.Standard.A1.Flex** — 2 OCPU / 12 GB já sobra (limite free: 4 OCPU / 24 GB).
4. Baixe a chave SSH (`.key`) e guarde.
5. Depois de criada: VCN → Security List → **Ingress**: TCP 80 e 443 de `0.0.0.0/0`.

Opcional (Ubuntu na Oracle já vem com `iptables` restritivo): liberar 80/443 dentro da VM.

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 2. DNS

No registrador (ou na HostGator, se o domínio está lá): registro **A** `@` → IP público da instância, e `www` → mesmo IP.

## 3. Enviar o código

```bash
ssh -i chave.key ubuntu@IP
sudo apt-get update -y && sudo apt-get install -y git
sudo git clone https://github.com/SEU_USUARIO/Meu_Condominio.git /srv/meu-condominio
sudo chown -R ubuntu:ubuntu /srv/meu-condominio
```

> Se o repositório for privado, use um Deploy Key (Settings → Deploy keys) ou um PAT só de leitura.

## 4. Provisionar

```bash
cd /srv/meu-condominio
sudo bash deploy/oracle/setup-server.sh meucondominio.com.br
```

O script imprime a senha do Postgres **uma vez**. Guarde.

## 5. Configurar o .env

```bash
cd /srv/meu-condominio
sudo -u meucond cp deploy/oracle/env.production.example .env
sudo -u meucond nano .env      # SECRET_KEY, DATABASE_URL, ADMIN_URL, superusuário
sudo chmod 600 .env
sudo chown meucond:meucond .env
```

Gerar chaves:

```bash
openssl rand -hex 32   # SECRET_KEY
openssl rand -base64 24 | tr -d '/+=' | head -c 24   # senha do banco, se preferir trocar
```

## 6. Primeiro deploy

```bash
cd /srv/meu-condominio
sudo -u meucond bash deploy/oracle/deploy.sh
```

## 7. Verificar

```bash
systemctl status meu-condominio --no-pager
journalctl -u meu-condominio -n 50 --no-pager
tail -f /var/log/meu-condominio/app.log
curl -I https://meucondominio.com.br
```

## 8. Atualizações

```bash
cd /srv/meu-condominio
sudo -u meucond bash deploy/oracle/deploy.sh
```

## 9. Migrar dados do Render/Neon (quando for a hora)

```bash
# no seu PC, com a DATABASE_URL antiga
pg_dump "postgres://...neon.tech/db?sslmode=require" -Fc -f condominio.dump
scp -i chave.key condominio.dump ubuntu@IP:/tmp/

# no servidor
sudo -u meucond pg_restore --no-owner --no-acl -d meucondominio /tmp/condominio.dump

# mídia (comprovantes): baixar do Render e copiar para /srv/meu-condominio/media
```

Depois de migrar, rode `python manage.py migrate` e `collectstatic` novamente.

## Notas

- Webhook do Pix (AbacatePay) exige HTTPS público: o Caddy resolve. A URL por condomínio continua sendo `https://SEU_DOMINIO/pagamentos/webhook/<slug>/<token>/`.
- `createcachetable` já roda no `deploy.sh` (o projeto usa `DatabaseCache` em produção).
- 3 workers atendem bem um condomínio; para vários, suba para 5 e monitore RAM.
- Não abra a porta 8000 no firewall: o gunicorn escuta só em 127.0.0.1.
