import os
import requests
import urllib3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

app = FastAPI(title="Semantic Math Search")

# --- Config ---
EMBEDDING_SERVICE_URL = os.getenv("GENERATE_EMBEDDINGS_API_URL", "http://localhost:8000") + "/embed"
TOKENS_SERVICE_URL    = os.getenv("GENERATE_TOKENS_API_URL", "http://localhost:8080") + "/api/formulas/process"
MEDIA_SERVICE_URL     = os.getenv("EMBEDDING_AVERAGE_API_URL", "http://localhost:7000") + "/aggregate/json"
ELASTIC_URL           = os.getenv("ELASTIC_URL", "https://localhost:9200")
ELASTIC_USER          = os.getenv("ELASTIC_USER", "elastic")
ELASTIC_PASSWORD      = os.getenv("ELASTIC_PASSWORD", "user123")

DIRECT_INDEX = "formulas_embedding"
TOKEN_INDEX  = "formulas_token_embedding_avg"  # NOTE: must match pipeline.py TOKEN_INDEX and the Elasticsearch index created at bulk time

# --- Elasticsearch client ---
es = Elasticsearch(
    ELASTIC_URL,
    basic_auth=(ELASTIC_USER, ELASTIC_PASSWORD),
    verify_certs=False,
)

# --- Models ---
class SearchRequest(BaseModel):
    mode: str          # "DIRECT" or "TOKENIZED"
    search_formula: str

# --- Helpers ---
def embed(text: str) -> list[float]:
    response = requests.post(EMBEDDING_SERVICE_URL, json={"text": text})
    response.raise_for_status()
    return response.json()["embedding"]

def tokenize(formula: str) -> list[str]:
    response = requests.post(TOKENS_SERVICE_URL, json={"formula": formula})
    response.raise_for_status()
    return response.json()["tokens"]

def average_embeddings(token_embeddings: list[list[float]]) -> list[float]:
    response = requests.post(MEDIA_SERVICE_URL, json={"token_embeddings": token_embeddings})
    response.raise_for_status()
    return response.json()["token_average_embedding"]

def knn_search(index: str, field: str, vector: list[float]) -> list[dict]:
    result = es.search(
        index=index,
        knn={
            "field": field,
            "query_vector": vector,
            "k": 30,
            "num_candidates": 100,
        },
    )
    return [
        {"score": hit["_score"], "formula": hit["_source"]["formula"]}
        for hit in result["hits"]["hits"]
    ]

# --- Endpoint ---
@app.post("/search-formula")
async def search_formula(body: SearchRequest):
    mode = body.mode.upper()
    formula = body.search_formula

    if mode == "DIRECT":
        vector = embed(formula)
        return knn_search(DIRECT_INDEX, "formula_embedding", vector)

    elif mode == "TOKENIZED":
        tokens = tokenize(formula)
        token_embeddings = [embed(token) for token in tokens]
        vector = average_embeddings(token_embeddings)
        return knn_search(TOKEN_INDEX, "token_average_embedding", vector)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode '{mode}'. Use DIRECT or TOKENIZED.")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
