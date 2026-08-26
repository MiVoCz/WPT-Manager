import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wpt_manager.gui.collection_edit_dialog import CollectionEditDialog
from wpt_manager.models.collection import Collection


def test_collection_edit_dialog_requires_nonempty_name():
    application = QApplication.instance() or QApplication([])
    dialog = CollectionEditDialog(
        Collection(name="Existing", description="Description")
    )

    assert dialog.collection_name == "Existing"
    assert dialog.collection_description == "Description"
    assert dialog.save_button.isEnabled()

    dialog.name_edit.setText("   ")
    assert not dialog.save_button.isEnabled()

    dialog.name_edit.setText(" Renamed ")
    assert dialog.save_button.isEnabled()
    assert dialog.collection_name == "Renamed"

    dialog.close()
    application.processEvents()
