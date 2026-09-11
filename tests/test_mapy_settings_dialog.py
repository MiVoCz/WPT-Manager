import os
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal, QUrlQuery
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest, QNetworkAccessManager
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from wpt_manager import credential_store as store
from wpt_manager.gui.imagekit_settings_dialog import ImageKitSettingsDialog
from wpt_manager.gui.map_window import MapWindow
from wpt_manager.mapy_search import MapySearchClient


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def vault(monkeypatch):
    values = {}
    monkeypatch.setattr(store.keyring, "get_password", MagicMock(side_effect=lambda service, name: values.get(name)))
    monkeypatch.setattr(store.keyring, "set_password", MagicMock(side_effect=lambda service, name, key: values.update({name: key})))
    monkeypatch.setattr(store.keyring, "delete_password", MagicMock(side_effect=lambda service, name: values.pop(name, None)))
    return values


class Reply(QObject):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.status = 200
        self.network_error = QNetworkReply.NetworkError.NoError
        self.body = b'{"items":[]}'
        self.deleted = False

    def attribute(self, attribute):
        return self.status

    def error(self):
        return self.network_error

    def readAll(self):
        return self.body

    def deleteLater(self):
        self.deleted = True


@pytest.fixture
def http(monkeypatch):
    reply = Reply()
    request = MagicMock(return_value=reply)
    monkeypatch.setattr(QNetworkAccessManager, "get", request)
    return request, reply


def test_shared_mapy_form_mask_save_unchanged_and_remove(app, vault):
    vault[store.MAPY_USERNAME] = "test-mapy-key"
    dialog = ImageKitSettingsDialog(provider="mapy")
    assert "Mapy.com" in dialog.windowTitle()
    assert dialog.key_edit.text() == ""
    assert dialog.key_edit.placeholderText() == "Saved credential"
    assert dialog.key_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    store.keyring.set_password.assert_not_called()
    store.keyring.delete_password.assert_not_called()
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.remove_button.click()
    assert store.MAPY_USERNAME not in vault
    assert dialog.status_label.text() == "Not configured"


def test_save_new_key_and_cancel(app, vault):
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.key_edit.setText(" test-mapy-key ")
    dialog.save()
    assert vault[store.MAPY_USERNAME] == "test-mapy-key"
    assert not dialog.key_edit.text()
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.key_edit.setText("discard-key")
    dialog.reject()
    assert vault[store.MAPY_USERNAME] == "test-mapy-key"
    assert not dialog.key_edit.text()


@pytest.mark.parametrize("value", ["", " "])
def test_empty_new_value_not_saved_or_tested(app, http, value):
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.key_edit.setText(value)
    dialog.key_edit.setModified(True)
    dialog.save()
    assert "non-empty" in dialog.status_label.text()
    dialog.test_connection()
    assert "non-empty" in dialog.status_label.text()
    http[0].assert_not_called()
    store.keyring.set_password.assert_not_called()


def test_env_indication(app, monkeypatch, vault):
    monkeypatch.setenv("MAPY_API_KEY", "test-mapy-key")
    dialog = ImageKitSettingsDialog(provider="mapy")
    assert "Mapy.com API key is currently provided by environment variable." in dialog.environment_label.text()
    assert "overrides saved credential" in dialog.environment_label.text()
    assert "test-mapy-key" not in dialog.environment_label.text()


def test_explicit_legacy_import_ui(app, tmp_path, vault):
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":"legacy-key"}', encoding="utf-8")
    dialog = ImageKitSettingsDialog(provider="mapy", legacy_path=path)
    assert dialog.migrate_button.isEnabled()
    assert not dialog.key_edit.text()
    assert "legacy-key" not in dialog.legacy_label.text()
    assert not vault
    dialog.migrate_button.click()
    assert vault[store.MAPY_USERNAME] == "legacy-key"
    assert dialog.key_edit.placeholderText() == "Saved credential"
    assert not dialog.migrate_button.isEnabled()
    dialog.remove_saved_key()
    assert dialog.status_label.text() == "Not configured"


def test_mixed_legacy_reminder_after_remove(app, tmp_path, vault):
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":"legacy-key","other":42}', encoding="utf-8")
    dialog = ImageKitSettingsDialog(provider="mapy", legacy_path=path)
    dialog.import_legacy_key()
    dialog.remove_saved_key()
    assert "fallback even after Remove saved key" in dialog.legacy_label.text()
    assert store.get_mapy_api_key(path) == "legacy-key"


