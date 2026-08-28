import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "wpt_manager.db"
ICONS_DIRECTORY = DATA_DIRECTORY / "icons"
CONFIG_PATH = DATA_DIRECTORY / "config.json"

USER_DATA_DIRECTORY_KEY = "user_data_directory"
ORGANIZATION_NAME = "MiVoCz"
DEVELOPMENT_APPLICATION_NAME = "WPT-Manager-Development"
FROZEN_APPLICATION_NAME = "WPT-Manager"


def application_settings_identity() -> tuple[str, str]:
    """Return the stable QSettings identity for the current runtime."""
    application_name = (
        FROZEN_APPLICATION_NAME
        if getattr(sys, "frozen", False)
        else DEVELOPMENT_APPLICATION_NAME
    )
    return ORGANIZATION_NAME, application_name


def configure_application_identity() -> tuple[str, str]:
    """Configure Qt identity before application settings are resolved."""
    organization_name, application_name = application_settings_identity()
    QCoreApplication.setOrganizationName(organization_name)
    QCoreApplication.setApplicationName(application_name)
    return organization_name, application_name


def create_application_settings() -> QSettings:
    organization_name, application_name = application_settings_identity()
    return QSettings(organization_name, application_name)


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
