#!/bin/bash
# ─────────────────────────────────────────────────
# Core DB Primary — Enable WAL Streaming Replication
# ─────────────────────────────────────────────────
set -e

echo "=== Setting up Core DB as replication primary ==="

# Create replication user
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
            CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '${REPLICATION_PASSWORD:-repl_secret}';
            RAISE NOTICE 'Created replication user: replicator';
        END IF;
    END
    \$\$;
EOSQL

# Allow replication connections in pg_hba.conf
if ! grep -q "replicator" "$PGDATA/pg_hba.conf" 2>/dev/null; then
    echo "host replication replicator all md5" >> "$PGDATA/pg_hba.conf"
    echo "host all replicator all md5" >> "$PGDATA/pg_hba.conf"
    echo "=== Added replication entries to pg_hba.conf ==="
fi

# Configure WAL settings for streaming replication
cat >> "$PGDATA/postgresql.conf" <<EOF

# ─── Replication Settings (added by setup-primary.sh) ───
wal_level = replica
max_wal_senders = 5
wal_keep_size = 128MB
hot_standby = on
EOF

echo "=== Primary replication configuration complete ==="

# Reload PostgreSQL to apply changes
pg_ctl reload -D "$PGDATA"
echo "=== PostgreSQL reloaded ==="
