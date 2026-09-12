"""Python-side contracts for marker identity and collection content changes."""
import os
from unittest.mock import MagicMock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui import main_window as gui
from wpt_manager.gui.waypoint_map import MAP_HTML, WaypointMap
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint


@pytest.fixture
def scene(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / "map.db")
    db.initialize()
    collections = [Collection("A"), Collection("B")]
    points = [Waypoint("Point A", 50, 14), Waypoint("Point B", 51, 15)]
    for collection, point in zip(collections, points):
        db.save_collection(collection)
        db.save_waypoint(point, collection.id)
    window = gui.MainWindow(db, icon_catalog=[])
    layers = {}
    map_window = MagicMock()
    map_window.show_collection.side_effect = lambda uid, wpts: layers.update({uid: wpts})
    map_window.hide_collection.side_effect = lambda uid: layers.pop(uid, None)
    window.map_window = map_window
    monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(window, "_confirm_waypoint_move", lambda *args: True)
    for name in ("show", "showNormal", "raise_", "activateWindow"):
        monkeypatch.setattr(window, name, lambda: None)
    window._refresh_map_collections({c.id for c in collections})
    window._select_waypoint_from_map(points[0].id)
    yield window, db, collections, points, layers
    window.map_window = None
    window.close()
    app.processEvents()


def hide(window, row):
    window.collection_list.item(row).setCheckState(Qt.CheckState.Unchecked)


@pytest.mark.parametrize("visible", [True, False])
def test_save_preserves_visibility(scene, visible):
    window, db, collections, points, layers = scene
    if not visible:
        hide(window, 0)
    window.name_edit.setText("Changed")
    window.save_waypoint()
    assert db.get_waypoint(points[0].id).name == "Changed"
    assert (collections[0].id in layers) is visible
    if visible:
        assert layers[collections[0].id][0].name == "Changed"


@pytest.mark.parametrize("visible", [True, False])
def test_add_to_other_collection(scene, monkeypatch, visible):
    window, db, collections, points, layers = scene
    if not visible:
        hide(window, 1)
    new = Waypoint("New B", 52, 16)
    dialog = MagicMock(waypoint=new, collection_id=collections[1].id)
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    monkeypatch.setattr(gui, "NewWaypointDialog", lambda *args, **kwargs: dialog)
    window.add_waypoint_from_map(52, 16)
    assert db.get_waypoint(new.id) == new
    assert window.collection_list.currentItem().data(Qt.ItemDataRole.UserRole) == collections[0].id
    assert (collections[1].id in layers) is visible
    if visible:
        assert {p.id for p in layers[collections[1].id]} == {points[1].id, new.id}


@pytest.mark.parametrize("visible", [True, False])
def test_move_between_collections(scene, monkeypatch, visible):
    window, db, collections, points, layers = scene
    if not visible:
        hide(window, 1)
    dialog = MagicMock(target_collection_id=collections[1].id)
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    monkeypatch.setattr(gui, "MoveWaypointsDialog", lambda *args: dialog)
    window.move_selected_waypoints()
    assert db.get_waypoint_collection_id(points[0].id) == collections[1].id
    assert layers[collections[0].id] == []
    assert (collections[1].id in layers) is visible
    if visible:
        assert {p.id for p in layers[collections[1].id]} == {p.id for p in points}


@pytest.mark.parametrize("action", ["select", "edit", "move", "delete", "search"])
def test_marker_from_other_collection_targets_uuid(scene, action):
    window, db, collections, points, layers = scene
    visibility = set(window._visible_collection_ids)
    target = points[1]
    if action == "select":
        assert window._select_waypoint_from_map(target.id)
    elif action == "edit":
        window.edit_waypoint_from_map(target.id)
    elif action == "move":
        window.move_waypoint_from_map(target.id, 52, 16)
        assert db.get_waypoint(target.id).latitude == 52
        assert layers[collections[1].id][0].latitude == 52
    elif action == "delete":
        window.delete_waypoint_from_map(target.id)
        assert db.get_waypoint(target.id) is None
        assert layers[collections[1].id] == []
        assert not window.waypoint_list.selectedItems()
    else:
        window.search_near_waypoint_from_map(target.id)
        window.map_window.prepare_search_near_waypoint.assert_called_once_with(target)
    assert window.collection_list.currentItem().data(Qt.ItemDataRole.UserRole) == collections[1].id
    assert db.get_waypoint(points[0].id) == points[0]
    assert window._visible_collection_ids == visibility
    if action != "delete":
        assert window.waypoint_list.currentItem().data(Qt.ItemDataRole.UserRole) == target.id
        assert window.name_edit.text() == target.name


