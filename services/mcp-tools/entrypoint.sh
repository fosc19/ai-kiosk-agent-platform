#!/bin/bash
set -e

echo "🗄️  Running database migrations..."
alembic upgrade head

echo "🌱 Checking if seeds are needed..."
python -c "
from mcp_tools.db.session import get_session
from mcp_tools.db.models import Store

with get_session() as session:
    count = session.query(Store).count()
    if count == 0:
        print('Database empty, loading seeds...')
        from mcp_tools.db.seeds import run_seeds
        results = run_seeds()
        print(f'Seeds loaded: {results}')
    else:
        print(f'Database already has {count} stores, skipping seeds.')
"

echo "🚀 Starting MCP Tools server..."
exec python -m mcp_tools.main
