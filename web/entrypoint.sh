#!/bin/sh
# Entrypoint del contenedor chat-web: aplica migraciones, recolecta
# estáticos y arranca el comando pasado (Daphne por defecto, ver
# compose.yaml). chat-worker usa este mismo Dockerfile pero con
# `command: celery ...`, que también pasa por acá — migrate/collectstatic
# son idempotentes así que no hay problema en correrlos también ahí.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
