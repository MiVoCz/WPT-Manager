import os
import time
from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from wpt_manager import credential_store as store
from wpt_manager.gui.imagekit_settings_dialog import ImageKitSettingsDialog
from wpt_manager.photos.imagekit import ImageKitPhotoSource
from wpt_manager.photos.imagekit_probe import main


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def http(monkeypatch):
    opener = MagicMock()
    response = opener.open.return_value.__enter__.return_value
    response.status = 200
    response.read.return_value = b'[]'
    monkeypatch.setattr("wpt_manager.photos.imagekit.build_opener", lambda *args: opener)
    return opener.open


def finish(app, dialog):
    deadline = time.monotonic() + 3
    while dialog.worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    assert dialog.worker is None


def test_saved_is_hidden_and_unchanged_save_preserves(app):
    store.keyring.get_password.return_value = "test-private-key"
    dialog = ImageKitSettingsDialog()
    assert dialog.key_edit.text() == ""
    assert dialog.key_edit.placeholderText() == "Saved credential"
    assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    store.keyring.set_password.assert_not_called()
    store.keyring.delete_password.assert_not_called()


def test_new_key_save_and_cancel(app):
    dialog = ImageKitSettingsDialog()
    dialog.key_edit.setText(" test-private-key ")
    dialog.save()
    store.keyring.set_password.assert_called_once_with(store.SERVICE_NAME, store.USERNAME, "test-private-key")
    assert not dialog.key_edit.text()
    store.keyring.set_password.reset_mock()
    dialog = ImageKitSettingsDialog()
    dialog.key_edit.setText("discard-key")
    dialog.reject()
    store.keyring.set_password.assert_not_called()
    assert not dialog.key_edit.text()


@pytest.mark.parametrize("value", [" ", ""])
def test_empty_edited_input_rejected(app, value):
    dialog = ImageKitSettingsDialog()
    dialog.key_edit.setText(value)
    dialog.key_edit.setModified(True)
    dialog.save()
    assert "non-empty" in dialog.status_label.text()
    store.keyring.set_password.assert_not_called()
    store.keyring.delete_password.assert_not_called()


def test_explicit_remove(app):
    store.keyring.get_password.return_value = "test-private-key"
    dialog = ImageKitSettingsDialog()
    dialog.remove_saved_key()
    store.keyring.delete_password.assert_called_once_with(store.SERVICE_NAME, store.USERNAME)


def test_environment_indicated(app, monkeypatch):
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "test-private-key")
    dialog = ImageKitSettingsDialog()
    assert "overrides saved credential" in dialog.environment_label.text()
    assert "test-private-key" not in dialog.environment_label.text()


@pytest.mark.parametrize("operation", ["get_password", "set_password", "delete_password"])
def test_store_failure_ui(app, operation):
    store.keyring.get_password.return_value = "test-private-key"
    dialog = ImageKitSettingsDialog()
    getattr(store.keyring, operation).side_effect = RuntimeError("test-private-key")
    if operation == "get_password":
        dialog = ImageKitSettingsDialog()
    elif operation == "set_password":
        dialog.key_edit.setText("new-key")
        dialog.save()
    else:
        dialog.remove_saved_key()
    assert dialog.status_label.text() == "Credential store unavailable"


@pytest.mark.parametrize("failure,expected", [
    (None, "Connected"),
    (401, "Invalid API key"), (403, "Invalid API key"),
    (TimeoutError("test-private-key"), "Network error"),
    (500, "Unexpected API error"),
    (RuntimeError("test-private-key"), "Unexpected API error"),
])
def test_connection_results(app, http, failure, expected):
    if isinstance(failure, int):
        http.side_effect = HTTPError("https://api.imagekit.io", failure, "test-private-key", {}, BytesIO())
    elif failure:
        http.side_effect = failure
    dialog = ImageKitSettingsDialog()
    dialog.key_edit.setText("test-private-key")
    dialog.test_connection()
    assert not dialog.test_button.isEnabled()
    finish(app, dialog)
    assert dialog.status_label.text() == expected
    assert dialog.test_button.isEnabled()
    store.keyring.set_password.assert_not_called()
    assert http.call_count == 1
    assert parse_qs(urlsplit(http.call_args.args[0].full_url).query)["limit"] == ["1"]


