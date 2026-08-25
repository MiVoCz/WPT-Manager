import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QTextEdit,
)

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.io.gpx_reader import load_gpx
from wpt_manager.models.collection import Collection
from wpt_manager.models.icon import IconInfo
from wpt_manager.models.waypoint import Waypoint


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
    assert window.icon_preview.width() == 32
    assert window.icon_preview.height() == 32
    assert window.icon_button.text() == "Select..."
    assert isinstance(window.color_edit, QLineEdit)
    assert window.color_preview.width() == 24
    assert window.color_preview.height() == 24
    assert isinstance(window.background_combo, QComboBox)
    assert [
        window.background_combo.itemText(index)
        for index in range(window.background_combo.count())
    ] == ["circle", "square", "octagon"]
    assert isinstance(window.latitude_edit, QLineEdit)
    assert window.latitude_edit.isReadOnly()
    assert isinstance(window.longitude_edit, QLineEdit)
    assert window.longitude_edit.isReadOnly()
    assert isinstance(window.note_edit, QLineEdit)
    assert isinstance(window.comment_edit, QTextEdit)

    assert window.import_button.text() == "Import GPX"
    assert window.export_button.text() == "Export GPX"
    assert not window.export_button.isEnabled()
    assert window.color_button.text() == "Choose color"
    assert window.save_button.text() == "Save"
    assert not window.save_button.isEnabled()
    assert window.collection_list.count() == 0
    assert window.waypoint_list.selectionMode() == (
        QAbstractItemView.SelectionMode.ExtendedSelection
    )

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


def test_selecting_collection_loads_its_waypoints(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first_collection = Collection(name="Francie")
    second_collection = Collection(name="Itálie")
    empty_collection = Collection(name="Prázdná")
    database.save_collection(first_collection)
    database.save_collection(second_collection)
    database.save_collection(empty_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    second_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(first_waypoint, first_collection.id)
    database.save_waypoint(second_waypoint, second_collection.id)
    window = MainWindow(database)

    assert window.waypoint_list.count() == 0

    window.collection_list.setCurrentRow(0)
    assert window.export_button.isEnabled()
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).text() == "Pont du Gard"
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == first_waypoint.id

    window.collection_list.setCurrentRow(1)
    assert window.waypoint_list.count() == 1
    assert window.waypoint_list.item(0).text() == "Koloseum"
    assert window.waypoint_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == second_waypoint.id

    window.collection_list.setCurrentRow(2)
    assert window.waypoint_list.count() == 0

    window.collection_list.setCurrentRow(-1)
    assert window.waypoint_list.count() == 0
    assert not window.export_button.isEnabled()

    window.close()
    application.processEvents()


def test_selecting_waypoint_loads_and_clears_editor(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    empty_collection = Collection(name="Prázdná")
    database.save_collection(collection)
    database.save_collection(empty_collection)
    first_waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )
    second_waypoint = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
        icon="natural_water",
        color="invalid-color",
        background="circle",
        note="Druhá poznámka",
        comment="Druhý komentář",
    )
    database.save_waypoint(first_waypoint, collection.id)
    database.save_waypoint(second_waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)

    window.waypoint_list.setCurrentRow(0)

    assert window.save_button.isEnabled()
    assert window.name_edit.text() == first_waypoint.name
    assert window.icon_edit.text() == first_waypoint.icon
    assert window.color_edit.text() == first_waypoint.color
    assert window.color_preview.autoFillBackground()
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == first_waypoint.color
    assert window.background_combo.currentText() == first_waypoint.background
    assert window.latitude_edit.text() == str(first_waypoint.latitude)
    assert window.longitude_edit.text() == str(first_waypoint.longitude)
    assert window.note_edit.text() == first_waypoint.note
    assert window.comment_edit.toPlainText() == first_waypoint.comment

    window.waypoint_list.setCurrentRow(1)
    assert window.name_edit.text() == second_waypoint.name
    assert window.color_edit.text() == second_waypoint.color
    assert not window.color_preview.autoFillBackground()
    assert window.latitude_edit.text() == str(second_waypoint.latitude)
    assert window.comment_edit.toPlainText() == second_waypoint.comment

    window.collection_list.setCurrentRow(1)
    assert window.waypoint_list.count() == 0
    assert window.name_edit.text() == ""
    assert window.icon_edit.text() == ""
    assert window.color_edit.text() == ""
    assert not window.color_preview.autoFillBackground()
    assert window.background_combo.currentText() == ""
    assert window.latitude_edit.text() == ""
    assert window.longitude_edit.text() == ""
    assert window.note_edit.text() == ""
    assert window.comment_edit.toPlainText() == ""
    assert not window.save_button.isEnabled()

    window.close()
    application.processEvents()


