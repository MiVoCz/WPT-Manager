import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wpt_manager.gui.collection_create_dialog import CollectionCreateDialog


def test_collection_create_dialog_requires_trimmed_nonempty_name():
    application = QApplication.instance() or QApplication([])
    dialog = CollectionCreateDialog()

    assert dialog.windowTitle() == "New Collection"
    assert not dialog.create_button.isEnabled()

    dialog.name_edit.setText("   ")
    assert dialog.collection_name == ""
    assert not dialog.create_button.isEnabled()

    dialog.name_edit.setText("  Alps 2026  ")
    assert dialog.collection_name == "Alps 2026"
    assert dialog.create_button.isEnabled()

    dialog.close()
    application.processEvents()
