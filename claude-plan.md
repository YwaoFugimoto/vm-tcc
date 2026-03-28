# Plan: Unified Formula Pipeline

## Context

Currently, processing a formula into Elasticsearch requires running 6+ scripts manually in sequence, copying intermediate files between stages. The goal is a **single `pipeline.py`** that accepts a formula as input and drives it all the way to both Elasticsearch indices — `formulas_embedding` (DIRECT path) and `formulas_token_embedding` (TOKENIZED path) — with no intermediate files and no manual steps.

The Java tokenization API lives on Windows and is not yet accessible from WSL; its integration will be added later. For now, the TOKENIZED path will accept a pre-tokenized list as input or can be skipped.

---

## What Gets Built

**File:** `/home/default/all-tcc-content/main_tcc/pipeline.py`

A single Python script that orchestrates both processing paths end-to-end.

---

## Pipeline Architecture

```
Input: formula string (+ optional token list)
              │
    ┌─────────┴─────────┐
    │                   │
 DIRECT PATH       TOKENIZED PATH
    │                   │
 POST /embed         [Java API - stub]
 (embedding-service  → token list
  port 8000)            │
    │              for each token:
    │              POST /embed
    │              (port 8000)
    │                   │
    │              POST /aggregate/json
    │              (api-media, port 7000)
    │                   │
    └─────────┬─────────┘
              │
     Elasticsearch bulk POST
     https://localhost:9200/_bulk
     → formulas_embedding
     → formulas_token_embedding
```

---

## Implementation Steps

### 1. Config block (top of file)
```python
EMBEDDING_SERVICE_URL = "http://localhost:8000/embed"
MEDIA_SERVICE_URL     = "http://localhost:7000/aggregate/json"
ELASTIC_URL           = "https://localhost:9200/_bulk"
ELASTIC_AUTH          = ("elastic", "user123")
DIRECT_INDEX          = "formulas_embedding"
TOKEN_INDEX           = "formulas_token_embedding"
```

### 2. `embed(text: str) -> list[float]`
- POST to embedding-service `/embed` with `{"text": text}`
- Returns 384-dim vector

### 3. `average_embeddings(token_embeddings: list[list[float]]) -> list[float]`
- POST to api-media `/aggregate/json` with `{"token_embeddings": [...]}`
- Returns single 384-dim averaged vector

### 4. `tokenize(formula: str) -> list[str]`
- **Stub for now** — raises `NotImplementedError` with clear message
- Will call Java API once it's accessible from WSL
- Callers check if token list was provided manually to bypass this

### 5. `build_bulk_action(index: str, doc_id: int) -> dict`
- Returns the `{"index": {"_index": index, "_id": doc_id}}` metadata line

### 6. `run_direct_path(formula: str, doc_id: int) -> list[str]`
- Calls `embed(formula)` → `formula_embedding`
- Returns 2 NDJSON lines: action + `{"formula": ..., "formula_embedding": [...]}`

### 7. `run_tokenized_path(formula: str, token_list: list[str], doc_id: int) -> list[str]`
- Embeds each token individually via `embed(token)`
- Calls `average_embeddings(token_embeddings)`
- Returns 2 NDJSON lines: action + `{"formula": ..., "token_list": [...], "token_average_embedding": [...]}`

### 8. `send_to_elastic(ndjson_lines: list[str])`
- POSTs joined NDJSON to `/_bulk`
- Uses `verify=False` (self-signed cert), basic auth
- Checks `response.json()["errors"]` and reports failures

### 9. `main(formula: str, token_list: list[str] | None)`
- Generates a doc_id (timestamp-based or sequential)
- Runs DIRECT path → collect lines
- If `token_list` provided, runs TOKENIZED path → collect lines
- Sends all lines in one bulk request
- CLI: `python pipeline.py "formula string" [--tokens "T1 T2 T3"]`

---

## CLI Interface

```bash
# Direct path only (tokenized path skipped — Java API not ready)
python pipeline.py "$\sum_{i=1}^n x_i$"

# Both paths (tokens provided manually)
python pipeline.py "$\sum_{i=1}^n x_i$" --tokens "A0270 A0295 A0301"
```

---

## Services Required at Runtime

| Service | Port | Start Command |
|---------|------|---------------|
| embedding-service | 8000 | `python3 app/main.py` in `/home/default/embedding-service/` |
| api-media | 7000 | `python3 api.py` in `/home/default/api-media/` |
| Elasticsearch | 9200 | `docker compose up` in `/home/default/kibana-tcc/mathseek/back-end/` |

---

## Files Referenced

| File | Role |
|------|------|
| `/home/default/all-tcc-content/main_tcc/pipeline.py` | **New file to create** |
| `/home/default/embedding-service/app/main.py` | POST /embed endpoint |
| `/home/default/api-media/api.py` | POST /aggregate/json endpoint |
| `/home/default/kibana-tcc/mathseek/back-end/docker-compose.yml` | Elasticsearch stack |
| `/home/default/all-tcc-content/main_tcc/media_ponderada.py` | Reusable weighted average logic (local fallback reference) |

---

## Verification

1. Start all three services (embedding-service, api-media, Elasticsearch via docker compose)
2. Run: `python pipeline.py "$\sum_{i=1}^n x_i$" --tokens "A0270 A0295"`
3. Confirm no errors in output
4. Verify both indices received the document:
   ```bash
   curl -k -u elastic:user123 https://localhost:9200/formulas_embedding/_search?pretty
   curl -k -u elastic:user123 https://localhost:9200/formulas_token_embedding/_search?pretty
   ```

---

## Future Work (out of scope for this plan)

- Integrate Java tokenizer from WSL once accessible (replace stub in `tokenize()`)
- Batch mode: accept a file of formulas and process in bulk
- Retry logic for failed HTTP calls to services
