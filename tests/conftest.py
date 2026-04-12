import pytest
import requests

BASE_URL = "http://localhost:3000"


def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires running services (search-service, ES, etc.)")


@pytest.fixture(scope="module")
def live_session():
    session = requests.Session()
    try:
        resp = session.get(f"{BASE_URL}/health", timeout=5)
        resp.raise_for_status()
    except Exception:
        pytest.skip("search-service not reachable at localhost:3000")
    yield session
    session.close()
