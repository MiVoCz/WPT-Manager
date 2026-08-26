import importlib
from pathlib import Path

import wpt_manager.paths as application_paths


def test_default_application_paths_do_not_depend_on_working_directory(
    tmp_path,
    monkeypatch,
):
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)

    paths = importlib.reload(application_paths)

    assert paths.PROJECT_ROOT == project_root
    assert paths.DATA_DIRECTORY == project_root / "data"
    assert paths.DATABASE_PATH == project_root / "data" / "wpt_manager.db"
    assert paths.ICONS_DIRECTORY == project_root / "data" / "icons"
    assert not (tmp_path / "data").exists()
