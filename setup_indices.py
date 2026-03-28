"""
Creates Elasticsearch indices with proper dense_vector mappings.
Run once before the first pipeline execution.
"""

import requests
import urllib3
import json
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ELASTIC_URL = "https://localhost:9200"
ELASTIC_AUTH = ("elastic", "user123")

INDICES = {
    "formulas_embedding": {
        "settings": {
            "number_of_shards": "1",
            "number_of_replicas": "0",
        },
        "mappings": {
            "properties": {
                "title": {
                    "type": "text",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 256}
                    },
                },
                "formula": {"type": "text"},
                "formula_embedding": {
                    "type": "dense_vector",
                    "dims": 384,
                    "index": True,
                    "similarity": "cosine",
                    "index_options": {
                        "type": "hnsw",
                        "m": 16,
                        "ef_construction": 100,
                    },
                },
            }
        },
    },
    # NOTE: vector field is "token_average_embedding" to match pipeline.py and search-service
    "formulas_token_embedding_avg": {
        "settings": {
            "number_of_shards": "1",
            "number_of_replicas": "0",
        },
        "mappings": {
            "properties": {
                "title": {
                    "type": "text",
                    "fields": {
                        "keyword": {"type": "keyword", "ignore_above": 256}
                    },
                },
                "formula": {"type": "text"},
                "token_list": {"type": "text"},
                "token_average_embedding": {
                    "type": "dense_vector",
                    "dims": 384,
                    "index": True,
                    "similarity": "cosine",
                    "index_options": {
                        "type": "hnsw",
                        "m": 16,
                        "ef_construction": 100,
                    },
                },
            }
        },
    },
}


def create_index(name: str, body: dict):
    url = f"{ELASTIC_URL}/{name}"
    resp = requests.head(url, auth=ELASTIC_AUTH, verify=False)
    if resp.status_code == 200:
        print(f"  {name} — already exists, skipping.")
        return

    resp = requests.put(url, json=body, auth=ELASTIC_AUTH, verify=False)
    if resp.ok:
        print(f"  {name} — created.")
    else:
        print(f"  {name} — FAILED: {resp.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    print("Creating Elasticsearch indices...")
    for name, body in INDICES.items():
        create_index(name, body)
    print("Done.")
