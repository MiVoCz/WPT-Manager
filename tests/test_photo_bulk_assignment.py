import os
import sqlite3
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QAbstractItemView

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.gui.photo_table import PHOTO_ID_ROLE
from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track
from wpt_manager.models.adventure import Adventure


@pytest.fixture
def data(tmp_path):
    database = Database(tmp_path / "bulk.db")
    database.initialize()
    tracks = [Track("First", "a.gpx"), Track("Second", "b.gpx")]
    database.save_tracks(tracks)
    photos = [Photo(name, "local", description=f"Description {name}",
                    source_url=f"https://example.invalid/{name}",
                    track_uuid=tracks[0].id if i == 0 else None)
              for i, name in enumerate(("Zulu", "Alpha", "Beta"))]
    for photo in photos:
        database.save_photo(photo)
    return database, tracks, photos


@pytest.fixture
def window(data):
    app = QApplication.instance() or QApplication([])
    database, _, _ = data
    widget = MainWindow(database, icon_catalog=[])
    yield widget
    widget.photo_editor.clear([])
    widget.close()
    app.processEvents()


def select(window, ids):
    selection = window.photo_table.selectionModel()
    selection.clearSelection()
    for row in range(window.photo_proxy.rowCount()):
        index = window.photo_proxy.index(row, 0)
        if index.data(PHOTO_ID_ROLE) in ids:
            selection.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)


def test_selection_transitions_and_preview(window, data):
    _, _, photos = data
    editor = window.photo_editor
    assert window.photo_table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    select(window, [photos[0].id])
    assert editor.name_edit.isEnabled() and not editor.bulk_mode
    old = editor.preview_label._reply
    generation = editor.preview_label._generation
    select(window, [p.id for p in photos[:2]])
    assert editor.bulk_mode and editor.selection_label.text() == "2 photos selected"
    assert not editor.name_edit.isEnabled() and not editor.description_edit.isEnabled()
    assert editor.name_edit.text() == "" and editor.preview_label.isHidden()
    old.abort.assert_called()
    editor.preview_label._finished(old, generation, photos[0].source_url)
    assert editor.preview_label._original.isNull() and editor.bulk_mode
    select(window, [photos[1].id])
    assert editor.name_edit.text() == "Alpha" and editor.name_edit.isEnabled()
    assert not editor.bulk_mode and not editor.preview_label.isHidden()
    select(window, [])
    assert not editor.track_combo.isEnabled() and editor.name_edit.text() == ""
    select(window, [p.id for p in photos])
    select(window, [])
    assert not editor.bulk_mode and not editor.save_button.isEnabled()


def test_mixed_values_explicit_apply_and_proxy_sort(window, data):
    database, tracks, photos = data
    window.photo_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    select(window, [photos[0].id, photos[1].id])
    editor = window.photo_editor
    assert editor.track_combo.currentIndex() == -1
    assert editor.track_combo.placeholderText() == "Multiple values"
    assert not editor.apply_selected_button.isEnabled()
    window.assign_selected_photos_track()
    assert database.get_photo(photos[0].id).track_uuid == tracks[0].id
    editor.track_combo.setCurrentIndex(editor.track_combo.findData(str(tracks[1].id)))
    assert database.get_photo(photos[1].id).track_uuid is None
    editor.apply_selected_button.click()
    for photo in photos[:2]:
        assert database.get_photo(photo.id) == replace(photo, track_uuid=tracks[1].id)
    assert database.get_photo(photos[2].id) == photos[2]
    assert set(window._selected_photo_ids()) == {p.id for p in photos[:2]}
    assert editor.track_combo.currentData() == str(tracks[1].id)


def test_three_photos_to_track_then_standalone(window, data):
    database, tracks, photos = data
    window.photo_table.selectAll()
    editor = window.photo_editor
    editor.track_combo.setCurrentIndex(editor.track_combo.findData(str(tracks[1].id)))
    editor.apply_selected_button.click()
    assert all(p.track_uuid == tracks[1].id for p in database.list_photos())
    assert "Assigned 3 photos" in window.statusBar().currentMessage()
    editor.track_combo.setCurrentIndex(0)
    editor.apply_selected_button.click()
    assert all(p.track_uuid is None for p in database.list_photos())
    assert window.statusBar().currentMessage() == "Set 3 photos as Standalone."


@pytest.mark.parametrize("filter_type", ["track", "adventure", "standalone"])
def test_filter_removes_assigned_rows(window, data, filter_type):
    database, tracks, photos = data
    database.set_photos_track([p.id for p in photos], tracks[0].id if filter_type != "standalone" else None)
    adventure = Adventure("Trip")
    database.save_adventure(adventure)
    database.add_track_to_adventure(adventure.uuid, tracks[0].id)
    window.load_photos()
    if filter_type == "adventure":
        combo = window.photo_adventure_filter
        value = str(adventure.uuid)
    else:
        combo = window.photo_track_filter
        value = str(tracks[0].id) if filter_type == "track" else "standalone"
    combo.setCurrentIndex(combo.findData(value))
    assert window.photo_proxy.rowCount() == 3
    window.photo_table.selectAll()
    window.photo_editor.track_combo.setCurrentIndex(window.photo_editor.track_combo.findData(str(tracks[1].id)))
    window.photo_editor.apply_selected_button.click()
    assert window.photo_proxy.rowCount() == 0
    assert window._selected_photo_ids() == []
    assert not window.photo_editor.track_combo.isEnabled()


def test_database_transaction_and_only_assignment_changes(data, monkeypatch):
    database, tracks, photos = data
    statements = []
    original = database._connect
    def connect():
        connection = original()
        connection.set_trace_callback(statements.append)
        return connection
    monkeypatch.setattr(database, "_connect", connect)
    assert database.set_photos_track([p.id for p in photos], tracks[1].id) == 3
    assert sum(s.startswith("BEGIN") for s in statements) == 1
    assert statements.count("COMMIT") == 1
    for photo in photos:
        assert database.get_photo(photo.id) == replace(photo, track_uuid=tracks[1].id)


def test_database_rolls_back_all_rows_on_failure(data):
    database, tracks, photos = data
    connection = database._connect()
    connection.execute("CREATE TRIGGER reject_bulk BEFORE UPDATE ON photos "
                       "WHEN OLD.name = 'Alpha' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    connection.commit()
    connection.close()
    with pytest.raises(sqlite3.IntegrityError):
        database.set_photos_track([p.id for p in photos], tracks[1].id)
    for photo in photos:
        assert database.get_photo(photo.id) == photo
