import base64
from dataclasses import replace
from uuid import UUID

from PySide6.QtCore import QPoint, QSignalBlocker, Signal, Slot, Qt
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.config import ApplicationConfig, load_application_config
from wpt_manager.gui.waypoint_map import WaypointMap
from wpt_manager.map_sources import (
    MAP_SOURCES,
    OPENSTREETMAP_SOURCE_ID,
    default_map_source_id,
    resolve_map_source,
)
from wpt_manager.mapy_search import (
    SEARCH_RESULT_TYPES,
    MapSearchResult,
    MapySearchClient,
    build_mapy_show_url,
)
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_duplicates import geographic_distance_m


def format_distance_m(distance_m: float) -> str:
    if distance_m < 1_000:
        return f"{distance_m:.0f} m"
    return f"{distance_m / 1_000:.1f} km"


def build_icon_data_urls(icon_catalog: list[IconInfo]) -> dict[str, str]:
    paths_by_name = {}
    for icon in icon_catalog:
        paths_by_name.setdefault(icon.icon_name, icon.svg_path)

    data_urls = {}
    for icon_name, svg_path in paths_by_name.items():
        try:
            encoded_svg = base64.b64encode(svg_path.read_bytes()).decode("ascii")
        except OSError:
            continue
        data_urls[icon_name] = f"data:image/svg+xml;base64,{encoded_svg}"
    return data_urls