@pytest.mark.parametrize("operation", ["get_password", "set_password", "delete_password"])
def test_store_failure_ui(app, vault, operation):
    vault[store.MAPY_USERNAME] = "test-mapy-key"
    dialog = ImageKitSettingsDialog(provider="mapy")
    getattr(store.keyring, operation).side_effect = RuntimeError("test-mapy-key")
    if operation == "get_password":
        dialog = ImageKitSettingsDialog(provider="mapy")
    elif operation == "set_password":
        dialog.key_edit.setText("new-key")
        dialog.save()
    else:
        dialog.remove_saved_key()
    assert dialog.status_label.text() == "Credential store unavailable"


@pytest.mark.parametrize("status,error,body,expected", [
    (200, QNetworkReply.NetworkError.NoError, b'{"items":[]}', "Connected"),
    (401, QNetworkReply.NetworkError.AuthenticationRequiredError, b'test-mapy-key', "Invalid API key"),
    (403, QNetworkReply.NetworkError.ContentAccessDenied, b'test-mapy-key', "Invalid API key"),
    (None, QNetworkReply.NetworkError.TimeoutError, b'', "Network error"),
    (None, QNetworkReply.NetworkError.ConnectionRefusedError, b'', "Network error"),
    (500, QNetworkReply.NetworkError.InternalServerError, b'test-mapy-key', "Unexpected API error"),
    (302, QNetworkReply.NetworkError.NoError, b'', "Unexpected API error"),
    (200, QNetworkReply.NetworkError.NoError, b'test-mapy-key', "Unexpected API error"),
])
def test_connection_results(app, http, status, error, body, expected):
    request, reply = http
    reply.status, reply.network_error, reply.body = status, error, body
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.key_edit.setText("test-mapy-key")
    dialog.test_connection()
    assert not dialog.test_button.isEnabled()
    assert dialog.status_label.text() == "Testing..."
    dialog.reject()  # The owner remains alive while a request is pending.
    assert dialog.key_edit.text() == "test-mapy-key"
    reply.finished.emit()
    assert dialog.status_label.text() == expected
    assert dialog.test_button.isEnabled()
    assert dialog._mapy_client is None
    assert reply.deleted
    request.assert_called_once()
    req = request.call_args.args[0]
    assert QUrlQuery(req.url()).queryItemValue("limit") == "1"
    assert "test-mapy-key" not in req.url().toString()
    assert bytes(req.rawHeader("X-MAPY-API-KEY")) == b"test-mapy-key"
    assert req.transferTimeout() == 10_000
    assert req.attribute(QNetworkRequest.Attribute.RedirectPolicyAttribute) == QNetworkRequest.RedirectPolicy.ManualRedirectPolicy
    store.keyring.set_password.assert_not_called()


@pytest.mark.parametrize("candidate,env,saved,legacy,expected", [
    ("candidate-key", "env-key", "saved-key", "legacy-key", "candidate-key"),
    ("", "env-key", "saved-key", "legacy-key", "env-key"),
    ("", None, "saved-key", "legacy-key", "saved-key"),
    ("", None, None, "legacy-key", "legacy-key"),
])
def test_connection_key_source_no_implicit_save(app, http, tmp_path, vault, monkeypatch, candidate, env, saved, legacy, expected):
    path = tmp_path / "config.json"
    path.write_text('{"mapy_api_key":"legacy-key"}', encoding="utf-8")
    if env:
        monkeypatch.setenv("MAPY_API_KEY", env)
    vault[store.MAPY_USERNAME] = saved
    dialog = ImageKitSettingsDialog(provider="mapy", legacy_path=path)
    dialog.key_edit.setText(candidate)
    dialog.test_connection()
    assert bytes(http[0].call_args.args[0].rawHeader("X-MAPY-API-KEY")) == expected.encode()
    http[1].finished.emit()
    store.keyring.set_password.assert_not_called()
    assert "legacy-key" in path.read_text(encoding="utf-8")


def test_missing_and_unavailable_connection(app, http):
    dialog = ImageKitSettingsDialog(provider="mapy")
    dialog.test_connection()
    assert dialog.status_label.text() == "Not configured"
    store.keyring.get_password.side_effect = RuntimeError("test-mapy-key")
    dialog.test_connection()
    assert dialog.status_label.text() == "Credential store unavailable"
    http[0].assert_not_called()


