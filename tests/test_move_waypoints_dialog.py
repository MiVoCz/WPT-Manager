import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wpt_manager.gui.move_waypoints_dialog import MoveWaypointsDialog
from wpt_manager.models.collection import Collection


def test_move_waypoints_dialog_uses_collection_uuids_in_given_order():
    application = QApplication.instance() or QApplication([])
    alpha = Collection(name="Alpha")
    zulu = Collection(name="Zulu")
    dialog = MoveWaypointsDialog(3, [alpha, zulu])

    assert dialog.windowTitle() == "Move Waypoints"
    assert dialog.collection_combo.count() == 2
    assert dialog.collection_combo.itemText(0) == "Alpha"
    assert dialog.collection_combo.itemData(0) == alpha.id
    assert dialog.target_collection_id == alpha.id

    dialog.collection_combo.setCurrentIndex(1)
    assert dialog.target_collection_id == zulu.id
    dialog.close()
    application.processEvents()
