from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
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
