import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track, TrackPoint


class FakeMap:
    def __init__(self):
        self.shown = set()

    def show_track(self, track, points):
        self.shown.add(track.id)

    def hide_track(self, track_id):
        self.shown.discard(track_id)


def test_adventure_checkbox_controls_single_track_visibility_state(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "visibility.db")
    database.initialize()
    first = Track("First", "first.gpx", [TrackPoint(50, 14, 0)])
    second = Track("Second", "second.gpx", [TrackPoint(51, 15, 0)])
    database.save_track(first)
    database.save_track(second)
    italy = Adventure("Italy")
    favorites = Adventure("Favorites")
    database.save_adventure(italy)
    database.save_adventure(favorites)
    for adventure in (italy, favorites):
        database.add_track_to_adventure(adventure.uuid, first.id)
    database.add_track_to_adventure(italy.uuid, second.id)
    window = MainWindow(database, icon_catalog=[])
    window.map_window = FakeMap()
    adventures = {
        window.adventure_list.item(index).data(Qt.ItemDataRole.UserRole):
        window.adventure_list.item(index)
        for index in range(window.adventure_list.count())
    }
    adventures[italy.uuid].setCheckState(Qt.CheckState.Checked)
    assert window.map_window.shown == {first.id, second.id}
    third = Track("Third", "third.gpx")
    database.save_track(third)
    database.add_track_to_adventure(italy.uuid, third.id)
    window._sync_effective_track_visibility()
    assert third.id not in window.map_window.shown
    database.remove_track_from_adventure(italy.uuid, third.id)
    window._sync_effective_track_visibility()
    assert third.id not in window.map_window.shown
    adventures[italy.uuid].setCheckState(Qt.CheckState.Unchecked)
    assert window.map_window.shown == set()
    for row in range(window.track_model.rowCount()):
        item = window.track_model.item(row, 0)
        if item.data(Qt.ItemDataRole.UserRole) == second.id:
            item.setCheckState(Qt.CheckState.Checked)
            break
    assert window.map_window.shown == {second.id}
    window.map_window = None
    window.close()
    application.processEvents()
