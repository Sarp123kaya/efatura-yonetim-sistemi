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
echo "📝 Applying schema and migrations..."

SQL_FILES=(
    "sql/stateful_ingestion_schema_v2.sql"
    "sql/migration_v2.2_despatch_improvements.sql"
    "sql/migration_irsaliye_override.sql"
    "sql/migration_incoming_xml_cache.sql"
)

for sql_file in "${SQL_FILES[@]}"; do
    echo "   ▶ $sql_file"
    if psql "$DB_URL" -v ON_ERROR_STOP=1 < "$sql_file"; then
        echo "   ✅ Applied"
    else
        echo "   ❌ Failed: $sql_file"
        exit 1
    fi
done

echo "✅ Schema and migrations applied successfully!"

echo ""
echo "🔍 Verifying tables..."

# Check if tables exist
TABLES=$(psql "$DB_URL" -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('agent_state', 'incoming_invoices', 'outgoing_invoices', 'incoming_invoice_xml_cache', 'agent_runs')")

if echo "$TABLES" | grep -q "agent_state" && \
   echo "$TABLES" | grep -q "incoming_invoices" && \
   echo "$TABLES" | grep -q "outgoing_invoices" && \
   echo "$TABLES" | grep -q "incoming_invoice_xml_cache"; then
    echo "✅ All tables created:"
    echo "   - agent_state"
    echo "   - incoming_invoices"
    echo "   - outgoing_invoices"
    echo "   - incoming_invoice_xml_cache"
    if echo "$TABLES" | grep -q "agent_runs"; then
        echo "   - agent_runs"
    fi
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
echo "1. First full run with XML cache: python3 scripts/run_invoice_pipeline.py --start-date 2026-01-01 --refresh-xml"
echo "2. Regular updates: python3 scripts/run_invoice_pipeline.py"
echo "3. Supplier detail Excel exports: python3 scripts/export_supplier_invoice_details.py"
echo ""