@pytest.mark.parametrize("source", ["env", "saved", "legacy"])
def test_tiles_and_search_same_resolver(app, http, tmp_path, vault, monkeypatch, source):
    path = tmp_path / "config.json"
    if source == "env":
        monkeypatch.setenv("MAPY_API_KEY", "test-mapy-key")
    elif source == "saved":
        vault[store.MAPY_USERNAME] = "test-mapy-key"
    else:
        path.write_text('{"mapy_api_key":"test-mapy-key"}', encoding="utf-8")
    window = MapWindow(legacy_config_path=path)
    assert "test-mapy-key" in window.waypoint_map._map_source_payload["tileUrl"]
    window.search_client.search("Prague")
    assert bytes(http[0].call_args.args[0].rawHeader("X-MAPY-API-KEY")) == b"test-mapy-key"
    http[1].finished.emit()
    window.close()


def test_provider_switch_and_live_removal(app, vault):
    window = MapWindow()
    initial = window.waypoint_map._map_source_payload.copy()
    window.map_source_combo.setCurrentIndex(window.map_source_combo.findData("mapy-basic"))
    assert window.map_source_combo.currentData() == "openstreetmap"
    assert window.waypoint_map._map_source_payload == initial
    assert "Settings -> Mapy.com" in window.map_source_status.text()
    vault[store.MAPY_USERNAME] = "test-mapy-key"
    window.refresh_credentials()
    assert window.search_button.isEnabled()
    window.map_source_combo.setCurrentIndex(window.map_source_combo.findData("mapy-basic"))
    assert window.waypoint_map._map_source_payload["id"] == "mapy-basic"
    vault.clear()
    window.refresh_credentials()
    assert window.map_source_combo.currentData() == "openstreetmap"
    assert window.waypoint_map._map_source_payload["id"] == "openstreetmap"
    assert not window.search_button.isEnabled()
    window.close()


def test_osm_switch_even_with_failed_store(app, vault):
    vault[store.MAPY_USERNAME] = "test-mapy-key"
    window = MapWindow()
    store.keyring.get_password.side_effect = RuntimeError("test-mapy-key")
    window.map_source_combo.setCurrentIndex(window.map_source_combo.findData("openstreetmap"))
    assert window.waypoint_map._map_source_payload["id"] == "openstreetmap"
    assert "Credential store unavailable" in window.map_source_status.text()
    window.close()


def test_search_re_resolves_on_each_request(app, http, vault):
    client = MapySearchClient()
    vault[store.MAPY_USERNAME] = "first-key"
    client.search("Prague")
    assert bytes(http[0].call_args.args[0].rawHeader("X-MAPY-API-KEY")) == b"first-key"
    vault[store.MAPY_USERNAME] = "second-key"
    client.search("Brno")
    assert bytes(http[0].call_args.args[0].rawHeader("X-MAPY-API-KEY")) == b"second-key"


def test_mapy_settings_menu_uses_selected_data_path(app, tmp_path, monkeypatch):
    from wpt_manager.database.database import Database
    from wpt_manager.gui.main_window import MainWindow
    database = Database(tmp_path / "settings.db")
    database.initialize()
    observed = []
    monkeypatch.setattr(ImageKitSettingsDialog, "exec", lambda self: observed.append((self._mapy, self._legacy_path)))
    window = MainWindow(database, icon_catalog=[], user_data_directory=tmp_path)
    window.map_window = MagicMock()
    window.mapy_settings_action.trigger()
    assert observed == [(True, tmp_path / "config.json")]
    window.map_window.refresh_credentials.assert_called_once()
    window.map_window = None
    window.close()


def test_browser_diagnostics_do_not_expose_key(app, caplog):
    from PySide6.QtWebEngineCore import QWebEnginePage
    from wpt_manager.gui.waypoint_map import MapWebPage, MAP_HTML
    page = MapWebPage()
    messages = []
    page.console_message.connect(messages.append)
    page.javaScriptConsoleMessage(
        QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel,
        "failed https://api.mapy.com/tile?apikey=test-mapy-key", 1,
        "https://api.mapy.com/?apikey=test-mapy-key",
    )
    assert "test-mapy-key" not in caplog.text + str(messages)
    assert 'console.error(source.label + " tile failed", url, error)' not in MAP_HTML
