from uuid import UUID

from PySide6.QtCore import QSignalBlocker, Signal, Slot, Qt
from PySide6.QtWidgets import QComboBox, QLabel, QMainWindow, QToolBar, QWidget

from wpt_manager.config import ApplicationConfig, load_application_config
from wpt_manager.gui.waypoint_map import WaypointMap
from wpt_manager.map_sources import (
    MAP_SOURCES,
    OPENSTREETMAP_SOURCE_ID,
    default_map_source_id,
    resolve_map_source,
)
from wpt_manager.models.waypoint import Waypoint


class MapWindow(QMainWindow):
    marker_clicked = Signal(object)
    map_clicked = Signal(float, float)

    def __init__(
        self,
        parent: QWidget | None = None,
        config: ApplicationConfig | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.config = config or load_application_config()
        self.setWindowTitle("WPT-Manager Map")
        self.resize(900, 700)
        self.selected_waypoint_ids: list[UUID] = []

        toolbar = QToolBar("Map controls", self)
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("Map Source:"))
        self.map_source_combo = QComboBox()
        for source in MAP_SOURCES:
            self.map_source_combo.addItem(source.label, source.id)
        toolbar.addWidget(self.map_source_combo)
        self.map_source_status = QLabel()
        toolbar.addWidget(self.map_source_status)
        self.addToolBar(toolbar)

        initial_source_id = default_map_source_id(self.config.mapy_api_key)
        initial_source, _ = resolve_map_source(
            initial_source_id,
            self.config.mapy_api_key,
        )
        self.map_source_combo.setCurrentIndex(
            self.map_source_combo.findData(initial_source_id)
        )
        self._update_map_source_status()
        self.waypoint_map = WaypointMap(initial_source)
        self.setCentralWidget(self.waypoint_map)
        self.waypoint_map.marker_clicked.connect(self._emit_marker_clicked)
        self.waypoint_map.map_clicked.connect(self.map_clicked)
        self.map_source_combo.currentIndexChanged.connect(
            self._change_map_source
        )

    def set_waypoints(self, waypoints: list[Waypoint]) -> None:
        self.waypoint_map.set_waypoints(waypoints)

    def set_selected_waypoint_ids(self, waypoint_ids: list[UUID]) -> None:
        self.selected_waypoint_ids = list(waypoint_ids)

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

    @Slot(str)
    def _emit_marker_clicked(self, waypoint_id: str) -> None:
        self.marker_clicked.emit(UUID(waypoint_id))
