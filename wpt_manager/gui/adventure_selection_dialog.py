from collections import Counter
from uuid import UUID

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QWidget

from wpt_manager.models.adventure import Adventure


class AdventureSelectionDialog(QDialog):
    """Select an Adventure by UUID, optionally choosing an import destination."""

    def __init__(
        self, adventures: list[Adventure], parent: QWidget | None = None,
        *, for_import: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Track Import" if for_import else "Add Tracks to Adventure")
        self.adventure_combo = QComboBox()
        if for_import:
            self.adventure_combo.addItem("Standalone Tracks", "standalone")
        counts = Counter(adventure.name for adventure in adventures)
        for adventure in adventures:
            label = adventure.name
            if counts[label] > 1:
                label = f"{label} ({adventure.uuid})"
            self.adventure_combo.addItem(label, str(adventure.uuid))
        if for_import:
            self.adventure_combo.addItem("New Adventure", "new")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.adventure_combo.count() > 0)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow("Import destination:" if for_import else "Adventure:", self.adventure_combo)
        layout.addRow(buttons)

    @property
    def selected_destination(self) -> UUID | str | None:
        value = self.adventure_combo.currentData()
        return value if value in {None, "standalone", "new"} else UUID(value)
