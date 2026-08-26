import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wpt_manager.gui.waypoint_editor import WaypointEditor
from wpt_manager.models.waypoint import Waypoint


def test_editor_shows_waypoint_and_emits_save_request():
    application = QApplication.instance() or QApplication([])
    editor = WaypointEditor([])
    waypoint = Waypoint(
        name="Point",
        latitude=50.0,
        longitude=14.0,
        icon="custom-icon",
        color="#123456",
        background="custom-background",
        note="Note",
        comment="Comment",
    )
    save_requests = []
    editor.save_requested.connect(lambda: save_requests.append(True))

    editor.show_waypoint(waypoint)
    editor.save_button.click()

    assert editor.values().background == "custom-background"
    assert editor.latitude_edit.isReadOnly()
    assert editor.longitude_edit.isReadOnly()
    assert save_requests == [True]

    editor.close()
    application.processEvents()


def test_editor_represents_bulk_mixed_state_and_tracks_changes():
    application = QApplication.instance() or QApplication([])
    editor = WaypointEditor([])
    first = Waypoint(
        name="First",
        latitude=50.0,
        longitude=14.0,
        icon="first",
        color="#FF0000",
        background="circle",
    )
    second = Waypoint(
        name="Second",
        latitude=51.0,
        longitude=15.0,
        icon="second",
        color="#00FF00",
        background="square",
    )

    editor.show_bulk([first, second])
    editor.icon_edit.setText("shared")
    editor.mark_bulk_field_changed("icon")

    assert editor.selection_label.text() == "Selected waypoints: 2"
    assert editor.color_edit.placeholderText() == "(mixed)"
    assert editor.background_combo.currentIndex() == -1
    assert not editor.name_edit.isEnabled()
    assert editor.bulk_changed_fields == {"icon"}

    editor.clear()
    assert not editor.save_button.isEnabled()
    assert editor.bulk_changed_fields == set()

    editor.close()
    application.processEvents()
