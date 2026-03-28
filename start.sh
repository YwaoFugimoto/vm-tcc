#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/logs"

port_running() {
  lsof -ti tcp:"$1" >/dev/null 2>&1
}

# --- Elasticsearch ---
echo "[1/6] Elasticsearch + Kibana..."
if curl -sk -u elastic:user123 https://localhost:9200/_cluster/health 2>/dev/null | grep -q '"status"'; then
  echo "      Already running."
else
  docker compose -f "$ROOT/docker/docker-compose.yml" --env-file "$ROOT/docker/.env" up -d
  echo "      Waiting for Elasticsearch to be ready..."
  until curl -sk -u elastic:user123 https://localhost:9200/_cluster/health | grep -q '"status"'; do
    sleep 5
  done
  echo "      Elasticsearch: https://localhost:9200"
  echo "      Kibana:        http://localhost:5601"
fi

# --- Create indices ---
echo "[2/6] Elasticsearch indices..."
python3 "$ROOT/setup_indices.py"

# --- Embedding service ---
echo "[3/6] embedding-service (port 8000)..."
if port_running 8000; then
  echo "      Already running."
else
  cd "$ROOT/embedding-service"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  nohup .venv/bin/python app/main.py > "$ROOT/logs/embedding-service.log" 2>&1 &
  echo "      PID $! — logs/embedding-service.log"
fi

# --- api-media ---
echo "[4/6] api-media (port 7000)..."
if port_running 7000; then
  echo "      Already running."
else
  cd "$ROOT/api-media"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  nohup .venv/bin/python api.py > "$ROOT/logs/api-media.log" 2>&1 &
  echo "      PID $! — logs/api-media.log"
fi

# --- tokenizer-service ---
echo "[5/6] tokenizer-service (port 8080)..."
if port_running 8080; then
  echo "      Already running."
elif [ ! -f "$ROOT/tokenizer-service/grammar2.6" ]; then
  echo "      WARNING: grammar2.6 not found — tokenized path will not work."
else
  cd "$ROOT/tokenizer-service"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  nohup .venv/bin/python api.py > "$ROOT/logs/tokenizer-service.log" 2>&1 &
  echo "      PID $! — logs/tokenizer-service.log"
fi

# --- search-service ---
echo "[6/6] search-service (port 3000)..."
if port_running 3000; then
  echo "      Already running."
else
  cd "$ROOT/search-service"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
    .venv/bin/pip install -q -r requirements.txt
  fi
  nohup .venv/bin/python api.py > "$ROOT/logs/search-service.log" 2>&1 &
  echo "      PID $! — logs/search-service.log"
fi

echo ""
echo "All services started. Run pipeline with:"
echo "  python3 pipeline.py <formulas_file> [--batch-size 100]"
