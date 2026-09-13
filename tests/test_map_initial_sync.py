"""Regression contract between current visibility, Qt readiness and JS layers."""
import os
import json
from itertools import permutations
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.gui.map_window import MapWindow
from wpt_manager.gui.waypoint_map import WaypointMap, MAP_HTML
from wpt_manager.models.collection import Collection
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.models.track import Track, TrackPoint


@pytest.fixture
def app(monkeypatch):
    application = QApplication.instance() or QApplication([])
    # Exercise the Python/JS contract without opening a GUI or loading web assets.
    monkeypatch.setattr(WaypointMap, "setHtml", lambda *args: None)
    for method in ("show", "raise_", "activateWindow"):
        monkeypatch.setattr(MapWindow, method, lambda *args: None)
    return application


def ready(view, order=("load", "ready", "visible")):
    actions = {
        "load": lambda: view._handle_load_finished(True),
        "ready": view.bridge.map_ready.emit,
        "visible": view._handle_first_visible_size,
    }
    for event in order:
        actions[event]()


def collection_payloads(scripts):
    prefix = "window.upsertCollection("
    return [json.loads(script[len(prefix):-2]) for script in scripts if script.startswith(prefix)]


@pytest.mark.parametrize("order", list(permutations(("load", "ready", "visible"))))
def test_initial_sync_all_layers_in_any_readiness_order(app, monkeypatch, order):
    view = WaypointMap()
    scripts = []
    monkeypatch.setattr(view, "_execute_javascript", scripts.append)
    collection_id = uuid4()
    point = Waypoint("Prepared", 50, 14)
    track = Track("Track", "test.gpx")
    view.upsert_collection(collection_id, [point])
    view.upsert_track(track, [TrackPoint(50, 14, 0), TrackPoint(51, 15, 1)])
    view.set_selected_waypoint_ids([point.id])
    view.set_search_result("Search", 50, 14)
    ready(view, order[:2])
    assert not collection_payloads(scripts)
    assert not any(script.startswith("window.upsertTrack(") for script in scripts)
    ready(view, order[2:])
    payloads = collection_payloads(scripts)
    assert len(payloads) == 1
    assert payloads[0]["id"] == str(collection_id)
    assert payloads[0]["waypoints"][0]["id"] == str(point.id)
    assert sum(script.startswith("window.upsertTrack(") for script in scripts) == 1
    assert any(script.startswith("window.setMapSource(") for script in scripts)
    assert any(script.startswith("window.setSearchResult(") for script in scripts)
    assert scripts.index(next(s for s in scripts if s.startswith("window.upsertCollection("))) < scripts.index(next(s for s in scripts if s.startswith("window.setSelectedWaypointIds(")))
    previous = list(scripts)
    ready(view)
    assert scripts == previous  # Repeated readiness does not duplicate the push.
    view.close()


def test_pending_state_uses_latest_visibility_before_ready(app, monkeypatch):
    view = WaypointMap()
    scripts = []
    monkeypatch.setattr(view, "_execute_javascript", scripts.append)
    hidden_id, visible_id = uuid4(), uuid4()
    hidden, visible = Waypoint("Hidden", 50, 14), Waypoint("Visible", 51, 15)
    view.set_selected_waypoint_ids([hidden.id])  # Selection must not imply visibility.
    view.upsert_collection(hidden_id, [hidden])
    view.remove_collection(hidden_id)
    view.upsert_collection(visible_id, [visible])
    ready(view)
    assert [payload["id"] for payload in collection_payloads(scripts)] == [str(visible_id)]
    assert all(str(hidden.id) not in str(payload) for payload in collection_payloads(scripts))
    view.close()


@pytest.mark.parametrize("change_before_open", [False, True])
def test_open_reopen_and_provider_switch_use_current_visibility(app, tmp_path, monkeypatch, change_before_open):
    database = Database(tmp_path / "data.db")
    database.initialize()
    first, second = Collection("First"), Collection("Second")
    first_point, second_point = Waypoint("First point", 50, 14), Waypoint("Second point", 51, 15)
    for collection, point in ((first, first_point), (second, second_point)):
        database.save_collection(collection)
        database.save_waypoint(point, collection.id)
    window = MainWindow(database, icon_catalog=[])
    assert window.data_tabs.tabText(0) == "Waypoints"
    assert window.data_tabs.widget(0).title() == "Waypoints"
    assert window.new_collection_button.text() == "New Collection"
    items = {window.collection_list.item(i).data(Qt.ItemDataRole.UserRole): window.collection_list.item(i) for i in range(window.collection_list.count())}
    if change_before_open:
        items[first.id].setCheckState(Qt.CheckState.Unchecked)
    expected = {second.id} if change_before_open else {first.id, second.id}
    assert window._visible_collection_ids == expected
    # Selecting a hidden collection must not display its waypoints.
    window.collection_list.setCurrentItem(items[first.id])
    toggles = []
    window.collection_list.itemChanged.connect(lambda item: toggles.append(item))
    for attempt in range(2):
        window.open_map()
        map_window = window.map_window
        view = map_window.waypoint_map
        scripts = []
        monkeypatch.setattr(view, "_execute_javascript", scripts.append)
        assert {payload["id"] for payload in view._collection_payloads.values()} == {str(value) for value in expected}
        ready(view)
        assert {payload["id"] for payload in collection_payloads(scripts)} == {str(value) for value in expected}
        assert not toggles  # Neither open nor ready simulates a checkbox change.
        snapshot = dict(view._collection_payloads)
        monkeypatch.setenv("MAPY_API_KEY", "test-mapy-key")
        scripts.clear()
        for provider in ("mapy-basic", "openstreetmap"):
            map_window.map_source_combo.setCurrentIndex(map_window.map_source_combo.findData(provider))
            assert view._collection_payloads == snapshot
        assert len(scripts) == 2
        assert all(script.startswith("window.setMapSource(") for script in scripts)
        map_window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert window.map_window is None
    # Normal user visibility changes still update only the relevant layer.
    window.open_map()
    view = window.map_window.waypoint_map
    scripts = []
    monkeypatch.setattr(view, "_execute_javascript", scripts.append)
    ready(view)
    scripts.clear()
    items[second.id].setCheckState(Qt.CheckState.Unchecked)
    assert str(second.id) not in view._collection_payloads
    assert any(script.startswith("window.removeCollection(") for script in scripts)
    items[second.id].setCheckState(Qt.CheckState.Checked)
    assert any(payload["id"] == str(second.id) for payload in collection_payloads(scripts))
    window.map_window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    window.close()


def test_js_provider_switch_only_replaces_base_layer():
    switch = MAP_HTML.split("window.setMapSource = function(source)", 1)[1].split("function initializeMap", 1)[0]
    assert "map.removeLayer(baseTileLayer)" in switch
    assert "markerLayer.clearLayers()" not in switch
    assert "collectionLayersById.clear()" not in switch
    assert "map.remove()" not in switch
