"""OS credentials, separate from application preferences and provider UI."""
import os
import sys

import keyring

SERVICE_NAME = "WPT-Manager"
USERNAME = "imagekit_private_key"


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


def get_saved_imagekit_private_key() -> str | None:
    try:
        _prepare_backend()
        value = keyring.get_password(SERVICE_NAME, USERNAME)
        return (value.strip() or None) if value else None
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None


def get_imagekit_private_key() -> str | None:
    """Resolve a nonblank environment key before consulting the OS store."""
    return imagekit_environment_key() or get_saved_imagekit_private_key()


def set_imagekit_private_key(key: str) -> None:
    key = key.strip()
    if not key:
        raise ValueError("Enter a non-empty Private API key.")
    try:
        _prepare_backend()
        keyring.set_password(SERVICE_NAME, USERNAME, key)
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None


def delete_imagekit_private_key() -> None:
    try:
        _prepare_backend()
        if keyring.get_password(SERVICE_NAME, USERNAME) is not None:
            keyring.delete_password(SERVICE_NAME, USERNAME)
    except Exception:
        raise CredentialStoreError("Credential store unavailable") from None
