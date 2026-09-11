import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.photo import Photo
from wpt_manager.models.photo_track_match import PhotoTrackMatchStatus as Status
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.photos.auto_assign import (
    apply_photo_matches, auto_assign_photos, match_summary, preview_photo_matches,
)
from wpt_manager.photos.photo_track_matcher import PhotoTrackMatcher


@pytest.fixture
def dataset(tmp_path):
    database = Database(tmp_path / "matching.db")
    database.initialize()
    time = datetime(2026, 9, 4, tzinfo=timezone.utc)
    first = Track("First", "a.gpx", points=[TrackPoint(50, 14, 0, time=time)])
    second = Track("Second", "b.gpx", points=[TrackPoint(50, 14, 0, time=time + timedelta(hours=1))])
    third = Track("Third", "c.gpx", points=[TrackPoint(50, 14, 0, time=time + timedelta(hours=1))])
    tracks = [first, second, third]
    database.save_tracks(tracks)
    photos = [
        Photo("Match", "imagekit", taken_at=time),
        Photo("Ambiguous", "imagekit", taken_at=time + timedelta(hours=1)),
        Photo("Too far", "imagekit", taken_at=time + timedelta(days=1)),
        Photo("Assigned", "imagekit", taken_at=time, track_uuid=second.id),
        Photo("No time", "imagekit"),
    ]
    for photo in photos:
        database.save_photo(photo)
    return database, photos, tracks


def test_preview_apply_summary_and_existing_assignment(dataset):
    database, photos, tracks = dataset
    results = preview_photo_matches(photos, PhotoTrackMatcher(tracks))
    assert database.get_photo(photos[0].id).track_uuid is None
    assert match_summary(results) == (
        "Photos scanned: 5\nMatched: 1\nNo match: 1\nAmbiguous: 1\nNo timestamp: 1\nAlready assigned: 1"
    )
    assert apply_photo_matches(database, results) == 1
    assert database.get_photo(photos[0].id).track_uuid == tracks[0].id
    assert database.get_photo(photos[3].id).track_uuid == tracks[1].id
    for index in (1, 2, 4):
        assert database.get_photo(photos[index].id).track_uuid is None
    saved = database.get_photo(photos[0].id)
    assert saved.latitude is None and saved.longitude is None
    assert saved.taken_at == photos[0].taken_at


@pytest.mark.parametrize("overwrite", [False, True])
def test_auto_assign_overwrite_option(dataset, overwrite):
    database, photos, tracks = dataset
    results = auto_assign_photos(database, photos, PhotoTrackMatcher(tracks), overwrite_existing=overwrite)
    assert results[photos[3].id].status == (Status.MATCHED if overwrite else Status.ALREADY_ASSIGNED)
    assert database.get_photo(photos[3].id).track_uuid == tracks[0 if overwrite else 1].id


def test_assignment_made_after_preview_is_preserved(dataset):
    database, photos, tracks = dataset
    results = preview_photo_matches(photos, PhotoTrackMatcher(tracks))
    photos[0].track_uuid = tracks[2].id
    database.update_photo(photos[0])
    assert apply_photo_matches(database, results) == 0
    assert database.get_photo(photos[0].id).track_uuid == tracks[2].id


@pytest.mark.parametrize("apply", [False, True])
def test_gui_apply_cancel_and_filters(dataset, monkeypatch, apply):
    application = QApplication.instance() or QApplication([])
    database, photos, tracks = dataset
    adventure = Adventure("Trip")
    database.save_adventure(adventure)
    database.add_track_to_adventure(adventure.uuid, tracks[0].id)
    def confirm(dialog):
        assert "Photos scanned: 5" in dialog.text()
        assert "Matched: 1" in dialog.text()
        assert database.get_photo(photos[0].id).track_uuid is None
        return QMessageBox.StandardButton.Apply if apply else QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, "exec", confirm)
    information = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", information)
    window = MainWindow(database, icon_catalog=[])
    window.match_photos_button.click()
    assert database.get_photo(photos[0].id).track_uuid == (tracks[0].id if apply else None)
    if apply:
        assert information.call_args.args[2] == "Matched 1 photos to tracks."
        window.photo_track_filter.setCurrentIndex(window.photo_track_filter.findData(str(tracks[0].id)))
        assert window.photo_proxy.rowCount() == 1
        window.photo_track_filter.setCurrentIndex(0)
        window.photo_adventure_filter.setCurrentIndex(window.photo_adventure_filter.findData(str(adventure.uuid)))
        assert window.photo_proxy.rowCount() == 1
        window.photo_adventure_filter.setCurrentIndex(0)
        window.photo_track_filter.setCurrentIndex(window.photo_track_filter.findData("standalone"))
        assert window.photo_proxy.rowCount() == 3
    else:
        information.assert_not_called()
    window.close()
    application.processEvents()
