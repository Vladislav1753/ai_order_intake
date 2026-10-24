# Run `just` to list recipes. Install: winget install --id Casey.Just -e
# The plain uv commands behind each recipe are listed in README "Setup".

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# List recipes
default:
    @just --list --unsorted

# Install dependencies and the pre-commit hook, migrate, and load the catalog
install:
    uv sync
    uv run pre-commit install
    uv run alembic upgrade head
    uv run python -m app.cli seed

# Apply all migrations to the database (var/orders.db unless DATABASE_URL is set)
migrate:
    uv run alembic upgrade head

# Load the catalog from data/seed/seed.json (insert or update by SKU; safe to rerun)
seed:
    uv run python -m app.cli seed

# Process the seed requests and data/inbox from saved responses (no API key needed)
process:
    uv run python -m app.cli process --mode replay

# Process with real model calls and save each response to replays/ (needs MODEL_API_KEY)
record:
    uv run python -m app.cli process --mode live

# Generate a migration from model changes, e.g. just revision "add attachments"
revision message:
    uv run alembic revision --autogenerate -m "{{message}}"

# Start the app on http://127.0.0.1:8000 with reload
run:
    uv run uvicorn app.main:app --reload

# Run pytest (extra args pass through, e.g. just test -k pricing)
test *args:
    uv run pytest {{args}}

# Lint with ruff
lint:
    uv run ruff check .

# Format, then apply ruff's safe fixes
format:
    uv run ruff format .
    uv run ruff check --fix .

# Type-check with mypy
typecheck:
    uv run mypy app scripts

# Full pre-commit gate, the same one a commit runs
check:
    uv run pre-commit run --all-files

# Fail if uv.lock is out of date with pyproject.toml
lock-check:
    uv lock --check
