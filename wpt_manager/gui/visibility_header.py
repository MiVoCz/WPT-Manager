from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QWidget


class VisibilityHeaderCheckBox(QCheckBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Visible", parent)
        self.setTristate(True)
        self.setEnabled(False)

    def nextCheckState(self) -> None:
        self.setCheckState(
            Qt.CheckState.Unchecked
            if self.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )
