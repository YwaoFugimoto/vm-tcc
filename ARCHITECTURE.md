# Arquitetura do Sistema / System Architecture

Documentacao tecnica do sistema de busca semantica para formulas matematicas, desenvolvido como Trabalho de Conclusao de Curso (TCC).

Technical documentation for the semantic search system for mathematical formulas, developed as a Final Course Project (TCC).

---

## 1. Visao Geral / Overview

### Problema / Problem

A busca tradicional por palavras-chave falha para formulas matematicas. A mesma expressao pode ser escrita de diversas formas em LaTeX — `\sum_{i=1}^n`, `\Sigma_{i=1}^{n}`, `\displaystyle\sum_{i=1}^n` — e uma busca textual nao reconhece que sao semanticamente equivalentes.

Traditional keyword search fails for mathematical formulas. The same expression can be written in many LaTeX forms, and text search cannot recognize semantic equivalence.

### Solucao / Solution

Converter formulas matematicas em vetores densos de 384 dimensoes (embeddings) usando o modelo `all-MiniLM-L12-v2` (Sentence Transformers). Formulas com significado semelhante produzem vetores proximos no espaco vetorial. A busca e feita por similaridade de cosseno usando KNN (k-Nearest Neighbors) no Elasticsearch com o algoritmo HNSW.

Convert mathematical formulas into 384-dimensional dense vectors (embeddings) using the `all-MiniLM-L12-v2` model. Similar formulas produce nearby vectors. Search is performed via cosine similarity using KNN in Elasticsearch with the HNSW algorithm.

### Duas Estrategias de Busca / Two Search Strategies

O sistema oferece dois modos de busca para comparar abordagens:

| Modo | Descricao | Vantagem |
|------|-----------|----------|
| **DIRECT** | Gera um unico embedding da formula inteira | Captura a estrutura global da formula |
| **TOKENIZED** | Decompoe a formula em tokens via `grammar2.6`, gera embedding de cada token, calcula a media | Captura a semantica dos componentes individuais |

---

## 2. Conceitos Fundamentais / Core Concepts

### Sentence Transformers

Biblioteca Python que fornece modelos pre-treinados para gerar embeddings de texto. O modelo utilizado e o `all-MiniLM-L12-v2`:
- Produz vetores de **384 dimensoes**
- Treinado em grandes corpus de texto para capturar significado semantico
- Leve e rapido (12 camadas, ~33M parametros)

### Similaridade de Cosseno / Cosine Similarity

Mede o angulo entre dois vetores. Valores entre 0 e 1 (apos normalizacao):
- **1.0** = vetores identicos (formula exata)
- **~0.9** = formulas muito similares
- **~0.5** = baixa similaridade
- **0.0** = sem relacao

### HNSW (Hierarchical Navigable Small World)

Algoritmo de busca aproximada de vizinhos mais proximos (ANN) usado pelo Elasticsearch. Parametros configurados:
- `m = 16` — numero de conexoes por nodo no grafo
- `ef_construction = 100` — qualidade do grafo durante indexacao
- `k = 30` — numero de resultados retornados
- `num_candidates = 100` — candidatos avaliados durante busca

### grammar2.6

Binario compilado (ELF x86-64) que implementa um lexer/parser para formulas LaTeX. Recebe uma formula via stdin e produz codigos de tokens via stdout:

```
Input:  ! \colon A \to 1
Output: A0270 A0295 A0917 A0144 A0656
```

Cada codigo (A0270, A0295, etc.) representa um conceito matematico, operador ou simbolo. A tokenizacao permite que a busca opere no nivel dos componentes da formula.

---

## 3. Arquitetura / Architecture

### Diagrama de Servicos / Service Diagram

```
                        +-----------------+
                        |   Kibana :5601  |
                        +--------+--------+
                                 |
                        +--------+--------+
                        | Elasticsearch   |
                        | :9200 (2 nodes) |
                        | HNSW + KNN      |
                        +--------+--------+
                                 |
         +-----------------------+-----------------------+
         |                                               |
+--------+--------+                            +---------+---------+
| search-service  |                            |    pipeline.py    |
| :3000           |                            |    (batch CLI)    |
| POST /search-   |                            |                   |
|      formula    |                            |                   |
+---+------+------+                            +---+------+--------+
    |      |                                       |      |
    |      +------+------+------+                  |      +------+------+------+
    |             |      |      |                  |             |      |      |
    |    +--------+  +---+--+ +-+--------+         |    +--------+  +---+--+ +-+--------+
    |    |embedding|  |api- | |tokenizer |         |    |embedding|  |api- | |tokenizer |
    |    |service  |  |media| |service   |         |    |service  |  |media| |service   |
    |    |:8000    |  |:7000| |:8080     |         |    |:8000    |  |:7000| |:8080     |
    |    |         |  |     | |grammar2.6|         |    |         |  |     | |grammar2.6|
    |    +---------+  +-----+ +----------+         |    +---------+  +-----+ +----------+
    |                                              |
    +----------------------------------------------+
                  Elasticsearch :9200
```

### Fluxo de Indexacao / Indexing Flow

```
formulas.txt (1 formula por linha)
       |
       v
  pipeline.py (processa em batches)
       |
       +------ CAMINHO DIRETO ------+------ CAMINHO TOKENIZADO ------+
       |                            |                                 |
  POST :8000/embed             POST :8080/api/formulas/process        |
  { text: formula }            { formula: formula }                   |
       |                            |                                 |
       v                            v                                 |
  formula_embedding          token list [A0270, A0295, ...]           |
  (384 dimensoes)                   |                                 |
       |                      para cada token:                        |
       |                        POST :8000/embed                      |
       |                            |                                 |
       |                      POST :7000/aggregate/json               |
       |                      { token_embeddings: [[...], [...]] }    |
       |                            |                                 |
       |                            v                                 |
       |                      token_average_embedding                 |
       |                      (384 dimensoes)                         |
       |                            |                                 |
       v                            v                                 |
  NDJSON:                      NDJSON:                                |
  { formula,                   { formula, token_list,                 |
    formula_embedding }          token_average_embedding }            |
       |                            |                                 |
       +----------------------------+---------------------------------+
       |
       v
  POST :9200/_bulk
  -> formulas_embedding (indice DIRETO)
  -> formulas_token_embedding_avg (indice TOKENIZADO)
```

### Fluxo de Busca / Search Flow

```
POST :3000/search-formula
{ mode: "DIRECT" | "TOKENIZED", search_formula: "..." }
       |
       +--- DIRECT ----+--- TOKENIZED ---+
       |                |                 |
  embed(formula)   tokenize(formula)      |
       |                |                 |
       |           embed(cada token)      |
       |                |                 |
       |           average(embeddings)    |
       |                |                 |
       v                v                 |
  KNN search        KNN search            |
  formulas_         formulas_token_       |
  embedding         embedding_avg         |
       |                |                 |
       +----------------+-----------------+
       |
       v
  [{ score: 0.95, formula: "..." }, ...]  (top 30 resultados)
```

---

## 4. Servicos / Services

### 4.1 embedding-service (porta 8000)

Gera embeddings vetoriais de 384 dimensoes a partir de texto usando Sentence Transformers.

**Arquivo:** `embedding-service/app/main.py`
**Modelo:** `all-MiniLM-L12-v2` (configuravel via env `MODEL_NAME`)

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/embed` | POST | Gera embedding para um texto |
| `/health` | GET | Verificacao de saude |

**POST /embed**
```json
// Request
{ "text": "\\sum_{i=1}^n x_i" }

// Response
{
  "embedding": [0.023, -0.041, ..., 0.018],  // 384 floats
  "model": "all-MiniLM-L12-v2",
  "dims": 384
}
```

**Detalhes tecnicos:**
- O modelo e carregado uma vez na inicializacao (`SentenceTransformer(MODEL_NAME)`)
- Encoding usa `batch_size=32`, `normalize_embeddings=False`
- Retorna o vetor como lista de floats (conversao numpy → list)

---

### 4.2 api-media (porta 7000)

Calcula a media aritmetica de multiplos embeddings de tokens, produzindo um unico vetor representativo.

**Arquivo:** `api-media/api.py`

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/aggregate/json` | POST | Media de embeddings via JSON |
| `/aggregate/ndjson` | POST | Media de embeddings via arquivo NDJSON |

**POST /aggregate/json**
```json
// Request
{
  "token_embeddings": [
    [0.1, 0.2, ..., 0.3],   // embedding token 1
    [0.4, 0.5, ..., 0.6]    // embedding token 2
  ]
}

// Response
{
  "token_average_embedding": [0.25, 0.35, ..., 0.45]  // media dos vetores
}
```

