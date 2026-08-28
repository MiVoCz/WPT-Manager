import sys
import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.gui.user_data_folder_dialog import UserDataFolderDialog
from wpt_manager.io.user_data import initialize_user_data_directory
from wpt_manager.paths import (
    create_application_settings,
    configure_application_identity,
    default_user_data_directory,
    stored_user_data_directory,
    store_user_data_directory,
)


def choose_user_data_directory() -> tuple[Path, QSettings] | None:
    settings = create_application_settings()
    stored_directory = stored_user_data_directory(settings)
    if stored_directory is not None:
        try:
            initialize_user_data_directory(stored_directory)
        except OSError as exc:
            QMessageBox.critical(
                None,
                "User data folder",
                f"The user data folder cannot be used:\n{exc}",
            )
            return None
        return stored_directory, settings

    dialog = UserDataFolderDialog(
        default_user_data_directory(),
        first_run=True,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    directory = dialog.selected_directory.resolve()
    try:
        initialize_user_data_directory(directory)
    except OSError as exc:
        QMessageBox.critical(
            None,
            "User data folder",
            f"The selected folder cannot be used:\n{exc}",
        )
        return None
    store_user_data_directory(settings, directory)
    return directory, settings


def main() -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application = QApplication(sys.argv)
    configure_application_identity()
    selected = choose_user_data_directory()
    if selected is None:
        return 0
    user_data_directory, settings = selected
    database = Database(user_data_directory / "wpt_manager.db")
    database.initialize()
    window = MainWindow(
        database,
        user_data_directory=user_data_directory,
        settings=settings,
    )
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
