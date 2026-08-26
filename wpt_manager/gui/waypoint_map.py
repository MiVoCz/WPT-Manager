import json
import logging

from PySide6.QtCore import QObject, QEvent, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
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
      new ResizeObserver(() => {
        if (map) map.invalidateSize(false);
      }).observe(
        document.getElementById("map")
      );
      reportReady();
    }

    window.setWaypoints = function(waypoints) {
      if (!map || !markerLayer) {
        console.error("setWaypoints called before the map was ready.");
        return;
      }
      markerLayer.clearLayers();
      const bounds = [];
      for (const waypoint of waypoints) {
        const marker = L.marker([waypoint.latitude, waypoint.longitude]);
        marker.bindTooltip(waypoint.name);
        marker.on("click", () => {
          if (bridge) bridge.markerClicked(waypoint.id);
        });
        marker.addTo(markerLayer);
        bounds.push([waypoint.latitude, waypoint.longitude]);
      }
      if (bounds.length > 0) {
        map.fitBounds(bounds, {padding: [20, 20], maxZoom: 14});
      } else {
        map.setView(DEFAULT_CENTER, DEFAULT_ZOOM);
      }
    };

    window.addEventListener("load", initializeMap);
  </script>
</body>
</html>
"""


class MapBridge(QObject):
    marker_clicked = Signal(str)
    map_clicked = Signal(float, float)
    map_ready = Signal()

    @Slot()
    def mapReady(self) -> None:
        self.map_ready.emit()

    @Slot(str)
    def markerClicked(self, waypoint_id: str) -> None:
        self.marker_clicked.emit(waypoint_id)

    @Slot(float, float)
    def mapClicked(self, latitude: float, longitude: float) -> None:
        self.map_clicked.emit(latitude, longitude)

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
    map_clicked = Signal(float, float)
    console_message = Signal(str)

    def __init__(
        self,
        initial_map_source: ResolvedMapSource | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if initial_map_source is None:
            initial_map_source, _ = resolve_map_source(
                OPENSTREETMAP_SOURCE_ID,
                None,
            )
        self._waypoint_payload: list[dict[str, str | float]] = []
        self._map_source_payload = self._source_payload(initial_map_source)
        self._page_loaded = False
        self._map_ready = False
        self._view_visible = False
        self._initial_size_invalidated = False
        self._pending_update = True
        self._pending_map_source = True
        self.console_messages: list[str] = []
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(300, 300)
        self.web_profile = QWebEngineProfile(self)
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
        self.bridge.map_clicked.connect(self.map_clicked)
        self.bridge.map_ready.connect(self._handle_map_ready)
        self.web_page.console_message.connect(self._record_console_message)
        self.loadFinished.connect(self._handle_load_finished)
        self.first_visible_size.connect(
            self._handle_first_visible_size
        )

        self.setHtml(MAP_HTML, QUrl("https://localhost/"))

    @property
    def web_view(self) -> MapWebView:
        """Return the directly embedded web view for API compatibility."""
        return self

    def set_waypoints(self, waypoints: list[Waypoint]) -> None:
        self._waypoint_payload = [
            {
                "id": str(waypoint.id),
                "name": waypoint.name,
                "latitude": waypoint.latitude,
                "longitude": waypoint.longitude,
            }
            for waypoint in waypoints
        ]
        self._pending_update = True
        self._flush_pending_waypoints()

    def set_map_source(self, source: ResolvedMapSource) -> None:
        self._map_source_payload = self._source_payload(source)
        self._pending_map_source = True
        self._flush_pending_map_source()

    def _handle_load_finished(self, loaded: bool) -> None:
        self._page_loaded = loaded
        if not loaded:
            message = "Map HTML failed to load."
            LOGGER.error(message)
            self._record_console_message(message)
            return
        self._flush_pending_map_source()
        self._flush_pending_waypoints()

    def _handle_map_ready(self) -> None:
        self._map_ready = True
        self._flush_pending_map_source()
        self._invalidate_initial_size_if_ready()
        self._flush_pending_waypoints()

    def _handle_first_visible_size(self) -> None:
        self._view_visible = True
        self._invalidate_initial_size_if_ready()
        self._flush_pending_waypoints()

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
        self._execute_javascript(f"window.setWaypoints({payload});")
        self._pending_update = False

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
        self.web_page.runJavaScript(script)

    def _record_console_message(self, message: str) -> None:
        self.console_messages.append(message)
        self.console_message.emit(message)
