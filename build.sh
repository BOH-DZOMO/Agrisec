#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. Install uv into Render's system environment
curl -LsSf https://astral.sh | sh
source $HOME/.local/bin/env

# 2. Ultra-fast dependency sync using uv
if [ -f "uv.lock" ]; then
    uv sync --frozen
else
    uv pip install -r requirements/production.txt
fi

# 3. Compile static styles and apply Postgres migrations
uv run python manage.py collectstatic --noinput --settings=config.settings.production
uv run python manage.py migrate --noinput --settings=config.settings.production

# 4. Create a superuser AUTOMATICALLY if it doesn't exist
uv run python manage.py createsuperuser --noinput || true