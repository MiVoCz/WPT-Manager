from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "wpt_manager.db"
ICONS_DIRECTORY = DATA_DIRECTORY / "icons"
CONFIG_PATH = DATA_DIRECTORY / "config.json"

USER_DATA_DIRECTORY_KEY = "user_data_directory"


def create_application_settings() -> QSettings:
    return QSettings("WPT-Manager", "WPT-Manager")


def default_user_data_directory() -> Path:
    documents = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    return Path(documents) / "WPT-Manager"


def stored_user_data_directory(settings: QSettings) -> Path | None:
    value = settings.value(USER_DATA_DIRECTORY_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value)


def store_user_data_directory(settings: QSettings, directory: Path) -> None:
    previous = settings.value(USER_DATA_DIRECTORY_KEY)
    settings.setValue(USER_DATA_DIRECTORY_KEY, str(directory))
    settings.sync()
    if settings.status() == QSettings.Status.NoError:
        return
    if previous is None:
        settings.remove(USER_DATA_DIRECTORY_KEY)
    else:
        settings.setValue(USER_DATA_DIRECTORY_KEY, previous)
    settings.sync()
    raise OSError("The user data folder setting could not be saved.")
