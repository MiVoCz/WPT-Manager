from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class UserDataFolderDialog(QDialog):
    def __init__(
        self,
        current_directory: Path,
        parent: QWidget | None = None,
        *,
        first_run: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            "Choose user data folder" if first_run else "User data folder"
        )
        layout = QVBoxLayout(self)
        if first_run:
            layout.addWidget(
                QLabel("Choose where WPT-Manager will store your data.")
            )
        row = QHBoxLayout()
        self.path_edit = QLineEdit(str(current_directory))
        self.browse_button = QPushButton("Browse...")
        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_button)
        layout.addLayout(row)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        layout.addWidget(self.buttons)
        self.browse_button.clicked.connect(self._browse)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(
            QDialogButtonBox.StandardButton.Apply
        ).clicked.connect(self._apply)

    @property
    def selected_directory(self) -> Path:
        return Path(self.path_edit.text().strip()).expanduser()

    @Slot()
    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose user data folder",
            self.path_edit.text(),
        )
        if selected:
            self.path_edit.setText(selected)

    @Slot()
    def _apply(self) -> None:
        if not self.path_edit.text().strip():
            QMessageBox.warning(
                self,
                "User data folder",
                "Choose a user data folder.",
            )
            return
        self.accept()
