from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel
import logging
import os

app = FastAPI(title="Embedding Service")

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega o nome do modelo de variável de ambiente ou usa o padrão
MODEL_NAME = os.getenv("MODEL_NAME", 'all-MiniLM-L12-v2')

try:
    model = SentenceTransformer(MODEL_NAME)
    logger.info(f"Model {MODEL_NAME} loaded successfully")
except Exception as e:
    logger.error(f"Failed to load model: {str(e)}")
    raise RuntimeError("Model loading failed")

class QueryRequest(BaseModel):
    text: str
    max_tokens: int = 256

@app.post("/embed")
async def generate_embedding(request: QueryRequest):
    try:
        embedding = model.encode(
            request.text,
            batch_size=32,
            normalize_embeddings=False,
            convert_to_numpy=True
        )
        return {
            "embedding": embedding.tolist(),
            "model": MODEL_NAME,
            "dims": len(embedding)
        }
    except Exception as e:
        logger.error(f"Encoding error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": MODEL_NAME}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
