#!/usr/bin/env bash
# Backup diário do banco. O Supabase no plano Free não guarda backup nenhum —
# se o projeto for apagado ou uma migração estragar dados, não há volta.
#
# Instalar no VPS (uma vez), como root:
#   chmod +x /opt/orkavyn/scripts/backup-banco.sh
#   /opt/orkavyn/scripts/backup-banco.sh            # testa: deve imprimir "ok"
#   (crontab -l 2>/dev/null; echo '0 3 * * * /opt/orkavyn/scripts/backup-banco.sh >> /var/log/orkavyn-backup.log 2>&1') | crontab -
#
# Restaurar:
#   docker run --rm -i -e URL postgres:17-alpine sh -c 'pg_restore --clean --no-owner -d "$URL"' < arquivo.dump
#
# O dump fica no próprio VPS: protege contra erro no banco, não contra perder
# o VPS. Baixe uma cópia de vez em quando (scp).
set -euo pipefail
umask 077

APP_DIR="/opt/orkavyn"
DESTINO="/opt/orkavyn-backups"
DIAS=14

URL="$(grep '^DATABASE_URL=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '"'"'")"
# pg_dump não funciona no pooler em modo transaction (6543); o modo session é
# a 5432 no mesmo host.
export URL="${URL/:6543\//:5432/}"

mkdir -p "$DESTINO"
ARQ="$DESTINO/orkavyn-$(date +%F).dump"
docker run --rm -e URL postgres:17-alpine \
  sh -c 'pg_dump --format=custom --no-owner --schema=public "$URL"' > "$ARQ.tmp"
mv "$ARQ.tmp" "$ARQ"
find "$DESTINO" -name 'orkavyn-*.dump' -mtime +"$DIAS" -delete

echo "$(date -Is) ok $ARQ $(du -h "$ARQ" | cut -f1)"
