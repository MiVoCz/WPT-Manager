import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QTextEdit,
)

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.models.collection import Collection


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


def test_main_window_defaults(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)

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
    assert window.collection_list.count() == 0

    window.close()
    application.processEvents()


def test_main_window_loads_collections_with_uuid(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first = Collection(name="Francie")
    second = Collection(name="Itálie")
    database.save_collection(first)
    database.save_collection(second)

    window = MainWindow(database)

    assert window.collection_list.count() == 2
    assert window.collection_list.item(0).text() == "Francie"
    assert window.collection_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == first.id
    assert window.collection_list.item(1).text() == "Itálie"
    assert window.collection_list.item(1).data(
        Qt.ItemDataRole.UserRole
    ) == second.id

    window.close()
    application.processEvents()


def test_import_button_imports_gpx_and_reloads_collections(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    messages = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(TEST_DATA), "GPX files (*.gpx)"),
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: (kwargs["text"], True),
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.import_button.click()

    collections = database.list_collections()
    assert len(collections) == 1
    assert collections[0].name == "mapy_export"
    assert window.collection_list.count() == 1
    assert window.collection_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == collections[0].id
    assert messages == ['Collection "mapy_export" was imported.']

    window.close()
    application.processEvents()


def test_import_button_shows_error_message(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    messages = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(TEST_DATA), "GPX files (*.gpx)"),
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *args, **kwargs: ("Chybný import", True),
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.import_gpx",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            GpxReaderError("Invalid GPX")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.import_button.click()

    assert database.list_collections() == []
    assert window.collection_list.count() == 0
    assert messages == [
        "The GPX file could not be imported:\nInvalid GPX"
    ]

    window.close()
    application.processEvents()
