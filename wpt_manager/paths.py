from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIRECTORY / "wpt_manager.db"
ICONS_DIRECTORY = DATA_DIRECTORY / "icons"
CONFIG_PATH = DATA_DIRECTORY / "config.json"