@pytest.mark.parametrize("entered,env,saved,expected", [
    ("new-key", "env-key", "saved-key", "new-key"),
    ("", "env-key", "saved-key", "env-key"),
    ("", None, "saved-key", "saved-key"),
])
def test_test_connection_resolution(app, http, monkeypatch, entered, env, saved, expected):
    import base64
    if env:
        monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", env)
    store.keyring.get_password.return_value = saved
    dialog = ImageKitSettingsDialog()
    dialog.key_edit.setText(entered)
    dialog.test_connection()
    finish(app, dialog)
    assert http.call_args.args[0].get_header("Authorization") == (
        "Basic " + base64.b64encode((expected + ":").encode()).decode()
    )


def test_missing_and_store_failure_connection(app, http):
    dialog = ImageKitSettingsDialog()
    dialog.test_connection()
    assert dialog.status_label.text() == "Not configured"
    store.keyring.get_password.side_effect = RuntimeError("test-private-key")
    dialog.test_connection()
    assert dialog.status_label.text() == "Credential store unavailable"
    http.assert_not_called()


def test_probe_saved_key_and_redaction(http, capsys):
    store.keyring.get_password.return_value = "test-private-key"
    http.return_value.__enter__.return_value.read.return_value = (
        b'[{"fileId":"1","name":"test-private-key","fileType":"image"}]'
    )
    assert main([]) == 0
    assert "test-private-key" not in capsys.readouterr().out


def test_probe_missing_and_store_failure(capsys):
    assert main([]) == 1
    assert capsys.readouterr().out.strip() == "ImageKit private API key is not configured."
    store.keyring.get_password.side_effect = RuntimeError("test-private-key")
    assert main([]) == 1
    assert capsys.readouterr().out.strip() == "Credential store unavailable"


def test_source_uses_saved_key(http):
    store.keyring.get_password.return_value = "test-private-key"
    assert ImageKitPhotoSource().list_photos() == []
    store.keyring.get_password.assert_called_once_with(store.SERVICE_NAME, store.USERNAME)


@pytest.mark.parametrize("mode", ["saved", "environment", "missing", "unavailable"])
def test_import_dialog_real_resolver(app, http, tmp_path, monkeypatch, mode):
    from PySide6.QtWidgets import QMessageBox
    from wpt_manager.database.database import Database
    from wpt_manager.gui.imagekit_import_dialog import ImageKitImportDialog
    database = Database(tmp_path / "import.db")
    database.initialize()
    error = MagicMock()
    monkeypatch.setattr(QMessageBox, "critical", error)
    if mode == "saved":
        store.keyring.get_password.return_value = "test-private-key"
    elif mode == "environment":
        monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", "test-private-key")
        store.keyring.get_password.side_effect = RuntimeError("store unavailable")
    elif mode == "unavailable":
        store.keyring.get_password.side_effect = RuntimeError("test-private-key")
    dialog = ImageKitImportDialog(database)
    dialog.load_photos()
    if mode in {"saved", "environment"}:
        assert dialog.source is not None
        http.assert_called_once()
        error.assert_not_called()
    else:
        assert dialog.source is None
        http.assert_not_called()
        error.assert_called_once()
        assert "test-private-key" not in str(error.call_args)


def test_settings_menu_opens_dialog(app, tmp_path, monkeypatch):
    from wpt_manager.database.database import Database
    from wpt_manager.gui.main_window import MainWindow
    execute = MagicMock(return_value=0)
    monkeypatch.setattr(ImageKitSettingsDialog, "exec", execute)
    database = Database(tmp_path / "settings.db")
    database.initialize()
    window = MainWindow(database, icon_catalog=[])
    window.imagekit_settings_action.trigger()
    execute.assert_called_once()
    window.close()
