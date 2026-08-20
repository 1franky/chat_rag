#!/bin/sh
# Entrypoint del contenedor chat-web: aplica migraciones y arranca el
# comando pasado (Daphne por defecto, ver compose.yaml). chat-worker usa
# este mismo Dockerfile pero con `command: celery ...`, que también pasa
# por acá — migrate es idempotente así que no hay problema en correrlo
# también ahí.
#
# collectstatic NO va acá: corre en build time (ver Dockerfile), porque
# con read_only: true el filesystem del contenedor no admite escritura en
# runtime salvo en los bind mounts explícitos (/data/sqlite, /data/media).
set -e

python manage.py migrate --noinput

exec "$@"
