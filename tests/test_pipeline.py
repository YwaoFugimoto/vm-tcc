import json
import tempfile
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pipeline


FAKE_EMBEDDING = [0.1] * 384
FAKE_AVG_EMBEDDING = [0.05] * 384
FAKE_TOKENS = ["A0270", "A0295", "A0917"]


def _mock_post(url, **kwargs):
    """Route mocked requests.post calls by URL."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()

    if "/embed" in url:
        resp.json.return_value = {"embedding": FAKE_EMBEDDING}
    elif "/aggregate/json" in url:
        resp.json.return_value = {"token_average_embedding": FAKE_AVG_EMBEDDING}
    elif "/api/formulas/process" in url:
        resp.json.return_value = {"tokens": FAKE_TOKENS}
    elif "/_bulk" in url:
        resp.json.return_value = {"errors": False, "items": [{"index": {"status": 201}}]}
    else:
        raise ValueError(f"Unexpected URL: {url}")

    return resp


# --- Unit tests ---

def test_build_bulk_action():
    result = pipeline.build_bulk_action("my_index", 42)
    assert result == {"index": {"_index": "my_index", "_id": 42}}


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_embed(mock_post):
    result = pipeline.embed("x^2")
    assert result == FAKE_EMBEDDING
    mock_post.assert_called_once()


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_tokenize(mock_post):
    result = pipeline.tokenize("x + y")
    assert result == FAKE_TOKENS


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_average_embeddings(mock_post):
    result = pipeline.average_embeddings([FAKE_EMBEDDING, FAKE_EMBEDDING])
    assert result == FAKE_AVG_EMBEDDING


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_run_direct_path(mock_post):
    lines = pipeline.run_direct_path("x^2", 0)
    assert len(lines) == 2
    action = json.loads(lines[0])
    doc = json.loads(lines[1])
    assert action["index"]["_index"] == "formulas_embedding"
    assert action["index"]["_id"] == 0
    assert doc["formula"] == "x^2"
    assert doc["formula_embedding"] == FAKE_EMBEDDING


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_run_tokenized_path(mock_post):
    lines = pipeline.run_tokenized_path("x^2", FAKE_TOKENS, 0)
    assert len(lines) == 2
    action = json.loads(lines[0])
    doc = json.loads(lines[1])
    assert action["index"]["_index"] == "formulas_token_embedding_avg"
    assert doc["formula"] == "x^2"
    assert doc["token_list"] == FAKE_TOKENS
    assert doc["token_average_embedding"] == FAKE_AVG_EMBEDDING


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_send_to_elastic(mock_post, capsys):
    lines = ['{"index":{"_index":"test","_id":0}}', '{"formula":"x"}']
    pipeline.send_to_elastic(lines)
    captured = capsys.readouterr()
    assert "[OK]" in captured.out


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_send_to_elastic_reports_errors(mock_post, capsys):
    def error_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "errors": True,
            "items": [{"index": {"status": 400, "error": {"reason": "bad mapping"}}}],
        }
        return resp

    mock_post.side_effect = error_post
    lines = ['{"index":{"_index":"test","_id":0}}', '{"formula":"x"}']
    pipeline.send_to_elastic(lines)
    captured = capsys.readouterr()
    assert "[ERROR]" in captured.out


# --- Integration test: main() end-to-end with mocked HTTP ---

@patch("pipeline.requests.post", side_effect=_mock_post)
def test_main_end_to_end(mock_post, capsys):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("x^2\n")
        f.write("a + b\n")
        f.write("\n")  # blank line should be skipped
        tmp_path = f.name

    try:
        pipeline.main(tmp_path, batch_size=2)
        captured = capsys.readouterr()
        assert "Processing 2 formula(s)" in captured.out
        assert "Pipeline complete." in captured.out

        # Verify tokenize was called for every formula (both paths always run)
        tokenize_calls = [
            c for c in mock_post.call_args_list
            if "/api/formulas/process" in str(c)
        ]
        assert len(tokenize_calls) == 2
    finally:
        os.unlink(tmp_path)


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_main_multiple_batches(mock_post, capsys):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for i in range(5):
            f.write(f"formula_{i}\n")
        tmp_path = f.name

    try:
        pipeline.main(tmp_path, batch_size=2)
        captured = capsys.readouterr()
        assert "batch 1/3" in captured.out.lower()
        assert "batch 3/3" in captured.out.lower()
        assert "Pipeline complete." in captured.out
    finally:
        os.unlink(tmp_path)


@patch("pipeline.requests.post")
def test_main_continues_on_formula_failure(mock_post, capsys, tmp_path):
    """If one formula fails, the pipeline skips it and continues."""
    call_count = [0]

    def _mock_with_failure(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        if "/embed" in url:
            call_count[0] += 1
            # Fail on the 1st embed call (formula 0 direct path)
            if call_count[0] == 1:
                resp.raise_for_status.side_effect = Exception("connection timeout")
                return resp
            resp.json.return_value = {"embedding": FAKE_EMBEDDING}
        elif "/aggregate/json" in url:
            resp.json.return_value = {"token_average_embedding": FAKE_AVG_EMBEDDING}
        elif "/api/formulas/process" in url:
            resp.json.return_value = {"tokens": FAKE_TOKENS}
        elif "/_bulk" in url:
            resp.json.return_value = {"errors": False, "items": [{"index": {"status": 201}}]}
        return resp

    mock_post.side_effect = _mock_with_failure

    input_file = tmp_path / "formulas.txt"
    input_file.write_text("bad_formula\ngood_formula\n")

    failed_file = os.path.join(os.getcwd(), pipeline.FAILED_FILE)
    try:
        pipeline.main(str(input_file), batch_size=10)
        captured = capsys.readouterr()
        assert "1 succeeded, 1 failed" in captured.out
        assert os.path.exists(failed_file)
        with open(failed_file) as f:
            content = f.read()
        assert "bad_formula" in content
    finally:
        if os.path.exists(failed_file):
            os.unlink(failed_file)


@patch("pipeline.requests.post")
def test_main_saves_unsent_batch_on_elastic_failure(mock_post, capsys, tmp_path):
    """If Elasticsearch is down, the batch is saved to disk."""

    def _mock_elastic_down(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()

        if "/embed" in url:
            resp.json.return_value = {"embedding": FAKE_EMBEDDING}
        elif "/aggregate/json" in url:
            resp.json.return_value = {"token_average_embedding": FAKE_AVG_EMBEDDING}
        elif "/api/formulas/process" in url:
            resp.json.return_value = {"tokens": FAKE_TOKENS}
        elif "/_bulk" in url:
            raise ConnectionError("Elasticsearch is down")
        return resp

    mock_post.side_effect = _mock_elastic_down

    input_file = tmp_path / "formulas.txt"
    input_file.write_text("x^2\n")

    unsent_dir = os.path.join(os.getcwd(), pipeline.UNSENT_DIR)
    try:
        pipeline.main(str(input_file), batch_size=10)
        captured = capsys.readouterr()
        assert "1 succeeded, 0 failed" in captured.out
        assert "[SAVED]" in captured.out
        assert os.path.isdir(unsent_dir)
    finally:
        import shutil
        if os.path.isdir(unsent_dir):
            shutil.rmtree(unsent_dir)


@patch("pipeline.requests.post", side_effect=_mock_post)
def test_main_start_from(mock_post, capsys):
    """--start-from skips formulas before the given index."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for i in range(5):
            f.write(f"formula_{i}\n")
        tmp_path = f.name

    try:
        pipeline.main(tmp_path, batch_size=100, start_from=3)
        captured = capsys.readouterr()
        assert "Processing 2 formula(s)" in captured.out
        assert "2 succeeded, 0 failed" in captured.out
    finally:
        os.unlink(tmp_path)
