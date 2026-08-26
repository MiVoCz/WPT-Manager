from PySide6.QtGui import QColor
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton, QVBoxLayout, QWidget

from wpt_manager.gui.waypoint_editor import WaypointEditor
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint
from wpt_manager.validation.waypoint_validator import validate_waypoint


class NewWaypointDialog(QDialog):
    def __init__(
        self,
        latitude: float,
        longitude: float,
        icon_catalog: list[IconInfo],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add waypoint")
        self.waypoint: Waypoint | None = None
        self.editor = WaypointEditor(icon_catalog)
        self.editor.setTitle("New waypoint")
        self.editor.show_waypoint(
            Waypoint(name="", latitude=latitude, longitude=longitude)
        )
        self.editor.save_button.setText("Create")
        self.cancel_button = QPushButton("Cancel")

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(self.cancel_button)

        self.editor.save_requested.connect(self._validate_and_accept)
        self.cancel_button.clicked.connect(self.reject)

    def _validate_and_accept(self) -> None:
        values = self.editor.values()
        waypoint = Waypoint(
            name=values.name,
            latitude=float(self.editor.latitude_edit.text()),
            longitude=float(self.editor.longitude_edit.text()),
            icon=values.icon,
            color=values.color,
            background=values.background,
            note=values.note,
            comment=values.comment,
        )
        errors = validate_waypoint(waypoint)
        color = QColor(waypoint.color)
        if not color.isValid():
            errors.append(
                "Waypoint color must be a valid Qt color or HEX value."
            )
        if errors:
            QMessageBox.warning(
                self,
                "Invalid waypoint",
                "\n".join(errors),
            )
            return

        waypoint.color = color.name(QColor.NameFormat.HexRgb).upper()
        self.waypoint = waypoint
        self.accept()
