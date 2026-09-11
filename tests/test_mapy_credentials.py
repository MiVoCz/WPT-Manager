import json
import traceback
from unittest.mock import MagicMock

import pytest

from wpt_manager import credential_store as store


@pytest.fixture
def vault(monkeypatch):
    values = {}
    monkeypatch.setattr(store.keyring, "get_password", MagicMock(side_effect=lambda service, name: values.get(name)))
    monkeypatch.setattr(store.keyring, "set_password", MagicMock(side_effect=lambda service, name, key: values.update({name: key})))
    monkeypatch.setattr(store.keyring, "delete_password", MagicMock(side_effect=lambda service, name: values.pop(name, None)))
    return values


@pytest.mark.parametrize("env,saved,legacy,expected", [
    (" env-key ", "saved-key", "legacy-key", "env-key"),
    (None, " saved-key ", "legacy-key", "saved-key"),
    (None, None, " legacy-key ", "legacy-key"),
    (None, None, None, None),
    (" ", "saved-key", "legacy-key", "saved-key"),
    ("", " ", "legacy-key", "legacy-key"),
    (" ", None, " ", None),
])
def test_priority(tmp_path, monkeypatch, vault, env, saved, legacy, expected):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mapy_api_key": legacy}), encoding="utf-8")
    original = path.read_bytes()
    if env is not None:
        monkeypatch.setenv("MAPY_API_KEY", env)
    vault[store.MAPY_USERNAME] = saved
    assert store.get_mapy_api_key(path) == expected
    assert path.read_bytes() == original
    store.keyring.set_password.assert_not_called()
    if env and env.strip():
        store.keyring.get_password.assert_not_called()


def test_providers_are_independent(vault):
    store.set_imagekit_private_key("test-private-key")
    store.set_mapy_api_key(" test-mapy-key ")
    assert store.get_imagekit_private_key() == "test-private-key"
    assert store.get_mapy_api_key() == "test-mapy-key"
    store.keyring.set_password.assert_called_with("WPT-Manager", "mapy_api_key", "test-mapy-key")
    store.delete_mapy_api_key()
    store.keyring.delete_password.assert_called_once_with("WPT-Manager", "mapy_api_key")
    assert store.get_imagekit_private_key() == "test-private-key"
    assert store.get_mapy_api_key() is None
    store.delete_mapy_api_key()
    assert store.keyring.delete_password.call_count == 1


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_blank_set_rejected(value):
    with pytest.raises(ValueError):
        store.set_mapy_api_key(value)
    store.keyring.set_password.assert_not_called()


@pytest.mark.parametrize("operation", ["get_password", "set_password", "delete_password"])
def test_store_failure_safe(monkeypatch, operation):
    key = "test-mapy-key"
    store.keyring.get_password.return_value = key
    getattr(store.keyring, operation).side_effect = RuntimeError("test-mapy-key")
    with pytest.raises(store.CredentialStoreError) as caught:
        if operation == "set_password":
            store.set_mapy_api_key(key)
        elif operation == "delete_password":
            store.delete_mapy_api_key()
        else:
            store.get_mapy_api_key()
    assert "test-mapy-key" not in "".join(traceback.format_exception(caught.value))
    monkeypatch.setenv("MAPY_API_KEY", "env-key")
    assert store.get_mapy_api_key() == "env-key"


def test_legacy_works_when_store_unavailable(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":"legacy-key"}', encoding="utf-8")
    store.keyring.get_password.side_effect = RuntimeError("test-mapy-key")
    assert store.get_mapy_api_key(path) == "legacy-key"
    store.keyring.set_password.assert_not_called()


@pytest.mark.parametrize("content", [None, "{bad json", '"test-mapy-key"', "[]", '{"mapy_api_key":42}', '{"mapy_api_key":" "}', b"\xff"])
def test_bad_or_missing_legacy_is_normal(tmp_path, content, caplog):
    path = tmp_path / "config.json"
    if isinstance(content, bytes):
        path.write_bytes(content)
    elif content is not None:
        path.write_text(content, encoding="utf-8")
    assert store.get_mapy_api_key(path) is None
    assert store.migrate_legacy_mapy_api_key(path) is False
    assert "test-mapy-key" not in caplog.text


def test_explicit_migration_clears_only_secret_config(tmp_path, vault):
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":" legacy-key "}', encoding="utf-8")
    assert store.get_mapy_api_key(path) == "legacy-key"
    assert not vault
    assert store.migrate_legacy_mapy_api_key(path) is False
    assert vault[store.MAPY_USERNAME] == "legacy-key"
    assert json.loads(path.read_text(encoding="utf-8")) == {}
    assert store.get_mapy_api_key(path) == "legacy-key"
    store.delete_mapy_api_key()
    assert store.get_mapy_api_key(path) is None


def test_mixed_config_preserved_byte_for_byte(tmp_path, vault):
    path = tmp_path / "config.json"
    original = '{ "mapy_api_key": "legacy-key", "other": {"value": 42} }'
    path.write_text(original, encoding="utf-8")
    assert store.migrate_legacy_mapy_api_key(path) is True
    assert path.read_text(encoding="utf-8") == original
    assert vault[store.MAPY_USERNAME] == "legacy-key"


@pytest.mark.parametrize("source", ["env", "saved"])
def test_migration_never_overwrites_existing(tmp_path, vault, monkeypatch, source):
    path = tmp_path / "config.json"
    original = '{"mapy_api_key":"legacy-key"}'
    path.write_text(original, encoding="utf-8")
    if source == "env":
        monkeypatch.setenv("MAPY_API_KEY", "env-key")
    else:
        vault[store.MAPY_USERNAME] = "saved-key"
    assert store.migrate_legacy_mapy_api_key(path) is True
    store.keyring.set_password.assert_not_called()
    assert path.read_text(encoding="utf-8") == original


def test_failed_migration_preserves_legacy(tmp_path, vault):
    path = tmp_path / "config.json"
    original = '{"mapy_api_key":"legacy-key"}'
    path.write_text(original, encoding="utf-8")
    store.keyring.set_password.side_effect = RuntimeError("legacy-key")
    with pytest.raises(store.CredentialStoreError):
        store.migrate_legacy_mapy_api_key(path)
    assert path.read_text(encoding="utf-8") == original
    assert not vault


def test_failed_cleanup_keeps_usable_saved_key(tmp_path, vault, monkeypatch):
    from pathlib import Path
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":"legacy-key"}', encoding="utf-8")
    monkeypatch.setattr(Path, "write_text", MagicMock(side_effect=PermissionError("legacy-key")))
    assert store.migrate_legacy_mapy_api_key(path) is True
    assert store.get_mapy_api_key(path) == "legacy-key"
