import json
import numpy as np
from typing import List, Dict, Any, Union
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Embedding Aggregator API")

# --- Modelos de Dados ---
class TokenEmbeddingsRequest(BaseModel):
    # Recebe uma lista de listas (cada sub-lista é um embedding de um token)
    token_embeddings: List[List[float]]

class AverageEmbeddingResponse(BaseModel):
    token_average_embedding: List[float]

# --- Função de Cálculo ---
def calculate_average(embeddings: List[List[float]]) -> List[float]:
    """Calcula a média vetorial usando NumPy."""
    if not embeddings:
        return []

    emb_array = np.array(embeddings)
    avg_embedding = np.mean(emb_array, axis=0)
    return avg_embedding.tolist()

# --- Endpoints ---

@app.post("/aggregate/json", response_model=AverageEmbeddingResponse)
async def aggregate_json(data: TokenEmbeddingsRequest):
    """
    Recebe um JSON com a lista de embeddings e retorna a média.
    """
    try:
        avg_vector = calculate_average(data.token_embeddings)
        return {"token_average_embedding": avg_vector}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/aggregate/ndjson")
async def aggregate_ndjson(file: UploadFile = File(...)):
    """
    Processa um arquivo NDJSON, calcula a média e remove campos pesados.
    """

    if not file.filename.endswith(('.ndjson', '.jsonl')):
        raise HTTPException(status_code=400, detail="O arquivo deve ser .ndjson")


    contents = await file.read()

    lines = contents.decode("utf-8").splitlines()
    
    output_lines = []
    it = iter(lines)
    
    for action_line in it:
        try:
            data_line = next(it)
            
            action_obj = json.loads(action_line)
            data_obj = json.loads(data_line)

            
            token_embs = data_obj.get("token_embeddings", [])
            
            if token_embs:
                # Calcula a média
                avg_vector = calculate_average(token_embs)
                data_obj["token_average_embedding"] = avg_vector
                

                # Limpeza para economizar banda/espaço (conforme seu script)
                data_obj.pop("token_embeddings", None)
                data_obj.pop("token_text", None)
            
            output_lines.append(action_obj)
            output_lines.append(data_obj)
            
        except StopIteration:
            break
        except Exception:
            continue

    return output_lines


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7000)
