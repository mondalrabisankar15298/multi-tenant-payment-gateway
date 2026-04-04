#!/bin/bash
# ─────────────────────────────────────────────────
# Core DB Replica — Bootstrap from Primary
# ─────────────────────────────────────────────────
set -e

PGDATA="/var/lib/postgresql/data"
PRIMARY_HOST="${PRIMARY_HOST:-core-db}"
PRIMARY_PORT="${PRIMARY_PORT:-5432}"
REPL_USER="${REPL_USER:-replicator}"
REPL_PASSWORD="${REPLICATION_PASSWORD:-repl_secret}"

echo "=== Setting up Core DB Read Replica ==="

# Wait for primary to be ready
echo "Waiting for primary at ${PRIMARY_HOST}:${PRIMARY_PORT}..."
until PGPASSWORD="$REPL_PASSWORD" pg_isready -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U "$REPL_USER" 2>/dev/null; do
    echo "  Primary not ready, retrying in 2s..."
    sleep 2
done
echo "Primary is ready!"

# Check if this is a fresh replica (no data yet)
if [ ! -f "$PGDATA/PG_VERSION" ]; then
    echo "=== Bootstrapping replica via pg_basebackup ==="

    # Clean data directory
    rm -rf "$PGDATA"/*

    # Clone from primary
    PGPASSWORD="$REPL_PASSWORD" pg_basebackup \
        -h "$PRIMARY_HOST" \
        -p "$PRIMARY_PORT" \
        -U "$REPL_USER" \
        -D "$PGDATA" \
        -Fp -Xs -R -P

    # -R creates standby.signal and sets primary_conninfo automatically
    # -Fp = plain format
    # -Xs = stream WAL during backup
    # -P = show progress

    # Ensure hot_standby is enabled (read-only queries)
    if ! grep -q "hot_standby = on" "$PGDATA/postgresql.conf" 2>/dev/null; then
        echo "hot_standby = on" >> "$PGDATA/postgresql.conf"
    fi

    echo "=== Replica bootstrap complete ==="
else
    echo "=== Data directory exists, assuming replica is already configured ==="
fi