**Detalhes tecnicos:**
- Usa `numpy.mean(axis=0)` para calculo eficiente
- Retorna lista vazia se input for vazio

---

### 4.3 tokenizer-service (porta 8080)

Converte formulas LaTeX em codigos de tokens usando o binario `grammar2.6`.

**Arquivo:** `tokenizer-service/api.py`
**Dependencia:** binario `grammar2.6` (ELF x86-64)

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/api/formulas/process` | POST | Tokeniza uma formula |
| `/api/formulas/process-file` | POST | Tokeniza arquivo de formulas |

**POST /api/formulas/process**
```json
// Request
{ "formula": "! \\colon A \\to 1" }

// Response
{ "tokens": ["A0270", "A0295", "A0917", "A0144", "A0656"] }
```

**Detalhes tecnicos:**
- Executa `grammar2.6` via `subprocess.run()`
- Envia formula via stdin, le tokens via stdout
- Tokens sao separados por espaco no output do binario
- Retorna 400 se formula vazia, 500 se o binario falhar

---

### 4.4 search-service (porta 3000)

Orquestra a busca semantica. Recebe uma formula e um modo, gera o embedding apropriado e executa busca KNN no Elasticsearch.

**Arquivo:** `search-service/api.py`

| Endpoint | Metodo | Descricao |
|----------|--------|-----------|
| `/search-formula` | POST | Busca semantica de formulas |
| `/health` | GET | Verificacao de saude |

**POST /search-formula**
```json
// Request
{
  "mode": "DIRECT",
  "search_formula": "(K\\odot X) = ((K_0 \\cdot X_a))"
}

// Response
[
  { "score": 0.9960, "formula": "(K\\odot X) = ((K_0 \\cdot X_a) ...)" },
  { "score": 0.7090, "formula": "(K/m)^\\ast(BG) \\to \\prod_F ..." },
  { "score": 0.6780, "formula": "!^\\ast: \\Map(1, \\mathcal{M} ...)" }
]
```

**Modo DIRECT:**
1. `embed(search_formula)` → vetor de 384 dimensoes
2. KNN search no indice `formulas_embedding`, campo `formula_embedding`

**Modo TOKENIZED:**
1. `tokenize(search_formula)` → lista de tokens
2. `embed(token)` para cada token → lista de vetores
3. `average_embeddings(token_embeddings)` → vetor medio
4. KNN search no indice `formulas_token_embedding_avg`, campo `token_average_embedding`

**Parametros KNN:** k=30, num_candidates=100, similaridade cosseno

---

### 4.5 Elasticsearch (porta 9200)

Cluster de 2 nodos para armazenamento e busca vetorial.

**Configuracao:** `docker/docker-compose.yml`
**Versao:** 8.17.2
**Seguranca:** TLS habilitado, autenticacao basica (`elastic:user123`)

---

### 4.6 Kibana (porta 5601)

Dashboard de monitoramento para visualizar indices, documentos e status do cluster.

---

## 5. Pipeline de Indexacao / Indexing Pipeline

**Arquivo:** `pipeline.py`

### Funcoes / Functions

| Funcao | Entrada | Saida | Descricao |
|--------|---------|-------|-----------|
| `embed(text)` | string | `list[float]` (384d) | POST ao embedding-service |
| `tokenize(formula)` | string | `list[str]` | POST ao tokenizer-service |
| `average_embeddings(embeddings)` | `list[list[float]]` | `list[float]` (384d) | POST ao api-media |
| `build_bulk_action(index, doc_id)` | string, int | dict | Monta header NDJSON para Elasticsearch |
| `run_direct_path(formula, doc_id)` | string, int | `list[str]` (2 linhas) | Gera NDJSON para caminho direto |
| `run_tokenized_path(formula, tokens, doc_id)` | string, list, int | `list[str]` (2 linhas) | Gera NDJSON para caminho tokenizado |
| `send_to_elastic(ndjson_lines)` | `list[str]` | - | POST `/_bulk` ao Elasticsearch |
| `log_failure(doc_id, formula, error)` | int, string, string | - | Loga formula com falha |
| `save_unsent_batch(batch_num, lines)` | int, `list[str]` | - | Salva batch nao enviado em disco |
| `main(input_file, batch_size, start_from)` | string, int, int | - | Orquestra o pipeline completo |

### Uso / Usage

```bash
# Processar todas as formulas
python3 pipeline.py formulas.txt