def test_multiple_waypoint_selection_enables_bulk_editor(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    other_collection = Collection(name="Prázdná")
    database.save_collection(collection)
    database.save_collection(other_collection)
    first = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    second = Waypoint(
        name="Gorges du Toulourenc",
        latitude=44.216738,
        longitude=5.224684,
    )
    database.save_waypoint(first, collection.id)
    database.save_waypoint(second, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)

    first_item = window.waypoint_list.item(0)
    second_item = window.waypoint_list.item(1)
    first_item.setSelected(True)
    second_item.setSelected(True)

    assert {
        item.data(Qt.ItemDataRole.UserRole)
        for item in window.waypoint_list.selectedItems()
    } == {first.id, second.id}
    assert window.editor_panel.isEnabled()
    assert window.save_button.isEnabled()
    assert not window.name_edit.isEnabled()
    assert window.icon_edit.isEnabled()
    assert window.color_edit.isEnabled()
    assert window.background_combo.isEnabled()
    assert not window.latitude_edit.isEnabled()
    assert not window.longitude_edit.isEnabled()
    assert not window.note_edit.isEnabled()
    assert not window.comment_edit.isEnabled()
    assert not window.waypoint_selection_label.isHidden()
    assert window.waypoint_selection_label.text() == "Selected waypoints: 2"

    second_item.setSelected(False)

    assert window.editor_panel.isEnabled()
    assert window.save_button.isEnabled()
    assert window.name_edit.text() == first.name
    assert window.waypoint_selection_label.isHidden()

    window.waypoint_list.clearSelection()

    assert window.editor_panel.isEnabled()
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()

    first_item.setSelected(True)
    second_item.setSelected(True)
    window.collection_list.setCurrentRow(1)

    assert window.waypoint_list.count() == 0
    assert window.editor_panel.isEnabled()
    assert window.name_edit.text() == ""
    assert not window.save_button.isEnabled()

    window.close()
    application.processEvents()


def test_bulk_edit_updates_only_explicit_fields(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    first = Waypoint(
        name="First",
        latitude=1.0,
        longitude=2.0,
        icon="first-icon",
        color="#FF0000",
        background="circle",
        note="First note",
        comment="First comment",
    )
    second = Waypoint(
        name="Second",
        latitude=3.0,
        longitude=4.0,
        icon="second-icon",
        color="#00FF00",
        background="square",
        note="Second note",
        comment="Second comment",
    )
    unselected = Waypoint(
        name="Unselected",
        latitude=5.0,
        longitude=6.0,
        icon="unchanged-icon",
        color="#0000FF",
        background="octagon",
        note="Unselected note",
        comment="Unselected comment",
    )
    for waypoint in (first, second, unselected):
        database.save_waypoint(waypoint, collection.id)

    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.item(0).setSelected(True)
    window.waypoint_list.item(1).setSelected(True)

    assert window.icon_edit.text() == ""
    assert window.color_edit.text() == ""
    assert window.background_combo.currentIndex() == -1
    assert window.bulk_changed_fields == set()

    window.icon_edit.setText("shared-icon")
    window.mark_bulk_field_changed("icon")
    window.save_button.click()

    loaded_first = database.get_waypoint(first.id)
    loaded_second = database.get_waypoint(second.id)
    assert loaded_first is not None
    assert loaded_second is not None
    assert loaded_first.icon == loaded_second.icon == "shared-icon"
    assert loaded_first.color == first.color
    assert loaded_second.color == second.color
    assert loaded_first.background == first.background
    assert loaded_second.background == second.background

    window.color_edit.setText("#123456")
    window.mark_bulk_field_changed("color")
    window.save_button.click()
    window.background_combo.setCurrentText("octagon")
    window.save_button.click()

    loaded_first = database.get_waypoint(first.id)
    loaded_second = database.get_waypoint(second.id)
    loaded_unselected = database.get_waypoint(unselected.id)
    assert loaded_first is not None
    assert loaded_second is not None
    assert loaded_unselected == unselected
    assert loaded_first.color == loaded_second.color == "#123456"
    assert loaded_first.background == loaded_second.background == "octagon"
    assert loaded_first.name == first.name
    assert loaded_second.name == second.name
    assert loaded_first.latitude == first.latitude
    assert loaded_second.longitude == second.longitude
    assert loaded_first.note == first.note
    assert loaded_second.note == second.note
    assert loaded_first.comment == first.comment
    assert loaded_second.comment == second.comment
    assert {
        item.data(Qt.ItemDataRole.UserRole)
        for item in window.waypoint_list.selectedItems()
    } == {first.id, second.id}
    assert messages == [
        "Updated 2 waypoints.",
        "Updated 2 waypoints.",
        "Updated 2 waypoints.",
    ]

    window.close()
    application.processEvents()


def test_save_button_updates_selected_waypoint(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Původní název",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.name_edit.setText("Pont du Gard")
    window.icon_edit.setText("historic_archaeological_site")
    window.color_edit.setText("#ff8000")
    window.background_combo.setCurrentText("square")
    window.note_edit.setText("Zastavit na focení")
    window.comment_edit.setPlainText(
        "Velmi pěkné místo pro delší zastávku."
    )
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded is not None
    assert loaded.id == waypoint.id
    assert loaded.name == "Pont du Gard"
    assert loaded.latitude == waypoint.latitude
    assert loaded.longitude == waypoint.longitude
    assert loaded.icon == "historic_archaeological_site"
    assert loaded.color == "#FF8000"
    assert loaded.background == "square"
    assert loaded.note == "Zastavit na focení"
    assert loaded.comment == "Velmi pěkné místo pro delší zastávku."
    assert window.waypoint_list.currentItem() is not None
    assert window.waypoint_list.currentItem().data(
        Qt.ItemDataRole.UserRole
    ) == waypoint.id
    assert window.waypoint_list.currentItem().text() == "Pont du Gard"
    assert window.name_edit.text() == "Pont du Gard"
    assert window.color_preview.autoFillBackground()
    assert messages == ['Waypoint "Pont du Gard" was saved.']

    window.close()
    application.processEvents()


def test_color_button_updates_color_and_handles_cancel(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)
    initial_colors = []

    def select_color(initial_color, *args, **kwargs):
        initial_colors.append(initial_color.name().upper())
        return QColor("#123456")

    window.color_edit.setText("#FF8000")
    monkeypatch.setattr(QColorDialog, "getColor", select_color)

    window.color_button.click()

    assert initial_colors == ["#FF8000"]
    assert window.color_edit.text() == "#123456"
    assert window.color_preview.autoFillBackground()
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == "#123456"

    monkeypatch.setattr(
        QColorDialog,
        "getColor",
        lambda *args, **kwargs: QColor(),
    )
    window.color_button.click()

    assert window.color_edit.text() == "#123456"
    assert window.color_preview.palette().color(
        QPalette.ColorRole.Window
    ).name().upper() == "#123456"

    window.close()
    application.processEvents()


def test_icon_button_updates_icon_and_handles_cancel(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.load_icon_catalog",
        lambda: [],
    )
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    window = MainWindow(database)

    class AcceptedIconDialog:
        selected_icon_name = "amenity_fuel"

        def __init__(self, catalog, parent):
            assert catalog == []
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.IconPickerDialog",
        AcceptedIconDialog,
    )

    window.icon_edit.setText("unknown_existing_icon")
    window.icon_button.click()
    assert window.icon_edit.text() == "amenity_fuel"

    class RejectedIconDialog(AcceptedIconDialog):
        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.IconPickerDialog",
        RejectedIconDialog,
    )

    window.icon_edit.setText("unknown_existing_icon")
    window.icon_button.click()
    assert window.icon_edit.text() == "unknown_existing_icon"

    window.close()
    application.processEvents()


def test_icon_preview_uses_cached_catalog_and_updates_live(
    tmp_path,
    monkeypatch,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    first_svg = tmp_path / "first.svg"
    duplicate_svg = tmp_path / "duplicate.svg"
    other_svg = tmp_path / "other.svg"
    first_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="32" height="16"><rect width="32" height="16" '
        'fill="#ff0000"/></svg>',
        encoding="utf-8",
    )
    duplicate_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="16" height="32"><rect width="16" height="32" '
        'fill="#0000ff"/></svg>',
        encoding="utf-8",
    )
    other_svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="24" height="24"><circle cx="12" cy="12" r="12" '
        'fill="#00ff00"/></svg>',
        encoding="utf-8",
    )
    catalog = [
        IconInfo("Alpha", "shared", first_svg),
        IconInfo("Beta", "shared", duplicate_svg),
        IconInfo("Beta", "other", other_svg),
    ]
    window = MainWindow(database, icon_catalog=catalog)

    assert window.icon_paths_by_name["shared"] == first_svg

    window.icon_edit.setText("shared")
    assert not window.icon_preview.pixmap().isNull()

    window.icon_edit.setText("unknown_icon")
    assert window.icon_edit.text() == "unknown_icon"
    assert window.icon_preview.pixmap().isNull()

    window.icon_edit.setText("other")
    assert not window.icon_preview.pixmap().isNull()

    class AcceptedIconDialog:
        selected_icon_name = "shared"

        def __init__(self, received_catalog, parent):
            assert received_catalog is catalog
            assert parent is window

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "wpt_manager.gui.main_window.IconPickerDialog",
        AcceptedIconDialog,
    )
    window.icon_button.click()

    assert window.icon_edit.text() == "shared"
    assert not window.icon_preview.pixmap().isNull()

    window.clear_waypoint_editor()
    assert window.icon_preview.pixmap().isNull()

    window.close()
    application.processEvents()


