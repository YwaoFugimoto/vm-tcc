import importlib.util
import os
import sys
from unittest.mock import patch, MagicMock

# Mock elasticsearch before importing the module (it connects at import time)
mock_es = MagicMock()
sys.modules["elasticsearch"] = MagicMock(Elasticsearch=MagicMock(return_value=mock_es))

_spec = importlib.util.spec_from_file_location(
    "search_api",
    os.path.join(os.path.dirname(__file__), "..", "search-service", "api.py"),
)
search_api = importlib.util.module_from_spec(_spec)
sys.modules["search_api"] = search_api
_spec.loader.exec_module(search_api)

from fastapi.testclient import TestClient

client = TestClient(search_api.app)

FAKE_EMBEDDING = [0.1] * 384
FAKE_TOKENS = ["A0270", "A0295"]
FAKE_AVG = [0.05] * 384
FAKE_ES_HITS = {
    "hits": {
        "hits": [
            {"_score": 0.95, "_source": {"formula": "x^2 + y^2"}},
            {"_score": 0.87, "_source": {"formula": "a + b"}},
        ]
    }
}


def _mock_post(url, **kwargs):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if "/embed" in url:
        resp.json.return_value = {"embedding": FAKE_EMBEDDING}
    elif "/api/formulas/process" in url:
        resp.json.return_value = {"tokens": FAKE_TOKENS}
    elif "/aggregate/json" in url:
        resp.json.return_value = {"token_average_embedding": FAKE_AVG}
    return resp


@patch.object(search_api, "requests")
def test_search_direct(mock_requests):
    mock_requests.post.side_effect = _mock_post
    search_api.es.search.return_value = FAKE_ES_HITS
    resp = client.post("/search-formula", json={"mode": "DIRECT", "search_formula": "x^2"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["score"] == 0.95
    assert data[0]["formula"] == "x^2 + y^2"


@patch.object(search_api, "requests")
def test_search_tokenized(mock_requests):
    mock_requests.post.side_effect = _mock_post
    search_api.es.search.return_value = FAKE_ES_HITS
    resp = client.post("/search-formula", json={"mode": "TOKENIZED", "search_formula": "x + y"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@patch.object(search_api, "requests")
def test_search_invalid_mode(mock_requests):
    resp = client.post("/search-formula", json={"mode": "INVALID", "search_formula": "x"})
    assert resp.status_code == 400


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
