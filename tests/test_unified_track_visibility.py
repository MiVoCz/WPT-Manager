import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track


def _model_item(model, track_id):
    for row in range(model.rowCount()):
        item = model.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == track_id:
            return item
    raise AssertionError("Track not found")


def test_track_visibility_synchronizes_main_and_adventure_tables(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "visibility.db")
    database.initialize()
    first = Track("First", "first.gpx")
    second = Track("Second", "second.gpx")
    database.save_track(first)
    database.save_track(second)
    italy = Adventure("Italy")
    alps = Adventure("Alps")
    database.save_adventure(italy)
    database.save_adventure(alps)
    database.add_tracks_to_adventure(italy.uuid, [first.id, second.id])
    database.add_track_to_adventure(alps.uuid, first.id)
    window = MainWindow(database, icon_catalog=[])
    adventures = {
        window.adventure_list.item(row).data(Qt.ItemDataRole.UserRole):
        window.adventure_list.item(row)
        for row in range(window.adventure_list.count())
    }
    window.adventure_list.setCurrentItem(adventures[italy.uuid])

    _model_item(window.track_model, first.id).setCheckState(
        Qt.CheckState.Checked
    )
    assert _model_item(
        window.adventure_editor.track_model, first.id
    ).checkState() == Qt.CheckState.Checked
    assert adventures[italy.uuid].checkState() == Qt.CheckState.PartiallyChecked
    assert adventures[alps.uuid].checkState() == Qt.CheckState.Checked

    _model_item(
        window.adventure_editor.track_model, second.id
    ).setCheckState(Qt.CheckState.Checked)
    assert _model_item(
        window.track_model, second.id
    ).checkState() == Qt.CheckState.Checked
    assert adventures[italy.uuid].checkState() == Qt.CheckState.Checked

    adventures[italy.uuid].setCheckState(Qt.CheckState.Unchecked)
    assert window._visible_track_ids == set()
    assert adventures[alps.uuid].checkState() == Qt.CheckState.Unchecked
    assert window.adventure_editor.visibility_header.checkState() == (
        Qt.CheckState.Unchecked
    )
    assert not hasattr(window, "edit_adventure_button")
    assert not hasattr(window, "add_to_adventure_button")
    assert not hasattr(window, "remove_from_adventure_button")
    window.close()
    application.processEvents()


def test_membership_changes_do_not_change_track_visibility(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "membership.db")
    database.initialize()
    track = Track("Track", "track.gpx")
    database.save_track(track)
    adventure = Adventure("Adventure")
    database.save_adventure(adventure)
    window = MainWindow(database, icon_catalog=[])
    window.set_track_visibility(track.id, True)
    database.add_track_to_adventure(adventure.uuid, track.id)
    window.load_tracks()
    window.load_adventures()
    assert window.get_track_visibility(track.id)
    database.remove_track_from_adventure(adventure.uuid, track.id)
    window.load_tracks()
    window.load_adventures()
    assert window.get_track_visibility(track.id)
    window.close()
    application.processEvents()


def test_adventure_track_header_bulk_preserves_selection_and_refreshes_once(
    tmp_path,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "adventure-header.db")
    database.initialize()
    first = Track("First", "first.gpx")
    second = Track("Second", "second.gpx")
    database.save_track(first)
    database.save_track(second)
    adventure = Adventure("Adventure")
    database.save_adventure(adventure)
    database.add_tracks_to_adventure(adventure.uuid, [first.id, second.id])
    window = MainWindow(database, icon_catalog=[])
    window.adventure_list.setCurrentRow(0)
    window.adventure_editor.select_track(first.id)
    window.set_track_visibility(first.id, True)
    assert window.adventure_editor.visibility_header.checkState() == (
        Qt.CheckState.PartiallyChecked
    )

    refresh_count = 0
    original_refresh = window.refresh_map_visibility

    def counted_refresh():
        nonlocal refresh_count
        refresh_count += 1
        original_refresh()

    window.refresh_map_visibility = counted_refresh
    window.adventure_editor.visibility_header.click()

    assert window._visible_track_ids == {first.id, second.id}
    assert window.adventure_editor.selected_track_ids() == [first.id]
    assert _model_item(
        window.track_model, second.id
    ).checkState() == Qt.CheckState.Checked
    assert window.adventure_list.currentItem().checkState() == (
        Qt.CheckState.Checked
    )
    assert refresh_count == 1
    window.close()
    application.processEvents()
