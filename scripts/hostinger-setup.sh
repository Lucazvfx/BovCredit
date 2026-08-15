#!/usr/bin/env bash
# Executa UMA VEZ no VPS Hostinger (Ubuntu 22.04/24.04) como root.
# Instala Docker, clona o repo e sobe o app.
set -euo pipefail

REPO_URL="https://github.com/lucazvfx/bovcredit.git"
APP_DIR="/opt/orkavyn"
DOMAIN="${1:-seudominio.com.br}"

echo "==> Atualizando pacotes"
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl git nginx certbot python3-certbot-nginx

echo "==> Instalando Docker"
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

echo "==> Clonando repositório"
git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

echo "==> Configurando variáveis de ambiente"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "!! EDITE $APP_DIR/.env com os valores reais antes de continuar !!"
  echo "   nano $APP_DIR/.env"
  echo ""
  read -rp "Pressione ENTER após salvar o .env..."
fi

echo "==> Configurando nginx"
DOMAIN_ESCAPED=$(echo "$DOMAIN" | sed 's/\./\\./g')
sed "s/seudominio\.com\.br/$DOMAIN/g" nginx/orkavyn.conf \
  > /etc/nginx/sites-available/orkavyn
ln -sf /etc/nginx/sites-available/orkavyn /etc/nginx/sites-enabled/orkavyn
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "==> Obtendo certificado SSL (Let's Encrypt)"
certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
  --non-interactive --agree-tos --email "$(grep ADMIN_EMAILS .env | cut -d= -f2)"

echo "==> Copiando arquivos estáticos para nginx"
mkdir -p /opt/orkavyn/static
# nginx serve /opt/orkavyn/static — que já é o próprio static/ do repo
ln -sfn "$APP_DIR/static" /opt/orkavyn/static

echo "==> Buildando e subindo containers"
docker compose up -d --build

echo ""
echo "==> Pronto! App rodando em https://$DOMAIN"
echo "    Logs: docker compose -f $APP_DIR/docker-compose.yml logs -f app"
