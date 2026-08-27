import json
import logging
from uuid import UUID

from PySide6.QtCore import QObject, QEvent, Signal, Slot, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QSizePolicy, QWidget

from wpt_manager.map_sources import (
    MAPY_COPYRIGHT_URL,
    MAPY_HOME_URL,
    OPENSTREETMAP_SOURCE_ID,
    ResolvedMapSource,
    resolve_map_source,
)
from wpt_manager.models.waypoint import Waypoint


LOGGER = logging.getLogger(__name__)


MAP_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        onerror="console.error('Leaflet CSS failed to load.');">
  <style>
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      overflow: hidden;
    }
    #map {
      width: 100%;
      height: 100%;
    }
    #offline {
      box-sizing: border-box;
      width: 100%;
      height: 100%;
      padding: 1rem;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: sans-serif;
    }
    #offline[hidden] { display: none; }
    #tile-status {
      position: absolute;
      z-index: 1000;
      left: 50%;
      bottom: 12px;
      transform: translateX(-50%);
      padding: 6px 10px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.9);
      font-family: sans-serif;
    }
    #tile-status[hidden] { display: none; }
    .mapy-logo-control,
    .mapy-logo-control a,
    .mapy-logo-control img,
    .leaflet-control-attribution,
    .leaflet-control-attribution a {
      pointer-events: auto;
    }
    .mapy-logo-control a,
    .mapy-logo-control img {
      display: block;
    }
    .wpt-marker-icon {
      background: transparent;
      border: 0;
    }
    .waypoint-marker {
      box-sizing: border-box;
      width: 32px;
      height: 32px;
      padding: 3px;
      transition: transform 120ms ease, filter 120ms ease;
    }
    .waypoint-marker.selected {
      transform: scale(1.3);
      filter: drop-shadow(0 0 2px #FFFFFF)
              drop-shadow(0 0 4px #FFFFFF)
              drop-shadow(0 0 4px #111827)
              drop-shadow(0 0 7px rgba(17, 24, 39, 0.95));
    }
    .wpt-marker-shape {
      box-sizing: border-box;
      display: flex;
      width: 100%;
      height: 100%;
      align-items: center;
      justify-content: center;
      border: 2px solid rgba(255, 255, 255, 0.9);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.55);
      overflow: hidden;
    }
    .wpt-marker-shape.circle { border-radius: 50%; }
    .wpt-marker-shape.square { border-radius: 3px; }
    .wpt-marker-shape.octagon {
      clip-path: polygon(
        30% 0, 70% 0, 100% 30%, 100% 70%,
        70% 100%, 30% 100%, 0 70%, 0 30%
      );
    }
    .wpt-marker-shape img {
      display: block;
      width: 18px;
      height: 18px;
      object-fit: contain;
      pointer-events: none;
    }
    .search-marker {
      box-sizing: border-box;
      width: 24px;
      height: 24px;
      border: 4px solid #FFFFFF;
      border-radius: 50%;
      background: #2563EB;
      box-shadow: 0 0 0 3px #111827, 0 2px 7px rgba(0, 0, 0, 0.7);
    }
  </style>
</head>
<body>
  <div id="map"></div>
  <div id="offline" hidden>Map library failed to load</div>
  <div id="tile-status" hidden>Map background is unavailable</div>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          onerror="console.error('Leaflet JavaScript failed to load.');">
  </script>
  <script>
    const DEFAULT_CENTER = [49.8, 15.5];
    const DEFAULT_ZOOM = 7;
    let map = null;
    let baseTileLayer = null;
    let markerLayer = null;
    let searchMarkerLayer = null;
    let searchMarker = null;
    let markersById = new Map();
    let selectedWaypointIds = new Set();
    let mapyLogoControl = null;
    let bridge = null;
    let readyReported = false;

    new QWebChannel(qt.webChannelTransport, channel => {
      bridge = channel.objects.mapBridge;
      initializeMap();
      reportReady();
    });

    function reportReady() {
      if (map && bridge && !readyReported) {
        readyReported = true;
        bridge.mapReady();
      }
    }

    window.invalidateMapSize = function() {
      if (map) map.invalidateSize(false);
    };

    window.setMapSource = function(source) {
      if (!map) {
        console.error("Map source set before the map was ready.");
        return;
      }
      if (baseTileLayer) {
        map.removeLayer(baseTileLayer);
      }
      if (mapyLogoControl) {
        map.removeControl(mapyLogoControl);
        mapyLogoControl = null;
      }

      const tileStatus = document.getElementById("tile-status");
      let tileErrorCount = 0;
      baseTileLayer = L.tileLayer(source.tileUrl, {
        minZoom: 0,
        maxZoom: source.maxZoom,
        attribution: source.attribution
      });
      baseTileLayer.on("loading", () => {
        tileErrorCount = 0;
        tileStatus.hidden = true;
      });
      baseTileLayer.on("load", () => {
        tileStatus.hidden = tileErrorCount === 0;
      });
      baseTileLayer.on("tileerror", event => {
        const url = event.tile.currentSrc || event.tile.src || "unknown URL";
        const error = event.error && event.error.message
          ? event.error.message
          : String(event.error || "unknown error");
        console.error(source.label + " tile failed", url, error);
        tileErrorCount += 1;
        tileStatus.hidden = false;
      });
      baseTileLayer.addTo(map);

      if (source.mapyLogoUrl) {
        mapyLogoControl = L.control({position: "bottomleft"});
        mapyLogoControl.onAdd = function() {
          const container = L.DomUtil.create("div", "mapy-logo-control");
          const link = L.DomUtil.create("a", "", container);
          link.href = "https://mapy.com/";
          link.target = "_blank";
          link.dataset.externalUrl = "https://mapy.com/";
          const logo = L.DomUtil.create("img", "", link);
          logo.src = source.mapyLogoUrl;
          logo.width = 100;
          logo.alt = "Mapy.com";
          L.DomEvent.disableClickPropagation(link);
          return container;
        };
        mapyLogoControl.addTo(map);
      }
    };

    function initializeMap() {
      if (map) {
        reportReady();
        return;
      }
      if (typeof L === "undefined") {
        console.error("Leaflet is unavailable; the map cannot initialize.");
        document.getElementById("map").hidden = true;
        document.getElementById("offline").hidden = false;
        return;
      }
      map = L.map("map").setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      markerLayer = L.layerGroup().addTo(map);
      searchMarkerLayer = L.layerGroup().addTo(map);
      map.getContainer().addEventListener("click", event => {
        const target = event.target;
        const link = target instanceof Element
          ? target.closest("a[data-external-url]")
          : null;
        if (!link || !bridge) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        bridge.openExternalUrl(link.dataset.externalUrl);
      }, true);
      map.on("click", event => {
        if (bridge) bridge.mapClicked(event.latlng.lat, event.latlng.lng);
      });
      map.on("contextmenu", event => {
        if (!bridge) return;
        event.originalEvent.preventDefault();
        bridge.mapContextMenu(
          event.latlng.lat,
          event.latlng.lng,
          event.originalEvent.clientX,
          event.originalEvent.clientY
        );
      });
      const reportViewport = () => {
        if (!bridge) return;
        const bounds = map.getBounds();
        bridge.viewportChanged(
          bounds.getWest(),
          bounds.getSouth(),
          bounds.getEast(),
          bounds.getNorth()
        );
      };
      map.on("moveend", reportViewport);
      reportViewport();
      new ResizeObserver(() => {
        if (map) map.invalidateSize(false);
      }).observe(
        document.getElementById("map")
      );
      reportReady();
    }

    function applyMarkerSelection(waypointId, marker) {
      const selected = selectedWaypointIds.has(waypointId);
      marker.setZIndexOffset(selected ? 1000 : 0);
      const element = marker.getElement();
      if (!element) return;
      const shell = element.querySelector(".waypoint-marker");
      if (shell) {
        shell.classList.toggle("selected", selected);
      }
    }

    window.setSelectedWaypointIds = function(waypointIds) {
      selectedWaypointIds = new Set(waypointIds);
      for (const [waypointId, marker] of markersById) {
        applyMarkerSelection(waypointId, marker);
      }
    };

    window.setWaypoints = function(waypoints, fitViewport = true) {
      if (!map || !markerLayer) {
        console.error("setWaypoints called before the map was ready.");
        return;
      }
      markerLayer.clearLayers();
      markersById.clear();
      const bounds = [];
      for (const waypoint of waypoints) {
        const background = ["circle", "square", "octagon"].includes(
          waypoint.background
        ) ? waypoint.background : "square";
        const shell = L.DomUtil.create("div", "waypoint-marker");
        const shape = L.DomUtil.create(
          "div",
          "wpt-marker-shape " + background,
          shell
        );
        shape.style.backgroundColor = waypoint.color;
        if (waypoint.iconSvgUrl) {
          const iconImage = L.DomUtil.create("img", "", shape);
          iconImage.src = waypoint.iconSvgUrl;
          iconImage.alt = "";
        }
        const icon = L.divIcon({
          className: "wpt-marker-icon",
          html: shell,
          iconSize: [32, 32],
          iconAnchor: [16, 16]
        });
        const marker = L.marker(
          [waypoint.latitude, waypoint.longitude],
          {icon: icon}
        );
        marker.bindTooltip(waypoint.name);
        marker.on("click", () => {
          if (bridge) bridge.markerClicked(waypoint.id);
        });
        marker.on("contextmenu", event => {
          if (!bridge) return;
          event.originalEvent.preventDefault();
          L.DomEvent.stopPropagation(event.originalEvent);
          bridge.markerContextMenu(
            waypoint.id,
            event.originalEvent.clientX,
            event.originalEvent.clientY
          );
        });
        marker.addTo(markerLayer);
        markersById.set(waypoint.id, marker);
        applyMarkerSelection(waypoint.id, marker);
        bounds.push([waypoint.latitude, waypoint.longitude]);
      }
      if (fitViewport && bounds.length > 0) {
        map.fitBounds(bounds, {padding: [20, 20], maxZoom: 14});
      } else if (fitViewport) {
        map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      }
    };

    window.setSearchResult = function(result) {
      if (!map || !searchMarkerLayer) return;
      searchMarkerLayer.clearLayers();
      searchMarker = null;
      if (!result) return;
      const shell = L.DomUtil.create("div", "search-marker");
      const icon = L.divIcon({
        className: "wpt-marker-icon",
        html: shell,
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      });
      searchMarker = L.marker(
        [result.latitude, result.longitude],
        {icon: icon, zIndexOffset: 2000}
      );
      searchMarker.bindTooltip(result.name);
      searchMarker.addTo(searchMarkerLayer);
      map.setView(
        [result.latitude, result.longitude],
        Math.max(map.getZoom(), 15)
      );
    };

    window.addEventListener("load", initializeMap);
  </script>
</body>
</html>
"""


class MapBridge(QObject):
    marker_clicked = Signal(str)
    marker_context_menu_requested = Signal(str, int, int)
    map_clicked = Signal(float, float)
    map_context_menu_requested = Signal(float, float, int, int)
    map_ready = Signal()
    viewport_changed = Signal(float, float, float, float)

    @Slot()
    def mapReady(self) -> None:
        self.map_ready.emit()

    @Slot(str)
    def markerClicked(self, waypoint_id: str) -> None:
        self.marker_clicked.emit(waypoint_id)

    @Slot(str, int, int)
    def markerContextMenu(
        self,
        waypoint_id: str,
        x: int,
        y: int,
    ) -> None:
        self.marker_context_menu_requested.emit(waypoint_id, x, y)

    @Slot(float, float)
    def mapClicked(self, latitude: float, longitude: float) -> None:
        self.map_clicked.emit(latitude, longitude)

    @Slot(float, float, int, int)
    def mapContextMenu(
        self,
        latitude: float,
        longitude: float,
        x: int,
        y: int,
    ) -> None:
        self.map_context_menu_requested.emit(latitude, longitude, x, y)

    @Slot(float, float, float, float)
    def viewportChanged(
        self,
        west: float,
        south: float,
        east: float,
        north: float,
    ) -> None:
        self.viewport_changed.emit(west, south, east, north)

    @Slot(str)
    def openExternalUrl(self, url: str) -> None:
        if url not in {MAPY_HOME_URL, MAPY_COPYRIGHT_URL}:
            LOGGER.warning("Blocked unexpected external map URL: %s", url)
            return
        QDesktopServices.openUrl(QUrl(url))


class MapWebPage(QWebEnginePage):
    console_message = Signal(str)

    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        formatted_message = f"{source_id}:{line_number}: {message}"
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessage:
            LOGGER.error("Map JavaScript error: %s", formatted_message)
        self.console_message.emit(formatted_message)


class MapWebView(QWebEngineView):
    first_visible_size = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shown = False
        self._visible_size_reported = False

    def showEvent(self, event: QEvent) -> None:
        self._shown = True
        super().showEvent(event)
        self._report_visible_size()

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._report_visible_size()

    def _report_visible_size(self) -> None:
        if (
            self._shown
            and not self._visible_size_reported
            and self.width() > 0
            and self.height() > 0
        ):
            self._visible_size_reported = True
            self.first_visible_size.emit()


class WaypointMap(MapWebView):
    marker_clicked = Signal(str)
    marker_context_menu_requested = Signal(str, int, int)
    map_clicked = Signal(float, float)
    map_context_menu_requested = Signal(float, float, int, int)
    console_message = Signal(str)
    viewport_changed = Signal(float, float, float, float)

    def __init__(
        self,
        initial_map_source: ResolvedMapSource | None = None,
        icon_data_urls: dict[str, str] | None = None,
        web_profile: QWebEngineProfile | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if initial_map_source is None:
            initial_map_source, _ = resolve_map_source(
                OPENSTREETMAP_SOURCE_ID,
                None,
            )
        self._icon_data_urls = icon_data_urls or {}
        self._waypoint_payload: list[dict[str, str | float | None]] = []
        self._selected_waypoint_ids: list[str] = []
        self._search_result_payload: dict[str, str | float] | None = None
        self._map_source_payload = self._source_payload(initial_map_source)
        self._page_loaded = False
        self._map_ready = False
        self._view_visible = False
        self._initial_size_invalidated = False
        self._pending_update = True
        self._pending_fit_viewport = True
        self._pending_selection = True
        self._pending_map_source = True
        self._pending_search_result = False
        self._web_engine_released = False
        self.console_messages: list[str] = []
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(300, 300)
        self.web_profile = web_profile or QWebEngineProfile(self)
        self.web_profile.setHttpUserAgent(
            "WPT-Manager/0.1 (PySide6 desktop application)"
        )
        self.web_page = MapWebPage(self.web_profile, self)
        self.setPage(self.web_page)
        self.bridge = MapBridge(self)
        self.channel = QWebChannel(self.page())
        self.channel.registerObject("mapBridge", self.bridge)
        self.page().setWebChannel(self.channel)
        self.bridge.marker_clicked.connect(self.marker_clicked)
        self.bridge.marker_context_menu_requested.connect(
            self.marker_context_menu_requested
        )
        self.bridge.map_clicked.connect(self.map_clicked)
        self.bridge.map_context_menu_requested.connect(
            self.map_context_menu_requested
        )
        self.bridge.viewport_changed.connect(self.viewport_changed)
        self.bridge.map_ready.connect(self._handle_map_ready)
        self.web_page.console_message.connect(self._record_console_message)
        self.loadFinished.connect(self._handle_load_finished)
        self.first_visible_size.connect(
            self._handle_first_visible_size
        )

        self.setHtml(MAP_HTML, QUrl("https://localhost/"))

    def release_web_engine(self) -> None:
        if self._web_engine_released:
            return
        self._web_engine_released = True
        self.stop()
        profile = self.web_profile
        page = self.web_page
        page.destroyed.connect(profile.deleteLater)
        replacement_page = QWebEnginePage(self)
        self.setPage(replacement_page)
        self.web_page = replacement_page
        self.channel = None
        self.web_profile = None
        page.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.release_web_engine()
        super().closeEvent(event)

    @property
    def web_view(self) -> MapWebView:
        """Return the directly embedded web view for API compatibility."""
        return self

    def set_waypoints(
        self,
        waypoints: list[Waypoint],
        fit_viewport: bool = True,
    ) -> None:
        self._waypoint_payload = [
            {
                "id": str(waypoint.id),
                "name": waypoint.name,
                "latitude": waypoint.latitude,
                "longitude": waypoint.longitude,
                "icon": waypoint.icon,
                "color": waypoint.color,
                "background": waypoint.background,
                "iconSvgUrl": self._icon_data_urls.get(waypoint.icon),
            }
            for waypoint in waypoints
        ]
        self._pending_fit_viewport = fit_viewport
        self._pending_update = True
        self._flush_pending_waypoints()

    def set_selected_waypoint_ids(self, waypoint_ids: list[UUID]) -> None:
        self._selected_waypoint_ids = [
            str(waypoint_id) for waypoint_id in waypoint_ids
        ]
        self._pending_selection = True
        self._flush_pending_selection()

    def set_map_source(self, source: ResolvedMapSource) -> None:
        self._map_source_payload = self._source_payload(source)
        self._pending_map_source = True
        self._flush_pending_map_source()

    def set_search_result(
        self,
        name: str,
        latitude: float,
        longitude: float,
    ) -> None:
        self._search_result_payload = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
        }
        self._pending_search_result = True
        self._flush_pending_search_result()

    def clear_search_result(self) -> None:
        self._search_result_payload = None
        self._pending_search_result = True
        self._flush_pending_search_result()

    def _handle_load_finished(self, loaded: bool) -> None:
        self._page_loaded = loaded
        if not loaded:
            message = "Map HTML failed to load."
            LOGGER.error(message)
            self._record_console_message(message)
            return
        self._flush_pending_map_source()
        self._flush_pending_waypoints()
        self._flush_pending_selection()
        self._flush_pending_search_result()

    def _handle_map_ready(self) -> None:
        self._map_ready = True
        self._flush_pending_map_source()
        self._invalidate_initial_size_if_ready()
        self._flush_pending_waypoints()
        self._flush_pending_selection()
        self._flush_pending_search_result()

    def _handle_first_visible_size(self) -> None:
        self._view_visible = True
        self._invalidate_initial_size_if_ready()
        self._flush_pending_waypoints()
        self._flush_pending_selection()
        self._flush_pending_search_result()

    def _invalidate_initial_size_if_ready(self) -> None:
        if (
            self._map_ready
            and self._view_visible
            and not self._initial_size_invalidated
        ):
            self._execute_javascript("window.invalidateMapSize();")
            self._initial_size_invalidated = True

    def _flush_pending_waypoints(self) -> None:
        if not (
            self._pending_update
            and self._page_loaded
            and self._map_ready
            and self._view_visible
        ):
            return
        payload = json.dumps(self._waypoint_payload, ensure_ascii=False)
        fit_viewport = "true" if self._pending_fit_viewport else "false"
        self._execute_javascript(
            f"window.setWaypoints({payload}, {fit_viewport});"
        )
        self._pending_update = False

    def _flush_pending_selection(self) -> None:
        if not (
            self._pending_selection
            and self._page_loaded
            and self._map_ready
            and self._view_visible
        ):
            return
        payload = json.dumps(self._selected_waypoint_ids)
        self._execute_javascript(
            f"window.setSelectedWaypointIds({payload});"
        )
        self._pending_selection = False

    def _flush_pending_map_source(self) -> None:
        if not (
            self._pending_map_source
            and self._page_loaded
            and self._map_ready
        ):
            return
        payload = json.dumps(self._map_source_payload, ensure_ascii=False)
        self._execute_javascript(f"window.setMapSource({payload});")
        self._pending_map_source = False

    def _flush_pending_search_result(self) -> None:
        if not (
            self._pending_search_result
            and self._page_loaded
            and self._map_ready
            and self._view_visible
        ):
            return
        payload = json.dumps(self._search_result_payload, ensure_ascii=False)
        self._execute_javascript(f"window.setSearchResult({payload});")
        self._pending_search_result = False

    @staticmethod
    def _source_payload(source: ResolvedMapSource) -> dict[str, str | int | None]:
        return {
            "id": source.id,
            "label": source.label,
            "tileUrl": source.tile_url,
            "maxZoom": source.max_zoom,
            "attribution": source.attribution,
            "mapyLogoUrl": source.mapy_logo_url,
        }

    def _execute_javascript(self, script: str) -> None:
        if self._web_engine_released:
            return
        self.web_page.runJavaScript(script)

    def _record_console_message(self, message: str) -> None:
        self.console_messages.append(message)
        self.console_message.emit(message)