# Com batch size customizado
python3 pipeline.py formulas.txt --batch-size 50

# Retomar a partir de uma formula especifica
python3 pipeline.py formulas.txt --start-from 175800
```

### Tratamento de Erros / Error Handling

- **Falha em formula individual:** loga em `failed_formulas.txt` (formato: `doc_id\tformula\terror`), continua processamento
- **Falha no Elasticsearch:** salva batch em `unsent_batches/batch_N.ndjson` para retry manual
- **Resumo final:** imprime `X succeeded, Y failed`

---

## 6. Indices do Elasticsearch / Elasticsearch Indices

**Arquivo de configuracao:** `setup_indices.py`

### formulas_embedding (Caminho DIRETO)

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `formula` | text | Formula LaTeX original |
| `title` | text (keyword) | Titulo opcional |
| `formula_embedding` | dense_vector (384d) | Embedding direto da formula |

### formulas_token_embedding_avg (Caminho TOKENIZADO)

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `formula` | text | Formula LaTeX original |
| `title` | text (keyword) | Titulo opcional |
| `token_list` | text | Lista de tokens (A0270, A0295, ...) |
| `token_average_embedding` | dense_vector (384d) | Media dos embeddings dos tokens |

### Configuracao dos Vetores / Vector Configuration

Ambos os indices usam a mesma configuracao para campos `dense_vector`:
- **Dimensoes:** 384
- **Indexado:** sim (habilitado para busca KNN)
- **Similaridade:** cosseno
- **Algoritmo:** HNSW
- **HNSW m:** 16 (conexoes por nodo)
- **HNSW ef_construction:** 100 (qualidade do grafo)
- **Shards:** 1, **Replicas:** 0

---

## 7. O Papel do grammar2.6 / The Role of grammar2.6

O `grammar2.6` e um binario compilado (lexer/parser) que transforma formulas LaTeX em sequencias de codigos de tokens. Cada codigo representa um conceito matematico:

```
Entrada: (K-\lambda I)^{-1} = \left( \begin{array}{ccc} (A-\lambda I)^{-1} & 0 \end{array} \right)

