import sqlite3
from pathlib import Path

from PySide6.QtCore import Qt
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
        self.background_edit = QLineEdit()
        self.note_edit = QLineEdit()
        self.comment_edit = QTextEdit()
        self.save_button = QPushButton("Save")

        editor_panel = QGroupBox("Waypoint editor")
        editor_layout = QVBoxLayout(editor_panel)
        editor_form = QFormLayout()
        editor_form.addRow(QLabel("Name"), self.name_edit)
        editor_form.addRow(QLabel("Icon"), self.icon_edit)
        editor_form.addRow(QLabel("Color"), self.color_edit)
        editor_form.addRow(QLabel("Background"), self.background_edit)
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
        self.load_collections()

    def load_collections(self) -> None:
        self.collection_list.clear()
        for collection in self.database.list_collections():
            item = QListWidgetItem(collection.name)
            item.setData(Qt.ItemDataRole.UserRole, collection.id)
            self.collection_list.addItem(item)

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
