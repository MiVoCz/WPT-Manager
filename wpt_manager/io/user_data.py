import json
import shutil
import tempfile
from pathlib import Path


DATABASE_FILENAME = "wpt_manager.db"
CONFIG_FILENAME = "config.json"
ICONS_DIRECTORY_NAME = "icons"


def initialize_user_data_directory(directory: Path) -> None:
    """Create a usable user data directory without replacing existing data."""
    directory.mkdir(parents=True, exist_ok=True)
    verify_directory_writable(directory)
    config_path = directory / CONFIG_FILENAME
    if not config_path.exists():
        config_path.write_text(
            json.dumps({"mapy_api_key": ""}, indent=2) + "\n",
            encoding="utf-8",
        )
    (directory / ICONS_DIRECTORY_NAME).mkdir(exist_ok=True)


def verify_directory_writable(directory: Path) -> None:
    """Raise OSError when directory cannot be used for application data."""
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise OSError(f"Not a directory: {directory}")
    with tempfile.NamedTemporaryFile(dir=directory, delete=True):
        pass


def existing_user_data_items(directory: Path) -> list[str]:
    """Return managed target items which already exist."""
    return [
        name
        for name in (
            DATABASE_FILENAME,
            CONFIG_FILENAME,
            ICONS_DIRECTORY_NAME,
        )
        if (directory / name).exists()
    ]


def copy_user_data(source: Path, target: Path, overwrite: bool = False) -> None:
    """Copy only managed user data, preserving the source directory."""
    verify_directory_writable(target)
    collisions = existing_user_data_items(target)
    if collisions and not overwrite:
        raise FileExistsError(
            "Target contains existing user data: " + ", ".join(collisions)
        )

    for filename in (DATABASE_FILENAME, CONFIG_FILENAME):
        source_path = source / filename
        if source_path.is_file():
            shutil.copy2(source_path, target / filename)

    source_icons = source / ICONS_DIRECTORY_NAME
    if source_icons.is_dir():
        shutil.copytree(
            source_icons,
            target / ICONS_DIRECTORY_NAME,
            dirs_exist_ok=overwrite,
        )
    initialize_user_data_directory(target)
