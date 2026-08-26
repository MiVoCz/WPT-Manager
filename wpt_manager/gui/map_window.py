from uuid import UUID

from PySide6.QtCore import Signal, Slot, Qt
from PySide6.QtWidgets import QComboBox, QLabel, QMainWindow, QToolBar, QWidget

from wpt_manager.gui.waypoint_map import WaypointMap
from wpt_manager.models.waypoint import Waypoint


class MapWindow(QMainWindow):
    marker_clicked = Signal(object)
    map_clicked = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("WPT-Manager Map")
        self.resize(900, 700)
        self.selected_waypoint_ids: list[UUID] = []

        toolbar = QToolBar("Map controls", self)
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("Map Source:"))
        self.map_source_combo = QComboBox()
        self.map_source_combo.addItem("OpenStreetMap")
        toolbar.addWidget(self.map_source_combo)
        self.addToolBar(toolbar)

        self.waypoint_map = WaypointMap()
        self.setCentralWidget(self.waypoint_map)
        self.waypoint_map.marker_clicked.connect(self._emit_marker_clicked)
        self.waypoint_map.map_clicked.connect(self.map_clicked)

    def set_waypoints(self, waypoints: list[Waypoint]) -> None:
        self.waypoint_map.set_waypoints(waypoints)

    def set_selected_waypoint_ids(self, waypoint_ids: list[UUID]) -> None:
        self.selected_waypoint_ids = list(waypoint_ids)

    @Slot(str)
    def _emit_marker_clicked(self, waypoint_id: str) -> None:
        self.marker_clicked.emit(UUID(waypoint_id))
