#!/bin/bash
# Instala (o actualiza) la entrada de crontab para el backup diario de
# chat_rag (plan.md, Fase 7). Idempotente: si ya existe una línea para
# backup.sh en el crontab del usuario actual, la reemplaza en vez de
# duplicarla.
#
# Uso: scripts/install_cron.sh [HH:MM]
#   (default: 03:00)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIME="${1:-03:00}"
HOUR="${TIME%%:*}"
MINUTE="${TIME##*:}"
LOG_FILE="$REPO_DIR/backups/cron.log"
MARKER="# chat_rag backup diario (scripts/install_cron.sh)"

mkdir -p "$REPO_DIR/backups"

CRON_LINE="$MINUTE $HOUR * * * $REPO_DIR/scripts/backup.sh >> $LOG_FILE 2>&1 $MARKER"

# Saca cualquier línea anterior con el mismo marcador y agrega la nueva —
# así correr esto dos veces (o con otro horario) no deja duplicados.
# `|| true` en el grep: con crontab vacío (primera vez, caso común) no hay
# ninguna línea que imprimir y grep -v sale con exit 1 — bajo `set -e` eso
# aborta el subshell entero antes de llegar al `echo`.
(crontab -l 2>/dev/null | grep -vF "$MARKER" || true; echo "$CRON_LINE") | crontab -

echo "Cron instalado: todos los días a las $TIME corre $REPO_DIR/scripts/backup.sh"
echo "Logs en: $LOG_FILE"
echo
echo "Crontab actual:"
crontab -l
