from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import setup_indices


@patch("setup_indices.requests.put")
@patch("setup_indices.requests.head")
def test_create_index_new(mock_head, mock_put):
    mock_head.return_value = MagicMock(status_code=404)
    mock_put.return_value = MagicMock(ok=True)

    setup_indices.create_index("test_index", {"settings": {}, "mappings": {}})

    mock_put.assert_called_once()
    call_url = mock_put.call_args[0][0]
    assert "test_index" in call_url


@patch("setup_indices.requests.put")
@patch("setup_indices.requests.head")
def test_create_index_already_exists(mock_head, mock_put, capsys):
    mock_head.return_value = MagicMock(status_code=200)

    setup_indices.create_index("test_index", {"settings": {}, "mappings": {}})

    mock_put.assert_not_called()
    assert "already exists" in capsys.readouterr().out


@patch("setup_indices.sys.exit")
@patch("setup_indices.requests.put")
@patch("setup_indices.requests.head")
def test_create_index_failure(mock_head, mock_put, mock_exit):
    mock_head.return_value = MagicMock(status_code=404)
    mock_put.return_value = MagicMock(ok=False, text="mapping error")

    setup_indices.create_index("bad_index", {"settings": {}, "mappings": {}})

    mock_exit.assert_called_once_with(1)


def test_indices_config():
    assert "formulas_embedding" in setup_indices.INDICES
    assert "formulas_token_embedding_avg" in setup_indices.INDICES

    direct = setup_indices.INDICES["formulas_embedding"]
    assert direct["mappings"]["properties"]["formula_embedding"]["type"] == "dense_vector"
    assert direct["mappings"]["properties"]["formula_embedding"]["dims"] == 384

    token = setup_indices.INDICES["formulas_token_embedding_avg"]
    assert token["mappings"]["properties"]["token_average_embedding"]["type"] == "dense_vector"
    assert token["mappings"]["properties"]["token_average_embedding"]["dims"] == 384
