#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/logs"

port_running() {
  lsof -ti tcp:"$1" >/dev/null 2>&1
}

wait_for_port() {
  local port=$1 name=$2 timeout=${3:-60}
  local elapsed=0
  echo "      Waiting for $name to be ready..."
  while ! port_running "$port"; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ $elapsed -ge $timeout ]; then
      echo "      ERROR: $name failed to start after ${timeout}s. Check logs/$name.log"
      exit 1
    fi
  done
  echo "      $name is ready."
}

setup_venv() {
  local dir=$1
  cd "$dir"
  if [ ! -d .venv ]; then
    echo "      Creating venv and installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt || {
      echo "      ERROR: pip install failed. Check output above."
      rm -rf .venv
      exit 1
    }
  fi
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
  setup_venv "$ROOT/embedding-service"
  nohup .venv/bin/python app/main.py > "$ROOT/logs/embedding-service.log" 2>&1 &
  echo "      PID $! — logs/embedding-service.log"
  wait_for_port 8000 "embedding-service" 120
fi

# --- api-media ---
echo "[4/6] api-media (port 7000)..."
if port_running 7000; then
  echo "      Already running."
else
  setup_venv "$ROOT/api-media"
  nohup .venv/bin/python api.py > "$ROOT/logs/api-media.log" 2>&1 &
  echo "      PID $! — logs/api-media.log"
  wait_for_port 7000 "api-media" 30
fi

# --- tokenizer-service ---
echo "[5/6] tokenizer-service (port 8080)..."
if port_running 8080; then
  echo "      Already running."
elif [ ! -f "$ROOT/tokenizer-service/grammar2.6" ]; then
  echo "      WARNING: grammar2.6 not found — tokenized path will not work."
else
  setup_venv "$ROOT/tokenizer-service"
  nohup .venv/bin/python api.py > "$ROOT/logs/tokenizer-service.log" 2>&1 &
  echo "      PID $! — logs/tokenizer-service.log"
  wait_for_port 8080 "tokenizer-service" 30
fi

# --- search-service ---
echo "[6/6] search-service (port 3000)..."
if port_running 3000; then
  echo "      Already running."
else
  setup_venv "$ROOT/search-service"
  nohup .venv/bin/python api.py > "$ROOT/logs/search-service.log" 2>&1 &
  echo "      PID $! — logs/search-service.log"
  wait_for_port 3000 "search-service" 30
fi

echo ""
echo "All services started. Run pipeline with:"
echo "  python3 pipeline.py <formulas_file> [--batch-size 100]"
