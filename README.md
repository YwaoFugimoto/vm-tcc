# vm-tcc

Pipeline para busca semantica de formulas matematicas. Recebe formulas em LaTeX, gera embeddings vetoriais e indexa no Elasticsearch para busca por similaridade (KNN).

## Estrutura do Projeto

```
vm-tcc/
├── pipeline.py                  Processa formulas em batch e indexa no Elasticsearch
├── setup_indices.py             Cria os indices com mapeamento dense_vector
├── start.sh                     Inicia todos os servicos com um comando
├── requirements.txt             Dependencias do pipeline
│
├── embedding-service/           Gera embedding vetorial (384 dims) a partir de texto
│   ├── app/main.py              FastAPI — porta 8000
│   └── requirements.txt
│
├── api-media/                   Calcula media dos embeddings de tokens
│   ├── api.py                   FastAPI — porta 7000
│   └── requirements.txt
│
├── tokenizer-service/           Tokeniza formulas LaTeX em codigos (A0270, A0295...)
│   ├── api.py                   FastAPI — porta 8080
│   ├── grammar2.6               Binario compilado (lexer/parser de formulas)
│   └── requirements.txt
│
├── search-service/              Busca semantica via KNN no Elasticsearch
│   ├── api.py                   FastAPI — porta 3000
│   ├── requirements.txt
│   └── .env.example
│
├── docker/
│   ├── docker-compose.yml       Elasticsearch (2 nodes) + Kibana
│   ├── .env                     Variaveis do docker compose
│   └── .env.example
│
└── tests/                       Testes unitarios e de integracao (pytest)
    ├── test_pipeline.py
    ├── test_api_media.py
    ├── test_tokenizer_service.py
    ├── test_search_service.py
    └── test_setup_indices.py
```

## Pre-requisitos

- Python 3.12+
- Docker e Docker Compose
- O binario `grammar2.6` dentro de `tokenizer-service/`

## Como Iniciar

### 1. Subir todos os servicos

```bash
bash start.sh
```

Isso executa 6 passos em sequencia:
1. Sobe Elasticsearch + Kibana via Docker Compose
2. Aguarda o Elasticsearch ficar saudavel e cria os indices (`setup_indices.py`)
3. Inicia `embedding-service` na porta 8000
4. Inicia `api-media` na porta 7000
5. Inicia `tokenizer-service` na porta 8080
6. Inicia `search-service` na porta 3000

Na primeira execucao, os virtual environments sao criados automaticamente.

Os logs de cada servico ficam em `logs/`.

### 2. Executar o pipeline

O pipeline recebe um arquivo com uma formula por linha:

```bash
python3 pipeline.py formulas.txt
```

Com batch size customizado (padrao: 100):

```bash
python3 pipeline.py formulas.txt --batch-size 50
```

Para cada formula, o pipeline:
1. **Caminho DIRETO** — gera embedding da formula e indexa em `formulas_embedding`
2. **Caminho TOKENIZADO** — tokeniza a formula, gera embedding de cada token, calcula a media e indexa em `formulas_token_embedding_avg`

### 3. Buscar formulas

```bash
# Busca direta
curl -X POST http://localhost:3000/search-formula \
  -H "Content-Type: application/json" \
  -d '{"mode": "DIRECT", "search_formula": "$\\sum_{i=1}^n x_i$"}'

# Busca tokenizada
curl -X POST http://localhost:3000/search-formula \
  -H "Content-Type: application/json" \
  -d '{"mode": "TOKENIZED", "search_formula": "$\\sum_{i=1}^n x_i$"}'
```

Retorna as 3 formulas mais similares com score de similaridade:

```json
[
  {"score": 0.95, "formula": "..."},
  {"score": 0.87, "formula": "..."},
  {"score": 0.82, "formula": "..."}
]
```

## Indices do Elasticsearch

| Indice | Campo vetorial | Uso |
|--------|----------------|-----|
| `formulas_embedding` | `formula_embedding` | Caminho DIRETO |
| `formulas_token_embedding_avg` | `token_average_embedding` | Caminho TOKENIZADO |

Ambos usam `dense_vector` com 384 dimensoes, similaridade cosseno e indice HNSW.

Os mapeamentos sao criados automaticamente pelo `setup_indices.py` (chamado no `start.sh`).

## Servicos

| Servico | Porta | Endpoint Principal |
|---------|-------|--------------------|
| embedding-service | 8000 | `POST /embed` — `{"text": "..."}` |
| api-media | 7000 | `POST /aggregate/json` — `{"token_embeddings": [[...], ...]}` |
| tokenizer-service | 8080 | `POST /api/formulas/process` — `{"formula": "..."}` |
| search-service | 3000 | `POST /search-formula` — `{"mode": "DIRECT\|TOKENIZED", "search_formula": "..."}` |
| Elasticsearch | 9200 | `https://localhost:9200` (auth: `elastic` / `user123`) |
| Kibana | 5601 | `http://localhost:5601` |

## Testes

```bash
python3 -m pytest tests/ -v
```

Todos os testes rodam sem servicos ativos (HTTP e Elasticsearch sao mockados).

## Fluxo Completo

```
formulas.txt
     │
     ▼
pipeline.py (batch)
     │
     ├── DIRETO: POST :8000/embed → embedding → Elasticsearch
     │
     └── TOKENIZADO: POST :8080/process → tokens
                         │
                     POST :8000/embed (cada token)
                         │
                     POST :7000/aggregate → media
                         │
                     Elasticsearch
     │
     ▼
search-service (:3000) → KNN query → top 3 resultados
```
