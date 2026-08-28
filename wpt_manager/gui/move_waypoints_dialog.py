from uuid import UUID

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.models.collection import Collection


class MoveWaypointsDialog(QDialog):
    def __init__(
        self,
        waypoint_count: int,
        target_collections: list[Collection],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.setWindowTitle("Move Waypoints")

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(f"Move {waypoint_count} selected waypoint(s) to:")
        )
        form = QFormLayout()
        self.collection_combo = QComboBox()
        for collection in target_collections:
            self.collection_combo.addItem(collection.name, collection.id)
        form.addRow("Collection:", self.collection_combo)
        layout.addLayout(form)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        self.move_button = self.button_box.addButton(
            "Move",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        layout.addWidget(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    @property
    def target_collection_id(self) -> UUID | None:
        value = self.collection_combo.currentData()
        return value if isinstance(value, UUID) else None
