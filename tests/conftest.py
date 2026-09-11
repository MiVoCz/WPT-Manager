from unittest.mock import MagicMock

from wpt_manager import credential_store

import pytest
from PySide6.QtNetwork import QNetworkAccessManager


@pytest.fixture(autouse=True)
def mock_preview_downloads(monkeypatch):
    """No Python Qt image request in the test suite may reach a real server."""
    request = MagicMock(side_effect=lambda *args: MagicMock())
    monkeypatch.setattr(QNetworkAccessManager, "get", request)
    return request


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch, tmp_path):
    """Never access the real OS credential store, even in regression tests."""
    monkeypatch.delenv("IMAGEKIT_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("MAPY_API_KEY", raising=False)
    monkeypatch.setattr(credential_store, "_legacy_path", lambda path: path if path is not None else tmp_path / "config.json")
    monkeypatch.setattr(credential_store, "_prepare_backend", lambda: None)
    for name in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(credential_store.keyring, name, MagicMock(return_value=None))
