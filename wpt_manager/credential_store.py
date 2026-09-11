"""OS credentials, separate from application preferences and provider UI."""
import os
import json
from pathlib import Path
import sys

import keyring

SERVICE_NAME = "WPT-Manager"
USERNAME = "imagekit_private_key"
MAPY_USERNAME = "mapy_api_key"


class CredentialStoreError(Exception):
    """The system credential store could not complete an operation."""


def _prepare_backend() -> None:
    # Select the native Windows store explicitly, including in frozen apps.
    # Never allow an installed third-party plaintext backend on Windows.
    if sys.platform == "win32":
        from keyring.backends.Windows import WinVaultKeyring
        if not isinstance(keyring.get_keyring(), WinVaultKeyring):
            keyring.set_keyring(WinVaultKeyring())


def imagekit_environment_key() -> str | None:
    return os.getenv("IMAGEKIT_PRIVATE_KEY", "").strip() or None


def _get_password(username: str) -> str | None:
    try:
        _prepare_backend()
        value = keyring.get_password(SERVICE_NAME, username)
        return (value.strip() or None) if value else None
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None


def get_imagekit_private_key() -> str | None:
    """Resolve a nonblank environment key before consulting the OS store."""
    return imagekit_environment_key() or get_saved_imagekit_private_key()


def _set_password(username: str, key: str) -> None:
    key = key.strip()
    if not key:
        raise ValueError("Enter a non-empty Private API key.")
    try:
        _prepare_backend()
        keyring.set_password(SERVICE_NAME, username, key)
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None


def _delete_password(username: str) -> None:
    try:
        _prepare_backend()
        if keyring.get_password(SERVICE_NAME, username) is not None:
            keyring.delete_password(SERVICE_NAME, username)
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None


def get_saved_imagekit_private_key() -> str | None:
    return _get_password(USERNAME)


def set_imagekit_private_key(key: str) -> None:
    _set_password(USERNAME, key)


def delete_imagekit_private_key() -> None:
    _delete_password(USERNAME)


def mapy_environment_key() -> str | None:
    return os.getenv("MAPY_API_KEY", "").strip() or None


def get_saved_mapy_api_key() -> str | None:
    return _get_password(MAPY_USERNAME)


def set_mapy_api_key(key: str) -> None:
    _set_password(MAPY_USERNAME, key)


def delete_mapy_api_key() -> None:
    _delete_password(MAPY_USERNAME)


def _legacy_path(path: Path | None) -> Path:
    if path is not None:
        return path
    from wpt_manager.paths import CONFIG_PATH
    return CONFIG_PATH


def _legacy_content(path: Path | None) -> dict[str, object]:
    try:
        content = json.loads(_legacy_path(path).read_text(encoding="utf-8"))
        return content if isinstance(content, dict) else {}
    except (OSError, ValueError, UnicodeError, RecursionError):
        # Never include parser exceptions or file contents in diagnostics.
        return {}


def get_legacy_mapy_api_key(path: Path | None = None) -> str | None:
    value = _legacy_content(path).get(MAPY_USERNAME)
    return (value.strip() or None) if isinstance(value, str) else None


def get_mapy_api_key(legacy_path: Path | None = None) -> str | None:
    """Resolve env, OS store, then legacy config, without saving during reads."""
    if key := mapy_environment_key():
        return key
    try:
        saved = get_saved_mapy_api_key()
    except CredentialStoreError:
        if legacy := get_legacy_mapy_api_key(legacy_path):
            return legacy
        raise
    return saved or get_legacy_mapy_api_key(legacy_path)


def migrate_legacy_mapy_api_key(path: Path | None = None) -> bool:
    """Explicit import. Return whether a legacy key remains in the file.

    Existing env/store credentials are never replaced. Mixed configs are left
    untouched; users can remove the obsolete field after verifying the import.
    """
    if mapy_environment_key() or get_saved_mapy_api_key():
        return bool(get_legacy_mapy_api_key(path))
    content = _legacy_content(path)
    value = content.get(MAPY_USERNAME)
    if not isinstance(value, str) or not value.strip():
        return False
    set_mapy_api_key(value)
    # Only clear a secret-only file, and only after successfully storing its key.
    if set(content) == {MAPY_USERNAME} and _legacy_content(path) == content:
        try:
            _legacy_path(path).write_text("{}\n", encoding="utf-8")
        except OSError:
            return True
        return False
    return True
