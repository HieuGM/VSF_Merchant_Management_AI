#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
SELECT 'CREATE DATABASE mem0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mem0')\gexec
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname mem0 \
  -c 'CREATE EXTENSION IF NOT EXISTS vector;'
