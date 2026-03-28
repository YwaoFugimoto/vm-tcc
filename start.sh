#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

# --- Elasticsearch ---
echo "[1/6] Starting Elasticsearch + Kibana..."
docker compose -f "$ROOT/docker/docker-compose.yml" --env-file "$ROOT/docker/.env" up -d
echo "      Elasticsearch: https://localhost:9200"
echo "      Kibana:        http://localhost:5601"

# --- Create indices ---
echo "[2/6] Waiting for Elasticsearch to be ready..."
until curl -sk -u elastic:user123 https://localhost:9200/_cluster/health | grep -q '"status"'; do
  sleep 5
done
echo "      Creating indices..."
python3 "$ROOT/setup_indices.py"

# --- Embedding service ---
echo "[3/6] Starting embedding-service on port 8000..."
cd "$ROOT/embedding-service"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
nohup .venv/bin/python app/main.py > "$ROOT/logs/embedding-service.log" 2>&1 &
echo "      PID $! — logs/embedding-service.log"

# --- api-media ---
echo "[4/6] Starting api-media on port 7000..."
cd "$ROOT/api-media"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
nohup .venv/bin/python api.py > "$ROOT/logs/api-media.log" 2>&1 &
echo "      PID $! — logs/api-media.log"

# --- tokenizer-service ---
echo "[5/6] Starting tokenizer-service on port 8080..."
cd "$ROOT/tokenizer-service"
if [ ! -f grammar2.6 ]; then
  echo "      WARNING: grammar2.6 binary not found in tokenizer-service/ — tokenized path will not work."
else
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  nohup .venv/bin/python api.py > "$ROOT/logs/tokenizer-service.log" 2>&1 &
  echo "      PID $! — logs/tokenizer-service.log"
fi

# --- search-service ---
echo "[6/6] Starting search-service on port 3000..."
cd "$ROOT/search-service"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
nohup .venv/bin/python api.py > "$ROOT/logs/search-service.log" 2>&1 &
echo "      PID $! — logs/search-service.log"

echo ""
echo "All services started. Run pipeline with:"
echo "  python3 pipeline.py <formulas_file> [--batch-size 100]"