@pytest.mark.parametrize(
    ("name", "color", "expected_error"),
    [
        ("", "#FF0000", "Waypoint name cannot be empty."),
        (
            "Pont du Gard",
            "invalid-color",
            "Waypoint color must be a valid Qt color or HEX value.",
        ),
    ],
)
def test_save_button_rejects_invalid_values(
    tmp_path,
    monkeypatch,
    name,
    color,
    expected_error,
):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Původní název",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.name_edit.setText(name)
    window.color_edit.setText(color)
    window.save_button.click()

    loaded = database.get_waypoint(waypoint.id)
    assert loaded == waypoint
    assert messages == [expected_error]

    window.close()
    application.processEvents()


def test_save_button_handles_database_error(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(waypoint, collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    window.waypoint_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        database,
        "update_waypoint",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("Database is locked")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.save_button.click()

    assert messages == [
        "The waypoint could not be saved:\nDatabase is locked"
    ]

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


def test_export_button_exports_selected_collection(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    other_collection = Collection(name="Itálie")
    database.save_collection(collection)
    database.save_collection(other_collection)
    waypoint = Waypoint(
        name="Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
        icon="historic_archaeological_site",
        color="#FF8000",
        background="square",
        note="Zastavit na focení",
        comment="Velmi pěkné místo pro delší zastávku.",
    )
    other_waypoint = Waypoint(
        name="Koloseum",
        latitude=41.890210,
        longitude=12.492231,
    )
    database.save_waypoint(waypoint, collection.id)
    database.save_waypoint(other_waypoint, other_collection.id)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    output_without_suffix = tmp_path / "export"
    dialog_arguments = []
    messages = []

    def select_output_file(*args, **kwargs):
        dialog_arguments.append(args)
        return str(output_without_suffix), "GPX files (*.gpx)"

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        select_output_file,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.export_button.click()

    output_file = tmp_path / "export.gpx"
    assert output_file.exists()
    assert dialog_arguments[0][2] == "Francie.gpx"
    assert dialog_arguments[0][3] == "GPX files (*.gpx)"
    exported_waypoints = load_gpx(output_file)
    assert len(exported_waypoints) == 1
    exported = exported_waypoints[0]
    assert exported.name == waypoint.name
    assert exported.latitude == waypoint.latitude
    assert exported.longitude == waypoint.longitude
    assert exported.note == waypoint.note
    assert exported.comment == waypoint.comment
    assert exported.icon == waypoint.icon
    assert exported.background == waypoint.background
    assert exported.color == waypoint.color
    assert messages == ['Collection "Francie" was exported.']

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: ("", ""),
    )
    window.export_button.click()
    assert messages == ['Collection "Francie" was exported.']

    window.close()
    application.processEvents()


def test_export_button_handles_error(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    collection = Collection(name="Francie")
    database.save_collection(collection)
    window = MainWindow(database)
    window.collection_list.setCurrentRow(0)
    messages = []
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (
            str(tmp_path / "francie.gpx"),
            "GPX files (*.gpx)",
        ),
    )
    monkeypatch.setattr(
        "wpt_manager.gui.main_window.export_collection_gpx",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("Access denied")
        ),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    window.export_button.click()

    assert messages == [
        "The collection could not be exported:\nAccess denied"
    ]

    window.close()
    application.processEvents()
