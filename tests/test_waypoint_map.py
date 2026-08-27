import os
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import QApplication, QMenu

from wpt_manager.gui.waypoint_map import MAP_HTML, MapBridge, WaypointMap
from wpt_manager.gui.map_window import build_icon_data_urls
from wpt_manager.map_sources import (
    MAPY_COPYRIGHT_URL,
    MAPY_HOME_URL,
    resolve_map_source,
)
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.models.icon import IconInfo


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
            "icon": "marker",
            "color": "#FF0000",
            "background": "circle",
            "iconSvgUrl": None,
        }
    ]
    assert (
        "window.setWaypoints = function(waypoints, fitViewport = true)"
        in MAP_HTML
    )
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
    assert '"wpt-marker-shape " + background' in MAP_HTML
    assert '.wpt-marker-shape.circle' in MAP_HTML
    assert '.wpt-marker-shape.square' in MAP_HTML
    assert '.wpt-marker-shape.octagon' in MAP_HTML
    assert "L.divIcon" in MAP_HTML
    assert ".waypoint-marker.selected" in MAP_HTML
    assert "transform: scale(1.3)" in MAP_HTML
    assert "marker.setZIndexOffset(selected ? 1000 : 0)" in MAP_HTML
    assert 'map.on("contextmenu"' in MAP_HTML
    assert "bridge.mapContextMenu(" in MAP_HTML
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
    assert len(scripts) == 4
    assert scripts[2].startswith("window.setWaypoints(")
    assert str(waypoint.id) in scripts[2]
    assert scripts[3] == "window.setSelectedWaypointIds([]);"
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


def test_custom_page_is_released_before_custom_profile():
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    custom_page = waypoint_map.web_page
    custom_profile = waypoint_map.web_profile
    destruction_order = []
    custom_page.destroyed.connect(
        lambda *_: destruction_order.append("page")
    )
    custom_profile.destroyed.connect(
        lambda *_: destruction_order.append("profile")
    )

    assert custom_page.parent() is waypoint_map
    assert custom_page.profile() is custom_profile

    waypoint_map.release_web_engine()

    assert waypoint_map._web_engine_released
    assert waypoint_map.page() is not custom_page
    assert waypoint_map.page().profile() is QWebEngineProfile.defaultProfile()
    assert waypoint_map.web_profile is None

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert destruction_order == ["page", "profile"]

    waypoint_map.release_web_engine()
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


def test_search_result_replaces_marker_without_changing_waypoints(monkeypatch):
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    waypoint = Waypoint(name="Kept", latitude=50.0, longitude=14.0)
    waypoint_map.set_waypoints([waypoint])
    original_payload = list(waypoint_map._waypoint_payload)
    scripts = []
    monkeypatch.setattr(waypoint_map, "_execute_javascript", scripts.append)
    waypoint_map._handle_load_finished(True)
    waypoint_map._handle_map_ready()
    waypoint_map._handle_first_visible_size()

    waypoint_map.set_search_result("First", 50.1, 14.1)
    first_script = scripts[-1]
    waypoint_map.set_search_result("Second", 50.2, 14.2)
    second_script = scripts[-1]

    assert first_script.startswith("window.setSearchResult(")
    assert '"name": "First"' in first_script
    assert second_script.startswith("window.setSearchResult(")
    assert '"name": "Second"' in second_script
    assert waypoint_map._search_result_payload == {
        "name": "Second",
        "latitude": 50.2,
        "longitude": 14.2,
    }
    assert waypoint_map._waypoint_payload == original_payload
    assert "searchMarkerLayer.clearLayers()" in MAP_HTML
    assert "Math.max(map.getZoom(), 15)" in MAP_HTML

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


def test_known_svg_icon_and_unknown_icon_fallback(tmp_path):
    application = QApplication.instance() or QApplication([])
    svg_path = tmp_path / "known.svg"
    svg_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    icon_urls = build_icon_data_urls(
        [IconInfo(group="Test", icon_name="known", svg_path=svg_path)]
    )
    waypoint_map = WaypointMap(icon_data_urls=icon_urls)
    known = Waypoint(
        name="Known",
        latitude=50.0,
        longitude=14.0,
        icon="known",
        color="#123456",
        background="octagon",
    )
    unknown = Waypoint(
        name="Unknown",
        latitude=51.0,
        longitude=15.0,
        icon="missing",
        color="#654321",
        background="square",
    )

    waypoint_map.set_waypoints([known, unknown])

    assert waypoint_map._waypoint_payload[0]["iconSvgUrl"].startswith(
        "data:image/svg+xml;base64,"
    )
    assert waypoint_map._waypoint_payload[0]["background"] == "octagon"
    assert waypoint_map._waypoint_payload[1]["iconSvgUrl"] is None
    assert waypoint_map._waypoint_payload[1]["background"] == "square"

    waypoint_map.close()
    application.processEvents()


def test_single_multi_and_cleared_marker_selection(monkeypatch):
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    scripts = []
    monkeypatch.setattr(waypoint_map, "_execute_javascript", scripts.append)
    waypoint_map._handle_load_finished(True)
    waypoint_map._handle_map_ready()
    waypoint_map._handle_first_visible_size()
    first_id = uuid4()
    second_id = uuid4()

    waypoint_map.set_selected_waypoint_ids([first_id])
    assert scripts[-1] == (
        f'window.setSelectedWaypointIds(["{first_id}"]);'
    )

    waypoint_map.set_selected_waypoint_ids([first_id, second_id])
    assert scripts[-1] == (
        f'window.setSelectedWaypointIds(["{first_id}", "{second_id}"]);'
    )

    waypoint_map.set_selected_waypoint_ids([])
    assert scripts[-1] == "window.setSelectedWaypointIds([]);"

    waypoint_map.close()
    application.processEvents()


def test_clear_search_result_removes_only_temporary_marker(monkeypatch):
    application = QApplication.instance() or QApplication([])
    waypoint_map = WaypointMap()
    scripts = []
    monkeypatch.setattr(waypoint_map, "_execute_javascript", scripts.append)
    waypoint_map._handle_load_finished(True)
    waypoint_map._handle_map_ready()
    waypoint_map._handle_first_visible_size()
    waypoint_map.set_search_result("Place", 50.0, 14.0)
    waypoint_payload = list(waypoint_map._waypoint_payload)

    waypoint_map.clear_search_result()

    assert scripts[-1] == "window.setSearchResult(null);"
    assert waypoint_map._search_result_payload is None
    assert waypoint_map._waypoint_payload == waypoint_payload

    waypoint_map.close()
    application.processEvents()


def test_map_context_menu_passes_coordinates_and_requests_add(monkeypatch):
    application = QApplication.instance() or QApplication([])
    bridge = MapBridge()
    bridge_coordinates = []
    bridge.map_context_menu_requested.connect(
        lambda *values: bridge_coordinates.append(values)
    )

    bridge.mapContextMenu(50.123, 14.456, 120, 80)

    assert bridge_coordinates == [(50.123, 14.456, 120, 80)]

    from wpt_manager.config import ApplicationConfig
    from wpt_manager.gui.map_window import MapWindow

    monkeypatch.setattr(QMenu, "popup", lambda *args: None)
    map_window = MapWindow(config=ApplicationConfig())
    requested_coordinates = []
    map_window.add_waypoint_requested.connect(
        lambda *values: requested_coordinates.append(values)
    )

    map_window._show_map_context_menu(50.123, 14.456, 120, 80)
    map_window._map_context_menu.actions()[0].trigger()

    assert requested_coordinates == [(50.123, 14.456)]

    map_window.close()
    application.processEvents()
