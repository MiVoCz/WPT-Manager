import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.gui.new_waypoint_dialog import NewWaypointDialog


def test_new_waypoint_dialog_rejects_empty_name(monkeypatch):
    application = QApplication.instance() or QApplication([])
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: messages.append(args[2]),
    )
    dialog = NewWaypointDialog(50.123, 14.456, [])

    assert dialog.editor.latitude_edit.isReadOnly()
    assert dialog.editor.longitude_edit.isReadOnly()
    assert dialog.editor.icon_edit.text() == "marker"
    assert dialog.editor.color_edit.text() == "#FF0000"
    assert dialog.editor.background_combo.currentText() == "circle"

    dialog.editor.save_button.click()

    assert dialog.waypoint is None
    assert messages == ["Waypoint name cannot be empty."]

    dialog.close()
    application.processEvents()
