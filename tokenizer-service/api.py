import os
import subprocess
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

app = FastAPI(title="Formula Tokenizer")

GRAMMAR_BIN = os.getenv("GRAMMAR_BIN", os.path.join(os.path.dirname(__file__), "grammar2.6"))


class FormulaRequest(BaseModel):
    formula: str


class ProcessedToken(BaseModel):
    tokens: list[str]


def tokenize(formula: str) -> list[str]:
    result = subprocess.run(
        [GRAMMAR_BIN],
        input=formula,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "grammar2.6 failed")
    return result.stdout.strip().split()


@app.post("/api/formulas/process", response_model=ProcessedToken)
def process_formula(body: FormulaRequest):
    if not body.formula.strip():
        raise HTTPException(status_code=400, detail="A fórmula não pode ser vazia.")
    try:
        return ProcessedToken(tokens=tokenize(body.formula))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao processar a fórmula: {e}")


@app.post("/api/formulas/process-file")
def process_file(file: UploadFile = File(...)):
    content = file.file.read().decode("utf-8")
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    try:
        return [ProcessedToken(tokens=tokenize(formula)) for formula in lines]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
