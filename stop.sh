#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping services..."

# --- Kill Python services by port ---
for port in 8000 7000 8080 3000; do
  pid=$(lsof -ti tcp:$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    kill $pid 2>/dev/null && echo "  Port $port — stopped (PID $pid)" || true
  else
    echo "  Port $port — not running"
  fi
done

# --- Stop Elasticsearch + Kibana ---
echo "Stopping Elasticsearch + Kibana..."
docker compose -f "$ROOT/docker/docker-compose.yml" --env-file "$ROOT/docker/.env" down

echo "All services stopped."
