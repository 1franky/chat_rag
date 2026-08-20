#!/bin/sh
# Wrapper interactivo de `createsuperuser`. Uso 100% personal: un solo
# superusuario, sin vista de registro (plan.md, sección 2.3).
#
# Uso: ./scripts/create_admin.sh
set -e

cd "$(dirname "$0")/.."

docker compose exec chat-web python manage.py createsuperuser
