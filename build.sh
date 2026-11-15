#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
npm ci
npm run build
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py createcachetable
python manage.py garantir_superusuario
