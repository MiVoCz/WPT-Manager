import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit

from wpt_manager.gui.main_window import MainWindow


def test_main_window_defaults():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.windowTitle() == "WPT-Manager"
    assert window.size().width() == 1000
    assert window.size().height() == 700
    assert window.main_splitter.orientation() == Qt.Orientation.Horizontal
    assert window.main_splitter.count() == 2
    assert window.right_splitter.orientation() == Qt.Orientation.Vertical
    assert window.right_splitter.count() == 2

    assert isinstance(window.name_edit, QLineEdit)
    assert isinstance(window.icon_edit, QLineEdit)
    assert isinstance(window.color_edit, QLineEdit)
    assert isinstance(window.background_edit, QLineEdit)
    assert isinstance(window.note_edit, QLineEdit)
    assert isinstance(window.comment_edit, QTextEdit)

    assert window.import_button.text() == "Import GPX"
    assert window.export_button.text() == "Export GPX"
    assert window.save_button.text() == "Save"

    window.close()
    application.processEvents()
