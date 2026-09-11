from unittest.mock import MagicMock

import pytest
from PySide6.QtNetwork import QNetworkAccessManager


@pytest.fixture(autouse=True)
def mock_preview_downloads(monkeypatch):
    """No Python Qt image request in the test suite may reach a real server."""
    request = MagicMock(side_effect=lambda *args: MagicMock())
    monkeypatch.setattr(QNetworkAccessManager, "get", request)
    return request
