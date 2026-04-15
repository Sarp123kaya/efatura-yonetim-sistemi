#!/bin/bash
# PostgreSQL Setup Script for Stateful Ingestion

set -e

echo "🔧 PostgreSQL Stateful Ingestion Setup"
echo "======================================"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "Creating from env.example..."
    cp env.example .env
    echo "✅ Created .env file"
    echo ""
    echo "⚠️  Please edit .env and set:"
    echo "   - DB_URL=postgresql://user:password@localhost:5432/invoices"
    echo "   - ISBASI_API_KEY=your_api_key"
    echo "   - ISBASI_USERNAME=your_username"
    echo ""
    read -p "Press enter when you've configured .env..."
fi

# Load DB_URL from .env
source .env

if [ -z "$DB_URL" ] && [ -z "$PG_DSN" ]; then
    echo "❌ DB_URL not set in .env!"
    echo "Please set DB_URL=postgresql://user:password@host:port/database"
    exit 1
fi

DB_URL="${DB_URL:-$PG_DSN}"

echo "📊 Database URL: ${DB_URL}"
echo ""

# Extract database name from URL
DB_NAME=$(echo "$DB_URL" | sed -E 's|.*/(.*?)(\?.*)?$|\1|')
echo "🗄️  Database: $DB_NAME"
echo ""

# Test connection
echo "🔌 Testing database connection..."
if psql "$DB_URL" -c "SELECT 1" > /dev/null 2>&1; then
    echo "✅ Connection successful!"
else
    echo "❌ Connection failed!"
    echo ""
    echo "Make sure PostgreSQL is running and DB_URL is correct."
    echo "To create database: createdb $DB_NAME"
    exit 1
fi

echo ""
echo "📝 Applying schema..."

# Apply schema
if psql "$DB_URL" < sql/stateful_ingestion_schema.sql; then
    echo "✅ Schema applied successfully!"
else
    echo "❌ Schema application failed!"
    exit 1
fi

echo ""
echo "🔍 Verifying tables..."

# Check if tables exist
TABLES=$(psql "$DB_URL" -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('agent_state', 'incoming_invoices', 'outgoing_invoices')")

if echo "$TABLES" | grep -q "agent_state" && \
   echo "$TABLES" | grep -q "incoming_invoices" && \
   echo "$TABLES" | grep -q "outgoing_invoices"; then
    echo "✅ All tables created:"
    echo "   - agent_state"
    echo "   - incoming_invoices"
    echo "   - outgoing_invoices"
else
    echo "⚠️  Some tables might be missing!"
fi

echo ""
echo "📊 Agent state:"
psql "$DB_URL" -c "SELECT agent_name, last_issue_date, last_run_at FROM agent_state ORDER BY agent_name"

echo ""
echo "======================================"
echo "✅ Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Run incoming agent: python backend/agents/incoming_agent.py"
echo "2. Run outgoing agent: python backend/agents/outgoing_agent.py"
echo ""
