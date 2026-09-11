from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from wpt_manager.photos.source import PhotoSourceItem


class SynologyCredentialsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import from Synology Photos")
        self.url_edit = QLineEdit()
        self.nas_url_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout()
        form.addRow("Share URL", self.url_edit)
        form.addRow("NAS / DDNS address", self.nas_url_edit)
        form.addRow("Password", self.password_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        help_text = QLabel(
            "QuickConnect share links can identify the shared album, but direct "
            "Synology Photos API access may require your NAS/DDNS address."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addLayout(form)
        layout.addWidget(buttons)


class SynologyPhotoSelectionDialog(QDialog):
    def __init__(
        self, items: list[PhotoSourceItem], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Synology Photos")
        self.items = items
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        for index, item in enumerate(items):
            row = QListWidgetItem(item.name)
            row.setData(256, index)
            self.list_widget.addItem(row)
        self.list_widget.selectAll()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Photos found: {len(items)}"))
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)

    @property
    def selected_items(self) -> list[PhotoSourceItem]:
        return [self.items[row.data(256)] for row in self.list_widget.selectedItems()]
