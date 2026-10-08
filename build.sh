#!/usr/bin/env bash
# Build script for Render (and any similar host). Runs on every deploy.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ -n "$ADMIN_EMAIL" ]; then python manage.py create_admin "$ADMIN_EMAIL"; fi