@pytest.mark.parametrize("action", ["edit", "delete", "move"])
def test_missing_marker_never_targets_current_waypoint(scene, action):
    window, db, collections, points, layers = scene
    missing = uuid4()
    assert db.get_waypoint_collection_id(missing) is None
    if action == "move":
        window.move_waypoint_from_map(missing, 0, 0)
    else:
        getattr(window, f"{action}_waypoint_from_map")(missing)
    assert db.get_waypoint(points[0].id) == points[0]
    assert window.waypoint_list.currentItem().data(Qt.ItemDataRole.UserRole) == points[0].id
    assert window.name_edit.text() == points[0].name


@pytest.mark.parametrize("visible", [True, False])
@pytest.mark.parametrize("workflow", ["merge", "import"])
def test_merge_and_import_refresh_target_without_changing_visibility(scene, monkeypatch, visible, workflow):
    window, db, collections, points, layers = scene
    target = collections[1].id
    if not visible:
        hide(window, 1)
    new = Waypoint("Merged", 52, 16)
    dialog = MagicMock(merged_target_id=target, created_collection_id=None)
    def execute():
        db.save_waypoint(new, target)
        return QDialog.DialogCode.Accepted
    dialog.exec.side_effect = execute
    if workflow == "merge":
        monkeypatch.setattr(gui, "CollectionMergeDialog", lambda *args: dialog)
        window.open_merge_dialog()
    else:
        monkeypatch.setattr(gui.QFileDialog, "getOpenFileName", lambda *args: ("input.gpx", ""))
        monkeypatch.setattr(gui, "GpxImportDialog", lambda *args: dialog)
        window.import_gpx_file()
    assert (target in window._visible_collection_ids) is visible
    assert (target in layers) is visible
    assert db.get_waypoint(new.id) == new
    if visible:
        assert {p.id for p in layers[target]} == {points[1].id, new.id}
    assert layers[collections[0].id] == [points[0]]


@pytest.mark.parametrize("visible", [True, False])
def test_bulk_save_refreshes_only_visible_content(scene, visible):
    window, db, collections, points, layers = scene
    extra = Waypoint("Extra", 52, 16)
    db.save_waypoint(extra, collections[0].id)
    window.load_waypoints(window.collection_list.currentItem())
    if not visible:
        hide(window, 0)
    window.waypoint_list.selectAll()
    window.waypoint_editor.color_edit.setText("#112233")
    window.waypoint_editor.mark_bulk_field_changed("color")
    window.save_waypoint()
    assert db.get_waypoint(extra.id).color == "#112233"
    assert db.get_waypoint(points[0].id).color == "#112233"
    assert (collections[0].id in layers) is visible
    if visible:
        assert all(p.color == "#112233" for p in layers[collections[0].id])
    assert layers[collections[1].id] == [points[1]]


def test_tooltip_contract_preserves_untrusted_names_as_text(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(WaypointMap, "setHtml", lambda *args: None)
    view = WaypointMap()
    try:
        name = '<img src=x onerror=alert(1)><b>test</b>'
        point = Waypoint(name, 50, 14)
        view.set_waypoints([point])
        view.upsert_collection(uuid4(), [point])
        view.set_search_result(name, 50, 14)
        assert view._waypoint_payload[0]["name"] == name
        assert view._search_result_payload["name"] == name
        assert MAP_HTML.count('const tooltip = document.createElement("span");') == 3
        assert MAP_HTML.count("tooltip.textContent = waypoint.name;") == 2
        assert "tooltip.textContent = result.name;" in MAP_HTML
        assert MAP_HTML.count("bindTooltip(tooltip)") == 3
        assert "bindTooltip(waypoint.name)" not in MAP_HTML
        assert "bindTooltip(result.name)" not in MAP_HTML
    finally:
        view.close()
        app.processEvents()