class MapWindow(QMainWindow):
    marker_clicked = Signal(object)
    map_clicked = Signal(float, float)
    add_waypoint_requested = Signal(float, float)

    def __init__(
        self,
        parent: QWidget | None = None,
        config: ApplicationConfig | None = None,
        icon_catalog: list[IconInfo] | None = None,
        search_client: MapySearchClient | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.config = config or load_application_config()
        self.setWindowTitle("WPT-Manager Map")
        self.resize(900, 700)
        self.selected_waypoint_ids: list[UUID] = []
        self._viewport_bbox: tuple[float, float, float, float] | None = None
        self._search_waypoint_position: tuple[float, float] | None = None
        self._selected_search_result: MapSearchResult | None = None
        self._search_result_types: tuple[str, ...] = ()
        self._search_reference_point: tuple[float, float] | None = None

        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        content_splitter = QSplitter(
            Qt.Orientation.Horizontal,
            central_widget,
        )
        self.setCentralWidget(central_widget)

        toolbar = QToolBar("Map controls", central_widget)
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("Map Source:"))
        self.map_source_combo = QComboBox()
        for source in MAP_SOURCES:
            self.map_source_combo.addItem(source.label, source.id)
        toolbar.addWidget(self.map_source_combo)
        self.map_source_status = QLabel()
        toolbar.addWidget(self.map_source_status)
        central_layout.addWidget(toolbar)
        central_layout.addWidget(content_splitter, 1)

        initial_source_id = default_map_source_id(self.config.mapy_api_key)
        initial_source, _ = resolve_map_source(
            initial_source_id,
            self.config.mapy_api_key,
        )
        self.map_source_combo.setCurrentIndex(
            self.map_source_combo.findData(initial_source_id)
        )
        self._update_map_source_status()
        self.search_client = search_client or MapySearchClient(
            self.config.mapy_api_key,
            self,
        )
        search_panel = self._build_search_panel(content_splitter)
        web_profile = QWebEngineProfile(self)
        self.waypoint_map = WaypointMap(
            initial_source,
            build_icon_data_urls(icon_catalog or []),
            web_profile,
            content_splitter,
        )
        content_splitter.addWidget(self.waypoint_map)
        content_splitter.addWidget(search_panel)
        content_splitter.setStretchFactor(0, 4)
        content_splitter.setStretchFactor(1, 1)
        content_splitter.setCollapsible(0, False)
        content_splitter.setCollapsible(1, False)
        content_splitter.setSizes([620, 280])
        self.waypoint_map.marker_clicked.connect(self._emit_marker_clicked)
        self.waypoint_map.map_clicked.connect(self.map_clicked)
        self.waypoint_map.map_context_menu_requested.connect(
            self._show_map_context_menu
        )
        self.waypoint_map.viewport_changed.connect(self._set_viewport_bbox)
        self.map_source_combo.currentIndexChanged.connect(
            self._change_map_source
        )
        self.search_button.clicked.connect(self._start_search)
        self.search_edit.returnPressed.connect(self._start_search)
        self.search_results.currentItemChanged.connect(
            self._select_search_result
        )
        self.search_client.results_ready.connect(self._show_search_results)
        self.search_client.error_occurred.connect(self._show_search_error)
        self.open_search_result_button.clicked.connect(
            self._open_search_result_in_mapy
        )
        search_available = self.search_client.is_available
        self.search_edit.setEnabled(search_available)
        self.search_button.setEnabled(search_available)
        if not search_available:
            self.search_status.setText(
                "Mapy.com search requires a configured API key."
            )

    def _build_search_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        panel.setMinimumWidth(280)
        layout = QVBoxLayout(panel)
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search Mapy.com")
        self.search_button = QPushButton("Search")
        search_row.addWidget(self.search_edit)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)
        filters = QFormLayout()
        self.search_type_combo = QComboBox()
        for label, result_types in SEARCH_RESULT_TYPES:
            self.search_type_combo.addItem(label, result_types)
        self.search_type_combo.currentIndexChanged.connect(
            self._change_search_type
        )
        self._change_search_type()
        filters.addRow("Type:", self.search_type_combo)
        self.search_area_combo = QComboBox()
        self.search_area_combo.addItem("Current map", "current-map")
        self.search_area_combo.addItem(
            "Near selected waypoint",
            "near-waypoint",
        )
        filters.addRow("Search area:", self.search_area_combo)
        self.search_radius_label = QLabel("Radius:")
        self.search_radius_combo = QComboBox()
        for radius_km in (1, 2, 5, 10, 20, 50):
            self.search_radius_combo.addItem(
                f"{radius_km} km",
                radius_km * 1_000,
            )
        self.search_radius_combo.setCurrentIndex(
            self.search_radius_combo.findData(5_000)
        )
        self.search_radius_combo.setToolTip(
            "This radius only prefers nearby results; it is not a hard filter."
        )
        filters.addRow(self.search_radius_label, self.search_radius_combo)
        layout.addLayout(filters)
        self.search_status = QLabel()
        self.search_status.setWordWrap(True)
        self.search_results = QListWidget()
        layout.addWidget(self.search_status)
        layout.addWidget(self.search_results)

        detail = QGroupBox("Selected result")
        detail_layout = QFormLayout(detail)
        self.search_detail_labels = {
            "name": QLabel(""),
            "label": QLabel(""),
            "location": QLabel(""),
            "latitude": QLabel(""),
            "longitude": QLabel(""),
        }
        for caption, key in (
            ("Name:", "name"),
            ("Label:", "label"),
            ("Location:", "location"),
            ("Latitude:", "latitude"),
            ("Longitude:", "longitude"),
        ):
            self.search_detail_labels[key].setWordWrap(True)
            detail_layout.addRow(caption, self.search_detail_labels[key])
        self.add_search_result_button = QPushButton("Add as Waypoint")
        self.add_search_result_button.setEnabled(False)
        detail_layout.addRow(self.add_search_result_button)
        self.open_search_result_button = QPushButton("Open in Mapy.com")
        self.open_search_result_button.setEnabled(False)
        detail_layout.addRow(self.open_search_result_button)
        layout.addWidget(detail)
        self.search_area_combo.currentIndexChanged.connect(
            self._change_search_area
        )
        self._change_search_area()
        return panel

    def set_search_waypoint(self, waypoint: Waypoint | None) -> None:
        self._search_waypoint_position = (
            (waypoint.latitude, waypoint.longitude)
            if waypoint is not None
            else None
        )
        if (
            waypoint is None
            and self.search_area_combo.currentData() == "near-waypoint"
        ):
            with QSignalBlocker(self.search_area_combo):
                self.search_area_combo.setCurrentIndex(
                    self.search_area_combo.findData("current-map")
                )
            self.search_status.setText(
                "Select one waypoint to search near it."
            )
        self._update_radius_visibility()

    @Slot()
    def _change_search_area(self) -> None:
        if (
            self.search_area_combo.currentData() == "near-waypoint"
            and self._search_waypoint_position is None
        ):
            with QSignalBlocker(self.search_area_combo):
                self.search_area_combo.setCurrentIndex(
                    self.search_area_combo.findData("current-map")
                )
            self.search_status.setText(
                "Select one waypoint to search near it."
            )
        self._update_radius_visibility()

    def _update_radius_visibility(self) -> None:
        is_near = self.search_area_combo.currentData() == "near-waypoint"
        self.search_radius_label.setVisible(is_near)
        self.search_radius_combo.setVisible(is_near)

    @Slot()
    def _change_search_type(self) -> None:
        result_types = self.search_type_combo.currentData()
        self._search_result_types = (
            tuple(result_types) if result_types is not None else ()
        )

    @Slot(float, float, float, float)
    def _set_viewport_bbox(
        self,
        west: float,
        south: float,
        east: float,
        north: float,
    ) -> None:
        self._viewport_bbox = (west, south, east, north)

    @Slot()
    def _start_search(self) -> None:
        query = self.search_edit.text().strip()
        if not query:
            self.search_status.setText("Enter a search query.")
            return
        self.search_status.setText("Searching…")
        self.search_results.clear()
        self.search_button.setEnabled(False)
        if self.search_area_combo.currentData() == "near-waypoint":
            if self._search_waypoint_position is None:
                self._show_search_error(
                    "Select one waypoint to search near it."
                )
                return
            latitude, longitude = self._search_waypoint_position
            self._search_reference_point = (latitude, longitude)
            self.search_status.setText(
                "Searching with the selected waypoint as a preference…"
            )
            self.search_client.search(
                query,
                result_types=self._search_result_types,
                prefer_near=(longitude, latitude),
                prefer_near_precision=self.search_radius_combo.currentData(),
            )
            return
        self._search_reference_point = self._viewport_center()
        self.search_client.search(
            query,
            prefer_bbox=self._viewport_bbox,
            result_types=self._search_result_types,
        )

    @Slot(list)
    def _show_search_results(self, results: list[MapSearchResult]) -> None:
        self.search_button.setEnabled(self.search_client.is_available)
        self.search_results.clear()
        if not results:
            self.search_status.setText("No results")
            return
        self.search_status.clear()
        sorted_results = self._results_by_distance(results)
        for result in sorted_results:
            lines = [result.name, result.label]
            if result.location:
                lines.append(result.location)
            if result.distance_m is not None:
                lines.append(format_distance_m(result.distance_m))
            item = QListWidgetItem("\n".join(lines))
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.search_results.addItem(item)

    def _viewport_center(self) -> tuple[float, float] | None:
        if self._viewport_bbox is None:
            return None
        west, south, east, north = self._viewport_bbox
        return ((south + north) / 2, (west + east) / 2)

    def _results_by_distance(
        self,
        results: list[MapSearchResult],
    ) -> list[MapSearchResult]:
        reference = self._search_reference_point
        if reference is None:
            return list(results)
        reference_latitude, reference_longitude = reference
        with_distances = [
            replace(
                result,
                distance_m=geographic_distance_m(
                    reference_latitude,
                    reference_longitude,
                    result.latitude,
                    result.longitude,
                ),
            )
            for result in results
        ]
        return sorted(
            with_distances,
            key=lambda result: (
                result.distance_m,
                result.name.casefold(),
                result.name,
                result.label.casefold(),
                result.latitude,
                result.longitude,
            ),
        )

    @Slot(str)
    def _show_search_error(self, message: str) -> None:
        self.search_button.setEnabled(self.search_client.is_available)
        self.search_results.clear()
        self.search_status.setText(message)

    @Slot(QListWidgetItem, QListWidgetItem)
    def _select_search_result(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self._selected_search_result = None
            self.open_search_result_button.setEnabled(False)
            return
        result = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(result, MapSearchResult):
            return
        self._selected_search_result = result
        self.open_search_result_button.setEnabled(True)
        self.search_detail_labels["name"].setText(result.name)
        self.search_detail_labels["label"].setText(result.label)
        self.search_detail_labels["location"].setText(result.location or "")
        self.search_detail_labels["latitude"].setText(
            f"{result.latitude:.7f}"
        )
        self.search_detail_labels["longitude"].setText(
            f"{result.longitude:.7f}"
        )
        self.waypoint_map.set_search_result(
            result.name,
            result.latitude,
            result.longitude,
        )

    @Slot()
    def _open_search_result_in_mapy(self) -> None:
        result = self._selected_search_result
        if result is None:
            return
        QDesktopServices.openUrl(
            build_mapy_show_url(result.latitude, result.longitude)
        )

    def set_waypoints(
        self,
        waypoints: list[Waypoint],
        fit_viewport: bool = True,
    ) -> None:
        self.waypoint_map.set_waypoints(waypoints, fit_viewport)

    def set_selected_waypoint_ids(self, waypoint_ids: list[UUID]) -> None:
        self.selected_waypoint_ids = list(waypoint_ids)
        self.waypoint_map.set_selected_waypoint_ids(waypoint_ids)

    @Slot()
    def _change_map_source(self) -> None:
        source_id = self.map_source_combo.currentData()
        source, fell_back = resolve_map_source(
            source_id,
            self.config.mapy_api_key,
        )
        if fell_back:
            with QSignalBlocker(self.map_source_combo):
                self.map_source_combo.setCurrentIndex(
                    self.map_source_combo.findData(OPENSTREETMAP_SOURCE_ID)
                )
        self.waypoint_map.set_map_source(source)
        self._update_map_source_status()

    def _update_map_source_status(self) -> None:
        if self.config.mapy_api_key:
            self.map_source_status.clear()
        else:
            self.map_source_status.setText(
                "Mapy.com API key is not configured; using OpenStreetMap."
            )

    @Slot(float, float, int, int)
    def _show_map_context_menu(
        self,
        latitude: float,
        longitude: float,
        x: int,
        y: int,
    ) -> None:
        menu = QMenu(self)
        action = menu.addAction("Add waypoint here")
        action.triggered.connect(
            lambda: self.add_waypoint_requested.emit(latitude, longitude)
        )
        self._map_context_menu = menu
        menu.popup(self.waypoint_map.mapToGlobal(QPoint(x, y)))

    @Slot(str)
    def _emit_marker_clicked(self, waypoint_id: str) -> None:
        self.marker_clicked.emit(UUID(waypoint_id))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.waypoint_map.release_web_engine()
        super().closeEvent(event)
