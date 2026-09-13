import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


class FakeLayerMap:
    def __init__(self):
        self.collections = {}
        self.tracks = {"track-kept": object()}

    def show_collection(self, collection_id, waypoints):
        self.collections[collection_id] = list(waypoints)

    def hide_collection(self, collection_id):
        self.collections.pop(collection_id, None)


def test_collection_selection_and_checkbox_visibility_are_independent(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "data.db")
    database.initialize()
    first = Collection("First")
    second = Collection("Second")
    database.save_collection(first)
    database.save_collection(second)
    database.save_waypoint(Waypoint("A", 50, 14), first.id)
    database.save_waypoint(Waypoint("B", 51, 15), second.id)
    window = MainWindow(database, icon_catalog=[])
    fake = FakeLayerMap()
    window.map_window = fake
    items = {
        window.collection_list.item(index).data(Qt.ItemDataRole.UserRole):
        window.collection_list.item(index)
        for index in range(window.collection_list.count())
    }
    items[first.id].setCheckState(Qt.CheckState.Unchecked)
    items[second.id].setCheckState(Qt.CheckState.Unchecked)
    window.collection_list.setCurrentItem(items[first.id])
    assert items[first.id].checkState() == Qt.CheckState.Unchecked
    items[first.id].setCheckState(Qt.CheckState.Checked)
    items[second.id].setCheckState(Qt.CheckState.Checked)
    assert set(fake.collections) == {first.id, second.id}
    items[first.id].setCheckState(Qt.CheckState.Unchecked)
    assert set(fake.collections) == {second.id}
    assert "track-kept" in fake.tracks
    window.map_window = None
    window.close()
    application.processEvents()


def test_delete_collection_removes_only_its_layer(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "data.db")
    database.initialize()
    first = Collection("First")
    second = Collection("Second")
    database.save_collection(first)
    database.save_collection(second)
    window = MainWindow(database, icon_catalog=[])
    fake = FakeLayerMap()
    window.map_window = fake
    for index in range(window.collection_list.count()):
        item = window.collection_list.item(index)
        fake.show_collection(item.data(Qt.ItemDataRole.UserRole), [])
        if item.data(Qt.ItemDataRole.UserRole) == first.id:
            window.collection_list.setCurrentItem(item)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes
    )
    window.delete_collection()
    assert set(fake.collections) == {second.id}
    window.map_window = None
    window.close()
    application.processEvents()
