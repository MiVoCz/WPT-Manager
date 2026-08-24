import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from wpt_manager.gui.main_window import MainWindow


def test_main_window_defaults():
    application = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.windowTitle() == "WPT-Manager"
    assert window.size().width() == 1000
    assert window.size().height() == 700

    window.close()
    application.processEvents()
