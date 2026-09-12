import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track


def _setup(tmp_path):
    database = Database(tmp_path / "photos-gui.db")
    database.initialize()
    member = Track("Italy Day", "italy.gpx")
    ungrouped = Track("Local Walk", "walk.gpx")
    database.save_track(member)
    database.save_track(ungrouped)
    adventure = Adventure("Italy")
    database.save_adventure(adventure)
    database.add_track_to_adventure(adventure.uuid, member.id)
    photos = [
        Photo("Lake Sunrise", "imagekit", track_uuid=member.id),
        Photo("Forest", "local", track_uuid=ungrouped.id),
        Photo("Standalone Lake", "local"),
    ]
    for photo in photos:
        database.save_photo(photo)
    return database, member, ungrouped, adventure, photos


def test_photos_tab_selection_editor_and_save(tmp_path):
    application = QApplication.instance() or QApplication([])
    database, member, ungrouped, adventure, photos = _setup(tmp_path)
    window = MainWindow(database, icon_catalog=[])
    assert window.data_tabs.tabText(3) == "Photos"
    window.data_tabs.setCurrentIndex(3)
    assert window.right_panel_stack.currentWidget() is window.photo_editor
    window._select_photo(photos[0].id)
    assert window.photo_editor.name_edit.text() == "Lake Sunrise"
    window.photo_editor.name_edit.setText("Renamed")
    window.photo_editor.description_edit.setPlainText("Description")
    window.photo_editor.track_combo.setCurrentIndex(
        window.photo_editor.track_combo.findData(str(ungrouped.id))
    )
    window.save_photo()
    saved = database.get_photo(photos[0].id)
    assert (saved.name, saved.description, saved.track_uuid) == (
        "Renamed", "Description", ungrouped.id
    )
    source_row = next(
        row for row in range(window.photo_model.rowCount())
        if window.photo_model.item(row, 0).data(Qt.ItemDataRole.UserRole) == saved.id
    )
    assert window.photo_model.item(source_row, 2).text() == "Local Walk"
    assert window.photo_model.item(source_row, 3).text() == "-"
    window.photo_editor.track_combo.setCurrentIndex(0)
    window.save_photo()
    assert database.get_photo(saved.id).track_uuid is None
    window.photo_table.clearSelection()
    window.photo_table.setCurrentIndex(window.photo_proxy.index(-1, -1))
    window.update_photo_selection(window.photo_proxy.index(-1, -1))
    assert not window.photo_editor.save_button.isEnabled()
    window.close()
    application.processEvents()


def test_photo_filters_are_combined_and_adventure_standalone_is_derived(tmp_path):
    application = QApplication.instance() or QApplication([])
    database, member, ungrouped, adventure, photos = _setup(tmp_path)
    window = MainWindow(database, icon_catalog=[])
    assert window.photo_proxy.rowCount() == 3
    window.photo_search_edit.setText("LAKE")
    assert window.photo_proxy.rowCount() == 2
    window.photo_track_filter.setCurrentIndex(
        window.photo_track_filter.findData(str(member.id))
    )
    assert window.photo_proxy.rowCount() == 1
    window.photo_adventure_filter.setCurrentIndex(
        window.photo_adventure_filter.findData(str(adventure.uuid))
    )
    assert window.photo_proxy.rowCount() == 1
    window.photo_track_filter.setCurrentIndex(0)
    window.photo_search_edit.clear()
    window.photo_adventure_filter.setCurrentIndex(
        window.photo_adventure_filter.findData("standalone")
    )
    assert {
        window.photo_proxy.index(row, 0).data()
        for row in range(window.photo_proxy.rowCount())
    } == {"Forest", "Standalone Lake"}
    window.photo_track_filter.setCurrentIndex(
        window.photo_track_filter.findData("standalone")
    )
    assert window.photo_proxy.rowCount() == 1
    assert window.photo_proxy.index(0, 0).data() == "Standalone Lake"
    window.close()
    application.processEvents()
