import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from wpt_manager.gui.waypoint_map import MAP_HTML, MapBridge, WaypointMap
from wpt_manager.map_sources import (
    MAPY_COPYRIGHT_URL,
    MAPY_HOME_URL,
    resolve_map_source,
)
from wpt_manager.models.waypoint import Waypoint


def test_map_payload_uses_uuid_and_replaces_previous_waypoints():
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    first = Waypoint(name="First", latitude=50.0, longitude=14.0)
    second = Waypoint(name="Second", latitude=51.0, longitude=15.0)

    waypoint_map.set_waypoints([first])
    waypoint_map.set_waypoints([second])

    assert waypoint_map._waypoint_payload == [
        {
            "id": str(second.id),
            "name": "Second",
            "latitude": 51.0,
            "longitude": 15.0,
        }
    ]
    assert "window.setWaypoints = function(waypoints)" in MAP_HTML
    assert "markerLayer.clearLayers()" in MAP_HTML
    assert "bridge.markerClicked(waypoint.id)" in MAP_HTML
    assert "bridge.mapClicked" in MAP_HTML
    assert "map.invalidateSize(false)" in MAP_HTML
    assert "Map library failed to load" in MAP_HTML
    assert "window.setMapSource = function(source)" in MAP_HTML
    assert "map.removeLayer(baseTileLayer)" in MAP_HTML
    assert "markerLayer.clearLayers()" in MAP_HTML
    assert "const DEFAULT_ZOOM = 7" in MAP_HTML
    assert "baseTileLayer.on(\"tileerror\"" in MAP_HTML
    assert 'target.closest("a[data-external-url]")' in MAP_HTML
    assert "event.preventDefault()" in MAP_HTML
    assert "pointer-events: auto" in MAP_HTML
    assert waypoint_map.web_view.minimumWidth() == 300
    assert waypoint_map.web_view.minimumHeight() == 300
    assert waypoint_map.web_profile.httpUserAgent() == (
        "WPT-Manager/0.1 (PySide6 desktop application)"
    )

    waypoint_map.close()
    application.processEvents()


def test_waypoints_wait_for_page_map_and_visible_view(monkeypatch):
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    scripts = []
    monkeypatch.setattr(waypoint_map, "_execute_javascript", scripts.append)
    waypoint = Waypoint(name="Prepared", latitude=50.0, longitude=14.0)

    waypoint_map.set_waypoints([waypoint])
    assert scripts == []
    assert waypoint_map._pending_update

    waypoint_map._handle_load_finished(True)
    assert scripts == []
    assert waypoint_map._pending_update

    waypoint_map._handle_map_ready()
    assert len(scripts) == 1
    assert scripts[0].startswith("window.setMapSource(")
    assert waypoint_map._pending_update

    waypoint_map._handle_first_visible_size()
    assert scripts[1] == "window.invalidateMapSize();"
    assert len(scripts) == 3
    assert scripts[2].startswith("window.setWaypoints(")
    assert str(waypoint.id) in scripts[2]
    assert not waypoint_map._pending_update

    waypoint_map.close()
    application.processEvents()


def test_empty_map_has_no_waypoint_payload():
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()

    waypoint_map.set_waypoints([])

    assert waypoint_map._waypoint_payload == []

    waypoint_map.close()
    application.processEvents()


def test_changing_map_source_does_not_change_waypoint_dataset():
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    waypoint = Waypoint(name="Kept", latitude=50.0, longitude=14.0)
    waypoint_map.set_waypoints([waypoint])
    original_payload = list(waypoint_map._waypoint_payload)
    source, _ = resolve_map_source("mapy-basic", "test-key")

    waypoint_map.set_map_source(source)

    assert waypoint_map._waypoint_payload == original_payload
    assert waypoint_map._pending_update
    assert waypoint_map._map_source_payload["id"] == "mapy-basic"

    waypoint_map.close()
    application.processEvents()


def test_map_attribution_links_open_in_external_browser(monkeypatch):
    opened_urls = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url.toString()) or True,
    )
    bridge = MapBridge()

    bridge.openExternalUrl(MAPY_HOME_URL)
    bridge.openExternalUrl(MAPY_COPYRIGHT_URL)
    bridge.openExternalUrl("https://example.com/")

    assert opened_urls == [MAPY_HOME_URL, MAPY_COPYRIGHT_URL]
