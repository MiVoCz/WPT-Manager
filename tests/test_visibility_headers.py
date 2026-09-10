import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.collection import Collection
from wpt_manager.models.track import Track


def _track_item(window, track_id):
    for row in range(window.track_model.rowCount()):
        item = window.track_model.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == track_id:
            return item
    raise AssertionError("Track not found")


def test_collection_header_is_tristate_and_preserves_selection(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "collections.db")
    database.initialize()
    database.save_collection(Collection("A"))
    database.save_collection(Collection("B"))
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(1)
    selected_id = window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    )
    window.collection_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert window.collection_visibility_header.checkState() == (
        Qt.CheckState.PartiallyChecked
    )
    window.collection_visibility_header.click()
    assert all(
        window.collection_list.item(row).checkState() == Qt.CheckState.Checked
        for row in range(window.collection_list.count())
    )
    window.collection_visibility_header.click()
    assert not window._visible_collection_ids
    assert window.collection_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == selected_id
    window.close()
    application.processEvents()


def test_track_header_only_changes_proxy_visible_manual_state(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    garda = Track("Garda", "a.gpx")
    other = Track("Other", "b.gpx")
    database.save_track(garda)
    database.save_track(other)
    window = MainWindow(database, icon_catalog=[])
    window._select_track(garda.id)
    window.track_search_edit.setText("GARDA")
    assert window.track_proxy.rowCount() == 1
    window.track_visibility_header.click()
    assert garda.id in window._visible_track_ids
    assert other.id not in window._visible_track_ids
    assert window._current_track_id() == garda.id
    window.track_search_edit.setText("missing")
    assert window.track_proxy.rowCount() == 0
    assert not window.track_visibility_header.isEnabled()
    assert garda.id in window._visible_track_ids
    window.close()
    application.processEvents()


def test_track_header_respects_standalone_and_adventure_filters(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "filters.db")
    database.initialize()
    standalone = Track("Solo", "solo.gpx")
    member = Track("Member", "member.gpxbots")
    database.save_track(standalone)
    database.save_track(member)
    adventure = Adventure("Italy")
    database.save_adventure(adventure)
    database.add_track_to_adventure(adventure.uuid, member.id)
    window = MainWindow(database, icon_catalog=[])
    window.track_adventure_filter.setCurrentIndex(
        window.track_adventure_filter.findData("standalone")
    )
    window.track_visibility_header.click()
    assert window._visible_track_ids == {standalone.id}
    window.track_adventure_filter.setCurrentIndex(
        window.track_adventure_filter.findData(str(adventure.uuid))
    )
    assert window.track_visibility_header.checkState() == Qt.CheckState.Unchecked
    window.track_visibility_header.click()
    assert window._visible_track_ids == {standalone.id, member.id}
    window.close()
    application.processEvents()


def test_adventure_header_bulk_controls_shared_track_visibility(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "adventures.db")
    database.initialize()
    track = Track("Track", "track.gpx")
    database.save_track(track)
    first = Adventure("First")
    second = Adventure("Second")
    database.save_adventure(first)
    database.save_adventure(second)
    database.add_track_to_adventure(first.uuid, track.id)
    other = Track("Other", "other.gpx")
    database.save_track(other)
    database.add_track_to_adventure(second.uuid, other.id)
    window = MainWindow(database, icon_catalog=[])
    _track_item(window, track.id).setCheckState(Qt.CheckState.Checked)
    # The manually checked Track derives one checked Adventure and one unchecked.
    assert window.adventure_visibility_header.checkState() == (
        Qt.CheckState.PartiallyChecked
    )
    window.adventure_visibility_header.click()
    window.adventure_visibility_header.click()
    assert not window._visible_track_ids
    window.close()
    application.processEvents()
