import json
import logging
from dataclasses import dataclass
from pathlib import Path

from wpt_manager.paths import CONFIG_PATH


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    mapy_api_key: str | None = None


def load_application_config(path: Path = CONFIG_PATH) -> ApplicationConfig:
    if not path.exists():
        return ApplicationConfig()
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Application configuration could not be loaded: %s", exc)
        return ApplicationConfig()
    if not isinstance(content, dict):
        LOGGER.warning("Application configuration must contain a JSON object.")
        return ApplicationConfig()
    api_key = content.get("mapy_api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        return ApplicationConfig()
    return ApplicationConfig(mapy_api_key=api_key.strip())
