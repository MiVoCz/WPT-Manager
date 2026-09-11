"""Folder selection and local import of read-only ImageKit photo references."""

import sqlite3

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from wpt_manager.database.database import Database
from wpt_manager.models.photo import Photo
from wpt_manager.photos.imagekit import ImageKitPhotoSource
from wpt_manager.photos.import_service import import_source_items
from wpt_manager.photos.source import PhotoSourceError, PhotoSourceItem


class ImageKitImportDialog(QDialog):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import from ImageKit")
        self.database = database
        self.source: ImageKitPhotoSource | None = None
        self.items: list[PhotoSourceItem] = []
        self.imported: list[Photo] = []
        self.folder_edit = QLineEdit("/")
        self.load_button = QPushButton("Load")
        self.status_label = QLabel("Choose a folder and load photos.")
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.import_button = QPushButton("Import")
        self.import_button.setEnabled(False)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton(self.import_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        form = QFormLayout()
        form.addRow("Folder/path", self.folder_edit)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.load_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)
        self.load_button.clicked.connect(self.load_photos)
        self.import_button.clicked.connect(self.import_photos)
        self.folder_edit.textChanged.connect(self._clear_items)
        self.list_widget.itemSelectionChanged.connect(self._update_import_button)

    def _clear_items(self) -> None:
        self.source = None
        self.items = []
        self.list_widget.clear()
        self.status_label.setText("Choose a folder and load photos.")
        self._update_import_button()

    def _update_import_button(self) -> None:
        self.import_button.setEnabled(self.source is not None and bool(self.list_widget.selectedItems()))

    @property
    def selected_items(self) -> list[PhotoSourceItem]:
        return [self.items[row.data(256)] for row in self.list_widget.selectedItems()]

    def load_photos(self) -> None:
        self._clear_items()
        try:
            source = ImageKitPhotoSource(folder=self.folder_edit.text().strip() or "/")
            items = source.list_photos()
        except PhotoSourceError:
            # Never expose provider data or authentication details in a GUI error.
            QMessageBox.critical(
                self, "ImageKit", "Photos could not be loaded. Check the ImageKit key, permissions and connection."
            )
            return
        self.source = source
        self.items = items
        for index, item in enumerate(items):
            row = QListWidgetItem(item.name)
            row.setData(256, index)
            self.list_widget.addItem(row)
        self.list_widget.selectAll()
        self.status_label.setText(f"Images found: {len(items)}")
        self._update_import_button()

    def import_photos(self) -> None:
        selected = self.selected_items
        if self.source is None or not selected:
            return
        try:
            self.imported = import_source_items(self.database, self.source, selected)
        except sqlite3.Error:
            QMessageBox.critical(self, "ImageKit", "Photos could not be saved to the local database.")
            return
        QMessageBox.information(
            self, "ImageKit",
            f"Imported: {len(self.imported)}\nSkipped duplicates: {len(selected) - len(self.imported)}",
        )
        self.accept()
