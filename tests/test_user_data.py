import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.io.user_data import copy_user_data, initialize_user_data_directory
from wpt_manager.main import choose_user_data_directory
from wpt_manager.paths import USER_DATA_DIRECTORY_KEY, stored_user_data_directory


def temporary_settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_first_run_uses_default_and_stores_only_bootstrap_path(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    settings = temporary_settings(tmp_path / "settings.ini")
    selected = tmp_path / "Documents" / "WPT-Manager"

    class AcceptedDialog:
        def __init__(self, current, *, first_run=False):
            assert current == selected
            assert first_run
            self.selected_directory = selected

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.main.create_application_settings", lambda: settings
    )
    monkeypatch.setattr(
        "wpt_manager.main.default_user_data_directory", lambda: selected
    )
    monkeypatch.setattr(
        "wpt_manager.main.UserDataFolderDialog", AcceptedDialog
    )

    result = choose_user_data_directory()

    assert result == (selected.resolve(), settings)
    assert stored_user_data_directory(settings) == selected.resolve()
    assert settings.allKeys() == [USER_DATA_DIRECTORY_KEY]
    assert json.loads((selected / "config.json").read_text()) == {
        "mapy_api_key": ""
    }
    assert (selected / "icons").is_dir()
    application.processEvents()


def test_copy_current_data_copies_only_managed_items(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    initialize_user_data_directory(source)
    (source / "wpt_manager.db").write_bytes(b"database")
    (source / "config.json").write_text(
        '{"mapy_api_key": "secret"}', encoding="utf-8"
    )
    nested = source / "icons" / "Favorites"
    nested.mkdir(parents=True)
    (nested / "marker.svg").write_text("<svg/>", encoding="utf-8")
    (source / "export.gpx").write_text("not copied", encoding="utf-8")
    (source / ".pytest_cache").mkdir()

    copy_user_data(source, target)

    assert (target / "wpt_manager.db").read_bytes() == b"database"
    assert (target / "config.json").read_text(encoding="utf-8") == (
        '{"mapy_api_key": "secret"}'
    )
    assert (target / "icons" / "Favorites" / "marker.svg").is_file()
    assert not (target / "export.gpx").exists()
    assert not (target / ".pytest_cache").exists()


class FolderDialog:
    result = QDialog.DialogCode.Accepted
    selected = Path()

    def __init__(self, current, parent):
        del current, parent
        self.selected_directory = self.selected

    def exec(self):
        return self.result


def create_window(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    source = tmp_path / "source"
    initialize_user_data_directory(source)
    database = Database(source / "wpt_manager.db")
    database.initialize()
    settings = temporary_settings(tmp_path / "settings.ini")
    settings.setValue(USER_DATA_DIRECTORY_KEY, str(source))
    window = MainWindow(
        database,
        icon_catalog=[],
        user_data_directory=source,
        settings=settings,
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.UserDataFolderDialog", FolderDialog
    )
    return application, window, source, settings


def test_change_folder_cancel_changes_nothing(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    FolderDialog.result = QDialog.DialogCode.Rejected
    FolderDialog.selected = tmp_path / "target"

    window.change_user_data_folder()

    assert stored_user_data_directory(settings) == source
    assert not FolderDialog.selected.exists()
    window.close()
    application.processEvents()


def test_use_existing_data_initializes_only_missing_items(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    target = tmp_path / "target"
    target.mkdir()
    existing_database = target / "wpt_manager.db"
    existing_database.write_bytes(b"existing")
    FolderDialog.result = QDialog.DialogCode.Accepted
    FolderDialog.selected = target
    restarts = []
    monkeypatch.setattr(
        window, "_choose_user_data_folder_action", lambda path: "existing"
    )
    monkeypatch.setattr(
        window,
        "_prompt_restart_after_data_folder_change",
        lambda: restarts.append(True),
    )

    window.change_user_data_folder()

    assert existing_database.read_bytes() == b"existing"
    assert (target / "config.json").is_file()
    assert (target / "icons").is_dir()
    assert stored_user_data_directory(settings) == target.resolve()
    assert restarts == [True]
    window.close()
    application.processEvents()


def test_copy_collision_requires_confirmation(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    (source / "config.json").write_text("source", encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    target_config = target / "config.json"
    target_config.write_text("target", encoding="utf-8")
    FolderDialog.result = QDialog.DialogCode.Accepted
    FolderDialog.selected = target
    monkeypatch.setattr(
        window, "_choose_user_data_folder_action", lambda path: "copy"
    )
    confirmations = []
    monkeypatch.setattr(
        window,
        "_confirm_user_data_overwrite",
        lambda path, items: confirmations.append((path, items)) or False,
    )

    window.change_user_data_folder()

    assert confirmations == [(target.resolve(), ["config.json"])]
    assert target_config.read_text(encoding="utf-8") == "target"
    assert stored_user_data_directory(settings) == source
    window.close()
    application.processEvents()


def test_change_folder_copies_data_then_updates_bootstrap(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    (source / "config.json").write_text(
        '{"mapy_api_key": "key"}', encoding="utf-8"
    )
    icon = source / "icons" / "Group" / "marker.svg"
    icon.parent.mkdir()
    icon.write_text("<svg/>", encoding="utf-8")
    database_bytes = (source / "wpt_manager.db").read_bytes()
    target = tmp_path / "target"
    FolderDialog.result = QDialog.DialogCode.Accepted
    FolderDialog.selected = target
    restarts = []
    monkeypatch.setattr(
        window, "_choose_user_data_folder_action", lambda path: "copy"
    )
    monkeypatch.setattr(
        window,
        "_prompt_restart_after_data_folder_change",
        lambda: restarts.append(True),
    )

    window.change_user_data_folder()

    assert (target / "wpt_manager.db").read_bytes() == database_bytes
    assert (target / "config.json").read_text(encoding="utf-8") == (
        '{"mapy_api_key": "key"}'
    )
    assert (target / "icons" / "Group" / "marker.svg").is_file()
    assert stored_user_data_directory(settings) == target.resolve()
    assert window.user_data_directory == source.resolve()
    assert restarts == [True]
    window.close()
    application.processEvents()


def test_copy_failure_keeps_original_bootstrap_path(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    target = tmp_path / "target"
    FolderDialog.result = QDialog.DialogCode.Accepted
    FolderDialog.selected = target
    monkeypatch.setattr(
        window, "_choose_user_data_folder_action", lambda path: "copy"
    )

    def fail_copy(*args, **kwargs):
        raise OSError("copy failed")

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.copy_user_data", fail_copy
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.QMessageBox.critical",
        lambda *args: None,
    )

    window.change_user_data_folder()

    assert stored_user_data_directory(settings) == source
    window.close()
    application.processEvents()
