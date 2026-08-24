import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.database import Database
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_importer import import_gpx
from wpt_manager.validation.waypoint_validator import validate_waypoint


class MainWindow(QMainWindow):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self.database = database
        self.setWindowTitle("WPT-Manager")
        self.resize(1000, 700)

        self.collection_list = QListWidget()
        self.import_button = QPushButton("Import GPX")
        self.export_button = QPushButton("Export GPX")

        collection_panel = QGroupBox("Collections")
        collection_layout = QVBoxLayout(collection_panel)
        collection_layout.addWidget(self.collection_list)

        collection_buttons = QHBoxLayout()
        collection_buttons.addWidget(self.import_button)
        collection_buttons.addWidget(self.export_button)
        collection_layout.addLayout(collection_buttons)

        self.waypoint_list = QListWidget()

        waypoint_panel = QGroupBox("Waypoints")
        waypoint_layout = QVBoxLayout(waypoint_panel)
        waypoint_layout.addWidget(self.waypoint_list)

        self.name_edit = QLineEdit()
        self.icon_edit = QLineEdit()
        self.color_edit = QLineEdit()
        self.color_preview = QLabel()
        self.color_preview.setFixedSize(24, 24)
        self.background_edit = QLineEdit()
        self.latitude_edit = QLineEdit()
        self.latitude_edit.setReadOnly(True)
        self.longitude_edit = QLineEdit()
        self.longitude_edit.setReadOnly(True)
        self.note_edit = QLineEdit()
        self.comment_edit = QTextEdit()
        self.save_button = QPushButton("Save")
        self.save_button.setEnabled(False)

        editor_panel = QGroupBox("Waypoint editor")
        editor_layout = QVBoxLayout(editor_panel)
        editor_form = QFormLayout()
        editor_form.addRow(QLabel("Name"), self.name_edit)
        editor_form.addRow(QLabel("Icon"), self.icon_edit)

        color_editor = QWidget()
        color_layout = QHBoxLayout(color_editor)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.addWidget(self.color_edit)
        color_layout.addWidget(self.color_preview)
        editor_form.addRow(QLabel("Color"), color_editor)
        editor_form.addRow(QLabel("Background"), self.background_edit)
        editor_form.addRow(QLabel("Latitude"), self.latitude_edit)
        editor_form.addRow(QLabel("Longitude"), self.longitude_edit)
        editor_form.addRow(QLabel("Note"), self.note_edit)
        editor_form.addRow(QLabel("Comment"), self.comment_edit)
        editor_layout.addLayout(editor_form)
        editor_layout.addWidget(self.save_button)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(waypoint_panel)
        self.right_splitter.addWidget(editor_panel)
        self.right_splitter.setStretchFactor(0, 2)
        self.right_splitter.setStretchFactor(1, 3)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(collection_panel)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([250, 750])

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.addWidget(self.main_splitter)
        self.setCentralWidget(central_widget)

        self.import_button.clicked.connect(self.import_gpx_file)
        self.collection_list.currentItemChanged.connect(
            self.load_waypoints
        )
        self.waypoint_list.currentItemChanged.connect(
            self.load_waypoint
        )
        self.save_button.clicked.connect(self.save_waypoint)
        self.load_collections()

    def load_collections(self) -> None:
        self.collection_list.clear()
        for collection in self.database.list_collections():
            item = QListWidgetItem(collection.name)
            item.setData(Qt.ItemDataRole.UserRole, collection.id)
            self.collection_list.addItem(item)

    def load_waypoints(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
    ) -> None:
        del previous_item
        self.waypoint_list.clear()
        if current_item is None:
            return

        collection_id = current_item.data(Qt.ItemDataRole.UserRole)
        for waypoint in self.database.list_waypoints(collection_id):
            item = QListWidgetItem(waypoint.name)
            item.setData(Qt.ItemDataRole.UserRole, waypoint.id)
            self.waypoint_list.addItem(item)

    def load_waypoint(
        self,
        current_item: QListWidgetItem | None,
        previous_item: QListWidgetItem | None = None,
    ) -> None:
        del previous_item
        self.clear_waypoint_editor()
        if current_item is None:
            return

        waypoint_id = current_item.data(Qt.ItemDataRole.UserRole)
        waypoint = self.database.get_waypoint(waypoint_id)
        if waypoint is None:
            return

        self.name_edit.setText(waypoint.name)
        self.icon_edit.setText(waypoint.icon)
        self.color_edit.setText(waypoint.color)
        self.update_color_preview(waypoint.color)
        self.background_edit.setText(waypoint.background)
        self.latitude_edit.setText(str(waypoint.latitude))
        self.longitude_edit.setText(str(waypoint.longitude))
        self.note_edit.setText(waypoint.note)
        self.comment_edit.setPlainText(waypoint.comment)
        self.save_button.setEnabled(True)

    def clear_waypoint_editor(self) -> None:
        self.name_edit.clear()
        self.icon_edit.clear()
        self.color_edit.clear()
        self.update_color_preview("")
        self.background_edit.clear()
        self.latitude_edit.clear()
        self.longitude_edit.clear()
        self.note_edit.clear()
        self.comment_edit.clear()
        self.save_button.setEnabled(False)

    def update_color_preview(self, color_value: str) -> None:
        color = QColor(color_value)
        if not color.isValid():
            self.color_preview.setAutoFillBackground(False)
            self.color_preview.setPalette(QPalette())
            return

        palette = self.color_preview.palette()
        palette.setColor(QPalette.ColorRole.Window, color)
        self.color_preview.setPalette(palette)
        self.color_preview.setAutoFillBackground(True)

    def save_waypoint(self) -> None:
        current_item = self.waypoint_list.currentItem()
        if current_item is None:
            return

        waypoint_id = current_item.data(Qt.ItemDataRole.UserRole)
        waypoint = self.database.get_waypoint(waypoint_id)
        if waypoint is None:
            self.clear_waypoint_editor()
            return

        waypoint.name = self.name_edit.text()
        waypoint.icon = self.icon_edit.text()
        waypoint.color = self.color_edit.text()
        waypoint.background = self.background_edit.text()
        waypoint.note = self.note_edit.text()
        waypoint.comment = self.comment_edit.toPlainText()

        errors = validate_waypoint(waypoint)
        if not QColor(waypoint.color).isValid():
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

        try:
            self.database.update_waypoint(waypoint)
        except (sqlite3.Error, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Save waypoint failed",
                f"The waypoint could not be saved:\n{exc}",
            )
            return

        current_item.setText(waypoint.name)
        self.load_waypoint(current_item)
        QMessageBox.information(
            self,
            "Save waypoint",
            f'Waypoint "{waypoint.name}" was saved.',
        )

    def import_gpx_file(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import GPX",
            "",
            "GPX files (*.gpx)",
        )
        if not selected_path:
            return

        source_path = Path(selected_path)
        collection_name, accepted = QInputDialog.getText(
            self,
            "Import GPX",
            "Collection name:",
            text=source_path.stem,
        )
        if not accepted or not collection_name.strip():
            return

        try:
            collection = import_gpx(
                self.database,
                source_path,
                collection_name.strip(),
            )
        except (GpxReaderError, sqlite3.Error) as exc:
            QMessageBox.critical(
                self,
                "Import GPX failed",
                f"The GPX file could not be imported:\n{exc}",
            )
            return

        self.load_collections()
        QMessageBox.information(
            self,
            "Import GPX",
            f'Collection "{collection.name}" was imported.',
        )
