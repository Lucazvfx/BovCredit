#!/usr/bin/env bash
# Executa UMA VEZ no VPS Hostinger (Ubuntu 22.04/24.04) como root.
# Instala Docker, clona o repo e sobe o app.
#
#   ./hostinger-setup.sh credito.orkavyn.tech [branch]
#
# O domínio precisa ter registro A apontando para o IP deste servidor ANTES
# de rodar — o certbot valida por HTTP e falha se o DNS não resolver aqui.
set -euo pipefail

REPO_URL="https://github.com/lucazvfx/bovcredit.git"
APP_DIR="/opt/orkavyn"
DOMAIN="${1:-}"
BRANCH="${2:-main}"

if [ -z "$DOMAIN" ]; then
  echo "Uso: $0 <dominio> [branch]" >&2
  echo "Ex.: $0 credito.orkavyn.tech main" >&2
  exit 1
fi

# Este VPS pode já servir outros sites. Nada aqui remove ou substitui
# configuração existente: instala só o que falta, adiciona um server block
# novo e não toca no default.
if [ -e "$APP_DIR" ]; then
  echo "$APP_DIR já existe — este script é só para a primeira instalação." >&2
  echo "Para atualizar:  cd $APP_DIR && git pull && docker compose up -d --build" >&2
  exit 1
fi

echo "==> Atualizando pacotes"
apt-get update -qq
apt-get install -y --no-install-recommends curl git certbot python3-certbot-nginx
command -v nginx >/dev/null || apt-get install -y --no-install-recommends nginx

echo "==> Instalando Docker"
if command -v docker >/dev/null; then
  echo "    já instalado, pulando"
else
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

echo "==> Clonando repositório (branch $BRANCH)"
git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
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

# ── nginx em HTTP primeiro ───────────────────────────────────────────────────
# O certbot --nginx precisa de um server block VÁLIDO e servindo na porta 80
# para resolver o desafio. Só depois ele injeta o TLS neste mesmo bloco.
echo "==> Configurando nginx (HTTP)"
sed "s/seudominio\.com\.br/$DOMAIN/g" nginx/orkavyn.conf \
  > /etc/nginx/sites-available/orkavyn
ln -sf /etc/nginx/sites-available/orkavyn /etc/nginx/sites-enabled/orkavyn
# O site default NÃO é removido. A versão anterior o apagava, o que numa
# máquina nova era inofensivo e aqui derrubaria o que já está no ar. nginx
# casa por server_name antes de cair no default_server, então o bloco novo
# convive com os existentes sem disputar nada.
mkdir -p /var/www/certbot
nginx -t && systemctl reload nginx

# ── App no ar antes do TLS ───────────────────────────────────────────────────
# Sobe aqui, e não no fim, para o proxy_pass ter destino quando o certbot
# recarregar o nginx.
echo "==> Buildando e subindo containers"
docker compose up -d --build

echo "==> Obtendo certificado SSL (Let's Encrypt)"
# Só o domínio pedido. A versão anterior somava "-d www.$DOMAIN" — num
# subdomínio como credito.orkavyn.tech esse nome não tem registro DNS, e o
# certbot é all-or-nothing: um nome que não valida derruba o certificado
# inteiro. Para incluir www, passe o domínio raiz e crie o registro antes.
CERT_EMAIL="$(grep '^ADMIN_EMAILS=' .env | cut -d= -f2- | cut -d, -f1 | tr -d ' \"')"
certbot --nginx -d "$DOMAIN" \
  --non-interactive --agree-tos --redirect --email "$CERT_EMAIL"

echo ""
echo "==> Pronto! App rodando em https://$DOMAIN"
echo "    Confirme o usuário não-root: docker compose -f $APP_DIR/docker-compose.yml exec app id"
echo "    Logs: docker compose -f $APP_DIR/docker-compose.yml logs -f app"
