import importlib.util
import os
import sys
from unittest.mock import patch, MagicMock

# Import tokenizer api.py under a unique module name
_spec = importlib.util.spec_from_file_location(
    "tokenizer_api",
    os.path.join(os.path.dirname(__file__), "..", "tokenizer-service", "api.py"),
)
tokenizer_api = importlib.util.module_from_spec(_spec)
sys.modules["tokenizer_api"] = tokenizer_api
_spec.loader.exec_module(tokenizer_api)

from fastapi.testclient import TestClient

client = TestClient(tokenizer_api.app)


@patch.object(tokenizer_api, "subprocess")
def test_process_formula(mock_subprocess):
    mock_subprocess.run.return_value = MagicMock(
        returncode=0, stdout="A0270 A0295 A0917\n", stderr=""
    )
    resp = client.post("/api/formulas/process", json={"formula": "x + y"})
    assert resp.status_code == 200
    assert resp.json() == {"tokens": ["A0270", "A0295", "A0917"]}


@patch.object(tokenizer_api, "subprocess")
def test_process_formula_empty(mock_subprocess):
    resp = client.post("/api/formulas/process", json={"formula": "   "})
    assert resp.status_code == 400


@patch.object(tokenizer_api, "subprocess")
def test_process_formula_grammar_fails(mock_subprocess):
    mock_subprocess.run.return_value = MagicMock(
        returncode=1, stdout="", stderr="parse error"
    )
    resp = client.post("/api/formulas/process", json={"formula": "bad input"})
    assert resp.status_code == 500


@patch.object(tokenizer_api, "subprocess")
def test_process_file(mock_subprocess):
    mock_subprocess.run.return_value = MagicMock(
        returncode=0, stdout="A0270 A0295\n", stderr=""
    )
    content = b"x + y\na + b\n"
    resp = client.post(
        "/api/formulas/process-file",
        files={"file": ("formulas.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["tokens"] == ["A0270", "A0295"]


@patch.object(tokenizer_api, "subprocess")
def test_process_file_empty(mock_subprocess):
    resp = client.post(
        "/api/formulas/process-file",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
