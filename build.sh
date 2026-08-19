#!/usr/bin/env bash
set -e

uv sync --frozen

uv run python manage.py collectstatic --noinput --settings=config.settings.production
uv run python manage.py migrate --noinput --settings=config.settings.production