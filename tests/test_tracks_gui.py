import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.collection import Collection
from wpt_manager.models.track import Track, TrackPoint
from wpt_manager.models.waypoint import Waypoint


class FakeMapWindow:
    def __init__(self):
        self.shown = {}
        self.hidden = []
        self.zoomed = []

    def show_track(self, track, points):
        self.shown[track.id] = (track, list(points))

    def hide_track(self, track_id):
        self.shown.pop(track_id, None)
        self.hidden.append(track_id)

    def zoom_to_track(self, track_id):
        self.zoomed.append(track_id)


def track_item(window, track_id):
    for row in range(window.track_model.rowCount()):
        item = window.track_model.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == track_id:
            return item
    raise AssertionError("Track not found")


def test_track_checkboxes_manage_independent_layers_and_keep_waypoints(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    collection = Collection("Places")
    database.save_collection(collection)
    waypoint = Waypoint("Place", 50, 14)
    database.save_waypoint(waypoint, collection.id)
    first = Track("First", "first.gpx", [TrackPoint(50, 14, 0)], point_count=1)
    second = Track("Second", "second.gpx", [TrackPoint(51, 15, 0)], point_count=1)
    database.save_track(first)
    database.save_track(second)

    window = MainWindow(database, icon_catalog=[])
    assert [window.data_tabs.tabText(i) for i in range(3)] == [
        "Collections", "Tracks", "Adventures"
    ]
    assert window.right_panel_stack.currentWidget() is window.right_splitter
    window.data_tabs.setCurrentIndex(1)
    assert window.right_panel_stack.currentWidget() is window.track_editor
    window.collection_list.setCurrentRow(0)
    original_waypoints = list(window._map_waypoints)
    fake_map = FakeMapWindow()
    window.map_window = fake_map

    first_item = track_item(window, first.id)
    second_item = track_item(window, second.id)
    first_item.setCheckState(Qt.CheckState.Checked)
    second_item.setCheckState(Qt.CheckState.Checked)
    assert set(fake_map.shown) == {first.id, second.id}
    first_item.setCheckState(Qt.CheckState.Unchecked)
    assert set(fake_map.shown) == {second.id}
    assert window._map_waypoints == original_waypoints == [waypoint]

    window._select_track(second.id)
    window.zoom_to_selected_track()
    assert fake_map.zoomed == [second.id]
    window.map_window = None
    window.close()
    application.processEvents()


def test_color_change_and_delete_update_only_selected_track(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "tracks.db")
    database.initialize()
    first = Track("First", "first.gpx", [TrackPoint(50, 14, 0)], point_count=1)
    second = Track("Second", "second.gpx", [TrackPoint(51, 15, 0)], point_count=1)
    database.save_track(first)
    database.save_track(second)
    window = MainWindow(database, icon_catalog=[])
    fake_map = FakeMapWindow()
    window.map_window = fake_map
    track_item(window, first.id).setCheckState(Qt.CheckState.Checked)
    track_item(window, second.id).setCheckState(Qt.CheckState.Checked)
    window._select_track(first.id)
    assert window.track_editor.name_edit.text() == "First"
    assert window.track_editor.distance_edit.isReadOnly()
    assert window.track_editor.point_count_edit.isReadOnly()
    window.track_editor.name_edit.setText("Renamed")
    window.track_editor.color_edit.setText("#ABCDEF")
    window.save_track()
    assert database.get_track(first.id).name == "Renamed"
    assert database.get_track(first.id).color == "#ABCDEF"
    assert fake_map.shown[first.id][0].color == "#ABCDEF"
    assert second.id in fake_map.shown
    window.track_table.clearSelection()
    window.track_table.setCurrentIndex(window.track_proxy.index(-1, -1))
    assert window.track_editor.name_edit.text() == ""
    assert not window.track_editor.save_button.isEnabled()

    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    window._select_track(first.id)
    window.delete_selected_track()
    assert database.get_track(first.id) is None
    assert first.id not in fake_map.shown
    assert second.id in fake_map.shown
    window.map_window = None
    window.close()
    application.processEvents()


def test_right_panel_follows_tab_and_preserves_selections(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "layout.db")
    database.initialize()
    collection = Collection("Places")
    database.save_collection(collection)
    waypoint = Waypoint("Place", 50, 14)
    database.save_waypoint(waypoint, collection.id)
    track = Track("Track", "track.gpx")
    database.save_track(track)
    window = MainWindow(database, icon_catalog=[])
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    window._select_track(track.id)
    window.show()
    application.processEvents()

    assert window.right_panel_stack.currentWidget() is window.right_splitter
    assert window.waypoint_panel.isVisible()
    assert window.waypoint_editor.isVisible()
    waypoint_id = window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    )
    track_id = window._current_track_id()

    window.data_tabs.setCurrentIndex(1)
    application.processEvents()
    assert window.right_panel_stack.currentWidget() is window.track_editor
    assert window.track_editor.isVisible()
    assert not window.waypoint_panel.isVisible()
    assert window.track_editor.parentWidget() is window.right_panel_stack

    window.data_tabs.setCurrentIndex(0)
    application.processEvents()
    assert window.right_panel_stack.currentWidget() is window.right_splitter
    assert window.waypoint_panel.isVisible()
    assert window.waypoint_editor.isVisible()
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == waypoint_id
    assert window._current_track_id() == track_id
    window.close()
    application.processEvents()
