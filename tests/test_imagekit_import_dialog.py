import os
from datetime import timedelta
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.imagekit_import_dialog import ImageKitImportDialog
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.photos.imagekit import ImageKitAuthenticationError, map_imagekit_asset


@pytest.fixture
def setup(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "imagekit-gui.db")
    database.initialize()
    source = MagicMock()
    source.source_type = "imagekit"
    source.list_photos.return_value = [map_imagekit_asset({
        "fileId": str(i), "name": f"Photo {i}", "fileType": "image",
        "url": f"https://ik.imagekit.io/test/{i}.jpg", "thumbnailUrl": None,
        "embeddedMetadata": {
            "DateTimeOriginal": "2026:09:04 17:46:15", "OffsetTimeOriginal": "+02:00",
            "GPSLatitude": -50.5, "GPSLongitude": -14.25,
            "GPSAltitude": 2101, "GPSAltitudeRef": "Above Sea Level",
        },
    }) for i in range(3)]
    factory = MagicMock(return_value=source)
    monkeypatch.setattr("wpt_manager.gui.imagekit_import_dialog.ImageKitPhotoSource", factory)
    info, error = MagicMock(), MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info)
    monkeypatch.setattr(QMessageBox, "critical", error)
    yield database, source, factory, info, error
    app.processEvents()


def test_load_select_import_and_duplicates(setup):
    database, source, factory, info, error = setup
    dialog = ImageKitImportDialog(database)
    assert dialog.folder_edit.text() == "/"
    assert not dialog.import_button.isEnabled()
    dialog.load_button.click()
    factory.assert_called_once_with(folder="/")
    assert len(dialog.selected_items) == 3
    dialog.list_widget.item(2).setSelected(False)
    dialog.import_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert info.call_args.args[2] == "Imported: 2\nSkipped duplicates: 0"
    photos = database.list_photos()
    assert len(photos) == 2
    for photo in photos:
        assert photo.source_type == "imagekit" and photo.track_uuid is None
        assert photo.external_id in {"0", "1"}
        assert photo.source_url == f"https://ik.imagekit.io/test/{photo.external_id}.jpg"
        assert photo.thumbnail_url is None
        assert (photo.latitude, photo.longitude, photo.altitude) == (-50.5, -14.25, 2101.0)
        assert photo.taken_at.utcoffset() == timedelta(hours=2)
    second = ImageKitImportDialog(database)
    second.load_button.click()
    second.import_button.click()
    assert info.call_args.args[2] == "Imported: 1\nSkipped duplicates: 2"
    assert len(database.list_photos()) == 3
    error.assert_not_called()


def test_folder_change_invalidates_selection_and_empty_load(setup):
    database, source, factory, info, error = setup
    dialog = ImageKitImportDialog(database)
    dialog.load_photos()
    dialog.folder_edit.setText("/ITA_2026/")
    assert not dialog.items and not dialog.import_button.isEnabled()
    dialog.import_photos()
    assert database.list_photos() == []
    source.list_photos.return_value = []
    dialog.load_button.click()
    factory.assert_called_with(folder="/ITA_2026/")
    assert dialog.status_label.text() == "Images found: 0"
    assert not dialog.import_button.isEnabled()


def test_error_does_not_expose_credentials(setup, monkeypatch, caplog):
    database, source, factory, info, error = setup
    key = "private_test_secret"
    monkeypatch.setenv("IMAGEKIT_PRIVATE_KEY", key)
    source.list_photos.side_effect = ImageKitAuthenticationError(key)
    dialog = ImageKitImportDialog(database)
    dialog.load_photos()
    assert not dialog.import_button.isEnabled()
    assert key not in str(error.call_args) + caplog.text
    assert database.list_photos() == []
    factory.assert_called_once_with(folder="/")


def test_main_window_import_button_and_refresh(setup, monkeypatch):
    database, source, factory, info, error = setup
    def execute(dialog):
        dialog.load_photos()
        dialog.import_photos()
        return dialog.result()
    monkeypatch.setattr(ImageKitImportDialog, "exec", execute)
    window = MainWindow(database, icon_catalog=[])
    window.import_imagekit_button.click()
    assert window.photo_model.rowCount() == 3
    assert len(database.list_photos()) == 3
    window.close()
