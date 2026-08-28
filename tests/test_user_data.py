import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow, application_restart_command
from wpt_manager.io.user_data import copy_user_data, initialize_user_data_directory
from wpt_manager.main import choose_user_data_directory
from wpt_manager.paths import (
    DEVELOPMENT_APPLICATION_NAME,
    FROZEN_APPLICATION_NAME,
    ORGANIZATION_NAME,
    USER_DATA_DIRECTORY_KEY,
    application_settings_identity,
    stored_user_data_directory,
    store_user_data_directory,
)


def temporary_settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def isolated_identity_settings(tmp_path: Path) -> QSettings:
    organization, application = application_settings_identity()
    return temporary_settings(tmp_path / f"{organization}-{application}.ini")


def test_development_and_frozen_use_distinct_stable_identities(monkeypatch):
    monkeypatch.delattr("sys.frozen", raising=False)
    development_identity = application_settings_identity()
    monkeypatch.setattr("sys.frozen", True, raising=False)
    frozen_identity = application_settings_identity()

    assert development_identity == (
        ORGANIZATION_NAME,
        DEVELOPMENT_APPLICATION_NAME,
    )
    assert frozen_identity == (ORGANIZATION_NAME, FROZEN_APPLICATION_NAME)
    assert development_identity != frozen_identity
    assert "0.1.0" not in frozen_identity[1]


def test_development_user_data_is_not_visible_to_frozen(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delattr("sys.frozen", raising=False)
    development_settings = isolated_identity_settings(tmp_path)
    development_directory = tmp_path / "development-data"
    store_user_data_directory(development_settings, development_directory)

    monkeypatch.setattr("sys.frozen", True, raising=False)
    frozen_settings = isolated_identity_settings(tmp_path)

    assert stored_user_data_directory(development_settings) == (
        development_directory
    )
    assert stored_user_data_directory(frozen_settings) is None


def test_first_and_second_frozen_start_use_production_setting(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr("sys.frozen", True, raising=False)
    settings = isolated_identity_settings(tmp_path)
    selected = tmp_path / "production-data"
    dialog_calls = []

    class AcceptedDialog:
        def __init__(self, current, *, first_run=False):
            dialog_calls.append((current, first_run))
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

    first_result = choose_user_data_directory()
    second_result = choose_user_data_directory()

    assert first_result == (selected.resolve(), settings)
    assert second_result == (selected.resolve(), settings)
    assert dialog_calls == [(selected, True)]
    assert stored_user_data_directory(settings) == selected.resolve()
    application.processEvents()


def test_frozen_restart_preserves_production_bootstrap_setting(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", "WPT-Manager.exe")
    settings = isolated_identity_settings(tmp_path)
    selected = tmp_path / "production-data"
    store_user_data_directory(settings, selected)

    restarted_settings = isolated_identity_settings(tmp_path)

    assert application_restart_command() == ("WPT-Manager.exe", [])
    assert stored_user_data_directory(restarted_settings) == selected


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


def test_development_restart_uses_active_python_package_entry(monkeypatch):
    monkeypatch.delattr("sys.frozen", raising=False)
    monkeypatch.setattr("sys.executable", "active-venv-python")

    assert application_restart_command() == (
        "active-venv-python",
        ["-m", "wpt_manager"],
    )


def test_frozen_restart_uses_executable_directly(monkeypatch):
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", "WPT-Manager.exe")

    assert application_restart_command() == ("WPT-Manager.exe", [])


def test_restart_launches_command_without_main_py_and_closes_windows(
    tmp_path,
    monkeypatch,
):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    del source, settings
    launched = []
    closed = []
    monkeypatch.delattr("sys.frozen", raising=False)
    monkeypatch.setattr("sys.executable", "venv-python.exe")
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.QProcess.startDetached",
        lambda *args: launched.append(args) or (True, 123),
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.QCoreApplication.quit",
        lambda: closed.append("quit"),
    )
    original_close = window.close
    monkeypatch.setattr(window, "close", lambda: closed.append("main"))
    window.map_window = type(
        "FakeMapWindow",
        (),
        {"close": lambda self: closed.append("map")},
    )()

    window._restart_application()

    assert launched == [
        (
            "venv-python.exe",
            ["-m", "wpt_manager"],
            str(Path.cwd()),
        )
    ]
    assert "main.py" not in " ".join(launched[0][1])
    assert closed == ["map", "main", "quit"]
    window.map_window = None
    original_close()
    application.processEvents()


def test_restart_later_does_not_launch_process(tmp_path, monkeypatch):
    application, window, source, settings = create_window(tmp_path, monkeypatch)
    del source, settings
    launches = []
    monkeypatch.setattr(window, "_ask_restart_now", lambda: False)
    monkeypatch.setattr(
        window, "_restart_application", lambda: launches.append(True)
    )

    window._prompt_restart_after_data_folder_change()

    assert launches == []
    window.close()
    application.processEvents()
