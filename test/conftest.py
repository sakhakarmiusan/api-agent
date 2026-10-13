# Hand-written. Generated tests in out/ use the `api` fixture.
import httpx
import pytest

import config


@pytest.fixture
def api():
    headers = {"Authorization": f"Bearer {config.TOKEN}"} if config.TOKEN else {}
    with httpx.Client(base_url=config.BASE_URL, headers=headers, timeout=30) as client:
        yield client
