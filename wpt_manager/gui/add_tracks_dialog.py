from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QVBoxLayout, QWidget,
)

from wpt_manager.models.track import Track


class AddTracksDialog(QDialog):
    def __init__(
        self, tracks: list[Track], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Existing Tracks")
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        for track in tracks:
            item = QListWidgetItem(
                f"{track.name} — {track.distance_m / 1000:.1f} km"
            )
            item.setData(Qt.ItemDataRole.UserRole, track.id)
            self.track_list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(self.track_list)
        layout.addWidget(buttons)

    @property
    def selected_track_ids(self) -> list[UUID]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.track_list.selectedItems()
        ]
