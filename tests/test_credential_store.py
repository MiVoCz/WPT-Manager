import traceback
from unittest.mock import MagicMock

import pytest

from wpt_manager import credential_store as store


@pytest.mark.parametrize("env,saved,expected", [
    (" env-key ", "saved-key", "env-key"),
    (None, " saved-key ", "saved-key"),
    (None, None, None), ("  ", "saved-key", "saved-key"),
    ("", " ", None),
])
def test_priority(monkeypatch, env, saved, expected):
    if env is not None:
        monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", env)
    store.keyring.get_password.return_value = saved
    assert store.get_imagekit_private_key() == expected
    if env and env.strip():
        store.keyring.get_password.assert_not_called()


def test_set_and_delete():
    store.set_imagekit_private_key(" test-private-key ")
    store.keyring.set_password.assert_called_once_with(
        "WPT-Manager", "imagekit_private_key", "test-private-key"
    )
    store.keyring.get_password.return_value = "test-private-key"
    store.delete_imagekit_private_key()
    store.keyring.delete_password.assert_called_once_with("WPT-Manager", "imagekit_private_key")


@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_blank_set(value):
    with pytest.raises(ValueError):
        store.set_imagekit_private_key(value)
    store.keyring.set_password.assert_not_called()


def test_delete_absent_is_noop():
    store.delete_imagekit_private_key()
    store.keyring.delete_password.assert_not_called()


@pytest.mark.parametrize("operation", ["read", "write", "delete", "backend"])
def test_safe_failure(monkeypatch, operation):
    secret = "test-private-key"
    failure = RuntimeError(secret)
    if operation == "backend":
        monkeypatch.setattr(store, "_prepare_backend", MagicMock(side_effect=failure))
    else:
        store.keyring.get_password.return_value = secret
        name = {"read": "get_password", "write": "set_password", "delete": "delete_password"}[operation]
        getattr(store.keyring, name).side_effect = failure
    with pytest.raises(store.CredentialStoreError) as caught:
        if operation == "write":
            store.set_imagekit_private_key(secret)
        elif operation == "delete":
            store.delete_imagekit_private_key()
        else:
            store.get_imagekit_private_key()
    assert secret not in "".join(traceback.format_exception(caught.value))
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "env-key")
    assert store.get_imagekit_private_key() == "env-key"
