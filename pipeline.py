import json
import argparse
import requests
import urllib3
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

EMBEDDING_SERVICE_URL = "http://localhost:8000/embed"
TOKENIZER_SERVICE_URL = "http://localhost:8080/api/formulas/process"
MEDIA_SERVICE_URL     = "http://localhost:7000/aggregate/json"
ELASTIC_URL           = "https://localhost:9200/_bulk"
ELASTIC_AUTH          = ("elastic", "user123")
DIRECT_INDEX = "formulas_embedding"
TOKEN_INDEX = "formulas_token_embedding_avg"  # NOTE: must match search-service/api.py TOKEN_INDEX and the Elasticsearch index created at bulk time
BATCH_SIZE = 100
FAILED_FILE = "failed_formulas.txt"
UNSENT_DIR = "unsent_batches"


def embed(text: str) -> list[float]:
    response = requests.post(EMBEDDING_SERVICE_URL, json={"text": text})
    response.raise_for_status()
    return response.json()["embedding"]


def average_embeddings(token_embeddings: list[list[float]]) -> list[float]:
    response = requests.post(MEDIA_SERVICE_URL, json={"token_embeddings": token_embeddings})
    response.raise_for_status()
    return response.json()["token_average_embedding"]


def tokenize(formula: str) -> list[str]:
    response = requests.post(TOKENIZER_SERVICE_URL, json={"formula": formula})
    response.raise_for_status()
    return response.json()["tokens"]


def build_bulk_action(index: str, doc_id: int) -> dict:
    return {"index": {"_index": index, "_id": doc_id}}


def run_direct_path(formula: str, doc_id: int) -> list[str]:
    action = json.dumps(build_bulk_action(DIRECT_INDEX, doc_id))
    doc = json.dumps({"formula": formula, "formula_embedding": embed(formula)})
    return [action, doc]


def run_tokenized_path(formula: str, token_list: list[str], doc_id: int) -> list[str]:
    token_embeddings = [embed(token) for token in token_list]
    avg_embedding = average_embeddings(token_embeddings)
    action = json.dumps(build_bulk_action(TOKEN_INDEX, doc_id))
    doc = json.dumps({
        "formula": formula,
        "token_list": token_list,
        "token_average_embedding": avg_embedding,
    })
    return [action, doc]


def send_to_elastic(ndjson_lines: list[str]):
    body = "\n".join(ndjson_lines) + "\n"
    response = requests.post(
        ELASTIC_URL,
        data=body,
        headers={"Content-Type": "application/x-ndjson"},
        auth=ELASTIC_AUTH,
        verify=False,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("errors"):
        failed = [item for item in result["items"] if "error" in list(item.values())[0]]
        print(f"[ERROR] {len(failed)} document(s) failed to index:")
        for item in failed:
            print(json.dumps(item, indent=2))
    else:
        print(f"[OK] {len(result['items'])} document(s) indexed.")


def log_failure(doc_id: int, formula: str, error: str):
    with open(FAILED_FILE, "a") as f:
        f.write(f"{doc_id}\t{formula}\t{error}\n")


def save_unsent_batch(batch_num: int, ndjson_lines: list[str]):
    os.makedirs(UNSENT_DIR, exist_ok=True)
    path = os.path.join(UNSENT_DIR, f"batch_{batch_num}.ndjson")
    with open(path, "w") as f:
        f.write("\n".join(ndjson_lines) + "\n")
    print(f"[SAVED] Unsent batch saved to {path}")


def main(input_file: str, batch_size: int = BATCH_SIZE, start_from: int = 0):
    with open(input_file) as f:
        formulas = [line.strip() for line in f if line.strip()]

    total = len(formulas)
    succeeded = 0
    failed = 0

    if start_from > 0:
        print(f"Resuming from formula {start_from}...")

    print(f"Processing {total - start_from} formula(s) in batches of {batch_size}...")

    for batch_start in range(start_from, total, batch_size):
        batch = formulas[batch_start: batch_start + batch_size]
        ndjson_lines: list[str] = []
        batch_num = batch_start // batch_size + 1
        total_batches = (total - start_from + batch_size - 1) // batch_size

        for offset, formula in enumerate(batch):
            doc_id = batch_start + offset
            try:
                print(f"  [{doc_id + 1}/{total}] direct...", end=" ", flush=True)
                ndjson_lines.extend(run_direct_path(formula, doc_id))
                print("ok.", end=" ", flush=True)

                print("tokenized...", end=" ", flush=True)
                token_list = tokenize(formula)
                ndjson_lines.extend(run_tokenized_path(formula, token_list, doc_id))
                print("ok.")
                succeeded += 1
            except Exception as e:
                print(f"FAILED: {e}")
                log_failure(doc_id, formula, str(e))
                failed += 1

        if ndjson_lines:
            try:
                print(f"Sending batch {batch_num}/{total_batches} to Elasticsearch...")
                send_to_elastic(ndjson_lines)
            except Exception as e:
                print(f"[ERROR] Batch {batch_num} failed to send: {e}")
                save_unsent_batch(batch_num, ndjson_lines)

    print(f"\nPipeline complete. {succeeded} succeeded, {failed} failed.")
    if failed > 0:
        print(f"Failed formulas saved to {FAILED_FILE}")
    if os.path.isdir(UNSENT_DIR) and os.listdir(UNSENT_DIR):
        print(f"Unsent batches saved to {UNSENT_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Formula embedding pipeline")
    parser.add_argument("input_file", help="Path to file with one formula per line")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help=f"Formulas per Elasticsearch bulk request (default: {BATCH_SIZE})")
    parser.add_argument("--start-from", type=int, default=0,
                        help="Skip formulas before this line number (for resuming)")
    args = parser.parse_args()

    main(args.input_file, batch_size=args.batch_size, start_from=args.start_from)
