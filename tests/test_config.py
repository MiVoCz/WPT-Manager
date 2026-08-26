import json

from wpt_manager.config import load_application_config


def test_load_application_config_without_api_key(tmp_path):
    missing_path = tmp_path / "config.json"

    config = load_application_config(missing_path)

    assert config.mapy_api_key is None


def test_load_application_config_with_api_key(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"mapy_api_key": " local-test-key "}),
        encoding="utf-8",
    )

    config = load_application_config(config_path)

    assert config.mapy_api_key == "local-test-key"
