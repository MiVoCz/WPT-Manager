from uuid import UUID

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
        collections: list[tuple[UUID, str]],
        selected_collection_id: UUID | None = None,
        parent: QWidget | None = None,
        *,
        name: str = "",
        note: str = "",
        comment: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add waypoint")
        self.waypoint: Waypoint | None = None
        self.collection_id: UUID | None = None
        self.collection_combo = QComboBox()
        for collection_id, collection_name in collections:
            self.collection_combo.addItem(collection_name, collection_id)
        selected_index = self.collection_combo.findData(selected_collection_id)
        if selected_index >= 0:
            self.collection_combo.setCurrentIndex(selected_index)

        self.editor = WaypointEditor(icon_catalog)
        self.editor.setTitle("New waypoint")
        self.editor.show_waypoint(
            Waypoint(
                name=name,
                latitude=latitude,
                longitude=longitude,
                note=note,
                comment=comment,
            )
        )
        self.editor.save_button.setText("Create")
        self.cancel_button = QPushButton("Cancel")

        layout = QVBoxLayout(self)
        collection_layout = QFormLayout()
        collection_layout.addRow("Collection:", self.collection_combo)
        layout.addLayout(collection_layout)
        layout.addWidget(self.editor)
        layout.addWidget(self.cancel_button)

        self.editor.save_button.setEnabled(bool(collections))

        self.editor.save_requested.connect(self._validate_and_accept)
        self.cancel_button.clicked.connect(self.reject)

    def _validate_and_accept(self) -> None:
        collection_id = self.collection_combo.currentData()
        if not isinstance(collection_id, UUID):
            QMessageBox.warning(
                self,
                "Collection required",
                "Select a collection for the waypoint.",
            )
            return

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
        self.collection_id = collection_id
        self.accept()