Saida:   A0302 A0901 A0005 A0552 A0899 A0306 A0239 A0005 A0656 A0034 A0302 ...
```

### Por que tokenizar? / Why tokenize?

- **DIRECT** trata `\sum_{i=1}^n x_i + y_i` como uma string unica. O embedding captura o "significado geral" da formula.
- **TOKENIZED** decompoe em `[\sum, _{i=1}^n, x_i, +, y_i]` (como codigos A0###). Cada token recebe seu proprio embedding. A media dos embeddings captura a composicao dos significados individuais.

Isso permite que a busca TOKENIZED encontre formulas que compartilham componentes matematicos, mesmo quando a estrutura global e diferente.

### Detalhes Tecnicos / Technical Details

- **Formato:** ELF 64-bit x86-64, dinamicamente linkeditado
- **Dependencia:** `libfl.so.2` (flex library — instalar com `apt install libfl2`)
- **I/O:** stdin (formula) → stdout (tokens separados por espaco)
- **Wrapper:** `tokenizer-service/api.py` expoe como HTTP API na porta 8080

---

## 8. Infraestrutura / Infrastructure

### start.sh — Inicializacao

Executa 6 passos em sequencia, com verificacoes de saude e criacao automatica de virtual environments:

| Passo | Servico | Acao |
|-------|---------|------|
| 1/6 | Elasticsearch + Kibana | `docker compose up -d`, aguarda cluster saudavel |
| 2/6 | Indices | Executa `setup_indices.py` (cria indices se nao existem) |
| 3/6 | embedding-service :8000 | Cria venv, instala deps, inicia, aguarda porta (timeout: 120s) |
| 4/6 | api-media :7000 | Cria venv, instala deps, inicia, aguarda porta (timeout: 30s) |
| 5/6 | tokenizer-service :8080 | Verifica `grammar2.6`, cria venv, inicia (timeout: 30s) |
| 6/6 | search-service :3000 | Cria venv, instala deps, inicia, aguarda porta (timeout: 30s) |

**Caracteristicas:**
- Pula servicos que ja estao rodando (idempotente)
- Se `pip install` falha, remove o venv e aborta
- Logs de cada servico em `logs/`

### stop.sh — Desligamento

1. Mata processos Python por porta (8000, 7000, 8080, 3000)
2. Para containers Docker (`docker compose down`)
3. Limpa arquivos de log

### Docker Compose

- **2 nodos Elasticsearch** (es01, es02) com TLS
- **1 Kibana** para monitoramento
- **1 servico setup** para gerar certificados SSL
- **Volumes persistentes:** `esdata01`, `esdata02`, `kibanadata`, `certs`
- **Memoria:** configuravel via `MEM_LIMIT` no `.env`

---

## 9. Testes / Tests

### Testes Unitarios (29 testes)

Rodam sem servicos ativos (tudo mockado):

```bash
python3 -m pytest tests/ -v -m "not live"
```

| Arquivo | Testes | Cobertura |
|---------|--------|-----------|
| `test_pipeline.py` | 16 | Todas as funcoes do pipeline, batching, falhas, resume |
| `test_api_media.py` | 3 | Endpoint de media (normal, unico, vazio) |
| `test_tokenizer_service.py` | 5 | Tokenizacao, upload de arquivo, formula vazia, falha |
| `test_search_service.py` | 4 | Busca DIRECT/TOKENIZED, modo invalido, health |
| `test_setup_indices.py` | 4 | Criacao de indice, existente, falha, mapeamentos |

### Testes de Execucao / Live Tests (54 testes)

Rodam contra o banco de dados real com 1.6M formulas:

```bash
python3 -m pytest tests/test_execution.py -v -s -m live
```

| Categoria | Testes | Validacao |
|-----------|--------|-----------|
| Estrutura da resposta | 3 | JSON valido, ate 30 resultados, scores 0-1 |
| Correspondencia exata | 3 | Score >= 0.95 para formulas indexadas |
| Ambos os modos | 2 | DIRECT e TOKENIZED retornam resultados |
| Relevancia semantica | 3 | Variacoes e subexpressoes encontram formulas relacionadas |
| Faixas de complexidade | 3 | Formulas curtas, medias e longas |
| Unicode e LaTeX especial | 4 | Setas unicode, `\mathbb`, `\mathcal`, `\overset` |
| Casos extremos | 3 | Formula vazia, modo invalido, muitos backslashes |
| Ordenacao de scores | 1 | Resultados em ordem decrescente |
| Comparacao DIRECT vs TOKENIZED | 32 | Top result, overlap top-10, distribuicao de scores |

### Comparacao entre Modos / Mode Comparison

Os testes de comparacao executam 8 formulas diversas em ambos os modos e verificam:
- **Mesmo top result:** O resultado #1 e o mesmo em ambos os modos?
- **Comparacao de scores:** Qual modo produz scores mais altos?
- **Overlap no top-10:** Quantas formulas aparecem nos top-10 de ambos os modos?
- **Distribuicao de scores:** Media, maximo e minimo dos scores por modo

---

## 10. Resumo de Portas / Port Summary

| Servico | Porta | Protocolo | Endpoint Principal |
|---------|-------|-----------|--------------------|
| Elasticsearch | 9200 | HTTPS | `/_bulk`, `/_search` |
| Kibana | 5601 | HTTP | Dashboard UI |
| embedding-service | 8000 | HTTP | `POST /embed` |
| api-media | 7000 | HTTP | `POST /aggregate/json` |
| tokenizer-service | 8080 | HTTP | `POST /api/formulas/process` |
| search-service | 3000 | HTTP | `POST /search-formula` |

## 11. Constantes e Invariantes / Constants and Invariants

- **Dimensao dos vetores:** 384 (fixo pelo modelo `all-MiniLM-L12-v2`)
- **Nomes dos indices:** `formulas_embedding` e `formulas_token_embedding_avg` (devem coincidir em `pipeline.py`, `search-service/api.py` e `setup_indices.py`)
- **Campos vetoriais:** `formula_embedding` (direto) e `token_average_embedding` (tokenizado)
- **KNN:** k=30 resultados, 100 candidatos avaliados
- **Autenticacao ES:** `elastic:user123`
- **SSL:** Verificacao desabilitada nos clientes Python (`verify=False`)
