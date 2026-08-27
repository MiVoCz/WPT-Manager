import os
from uuid import uuid4

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
    collection_id = uuid4()
    dialog = NewWaypointDialog(
        50.123,
        14.456,
        [],
        [(collection_id, "Places")],
    )

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


def test_new_waypoint_dialog_defaults_to_current_collection():
    application = QApplication.instance() or QApplication([])
    first_id = uuid4()
    current_id = uuid4()
    dialog = NewWaypointDialog(
        50.123,
        14.456,
        [],
        [(first_id, "First"), (current_id, "Current")],
        current_id,
    )

    assert dialog.collection_combo.currentData() == current_id
    assert [
        dialog.collection_combo.itemData(index)
        for index in range(dialog.collection_combo.count())
    ] == [first_id, current_id]

    dialog.close()
    application.processEvents()


def test_new_waypoint_dialog_defaults_to_first_collection_without_current():
    application = QApplication.instance() or QApplication([])
    first_id = uuid4()
    second_id = uuid4()
    dialog = NewWaypointDialog(
        50.123,
        14.456,
        [],
        [(first_id, "First"), (second_id, "Second")],
    )

    assert dialog.collection_combo.currentData() == first_id

    dialog.close()
    application.processEvents()


def test_new_waypoint_dialog_can_select_another_collection():
    application = QApplication.instance() or QApplication([])
    first_id = uuid4()
    second_id = uuid4()
    dialog = NewWaypointDialog(
        50.123,
        14.456,
        [],
        [(first_id, "Same name"), (second_id, "Same name")],
        first_id,
    )

    dialog.collection_combo.setCurrentIndex(1)
    dialog.editor.name_edit.setText("New place")
    dialog.editor.save_button.click()

    assert dialog.collection_id == second_id
    assert dialog.waypoint is not None

    dialog.close()
    application.processEvents()


def test_new_waypoint_dialog_prefills_search_result_fields():
    application = QApplication.instance() or QApplication([])
    collection_id = uuid4()
    dialog = NewWaypointDialog(
        50.0835,
        14.3952,
        [],
        [(collection_id, "Places")],
        collection_id,
        name="Petřínská rozhledna",
        note="Rozhledna",
        comment="Praha, Česko",
    )

    assert dialog.editor.name_edit.text() == "Petřínská rozhledna"
    assert float(dialog.editor.latitude_edit.text()) == 50.0835
    assert float(dialog.editor.longitude_edit.text()) == 14.3952
    assert dialog.editor.latitude_edit.isReadOnly()
    assert dialog.editor.longitude_edit.isReadOnly()
    assert dialog.editor.note_edit.text() == "Rozhledna"
    assert dialog.editor.comment_edit.toPlainText() == "Praha, Česko"
    assert dialog.collection_combo.currentData() == collection_id

    dialog.close()
    application.processEvents()
