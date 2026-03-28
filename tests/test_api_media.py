import importlib.util
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "media_api",
    os.path.join(os.path.dirname(__file__), "..", "api-media", "api.py"),
)
media_api = importlib.util.module_from_spec(_spec)
sys.modules["media_api"] = media_api
_spec.loader.exec_module(media_api)

from fastapi.testclient import TestClient

client = TestClient(media_api.app)


def test_aggregate_json():
    embeddings = [[1.0, 2.0, 3.0], [3.0, 4.0, 5.0]]
    resp = client.post("/aggregate/json", json={"token_embeddings": embeddings})
    assert resp.status_code == 200
    avg = resp.json()["token_average_embedding"]
    assert len(avg) == 3
    assert abs(avg[0] - 2.0) < 1e-6
    assert abs(avg[1] - 3.0) < 1e-6
    assert abs(avg[2] - 4.0) < 1e-6


def test_aggregate_json_single_embedding():
    embeddings = [[1.0, 2.0, 3.0]]
    resp = client.post("/aggregate/json", json={"token_embeddings": embeddings})
    assert resp.status_code == 200
    assert resp.json()["token_average_embedding"] == [1.0, 2.0, 3.0]


def test_aggregate_json_empty():
    resp = client.post("/aggregate/json", json={"token_embeddings": []})
    assert resp.status_code == 200
    assert resp.json()["token_average_embedding"] == []
