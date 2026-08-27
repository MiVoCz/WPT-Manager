import sys

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from diagnostics.popup_probe import PopupProbe, print_screens


def main() -> int:
    application = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("QComboBox popup diagnostic — QWebEngineView")
    window.resize(700, 500)
    panel = QWidget()
    layout = QVBoxLayout(panel)
    combo = QComboBox()
    combo.addItems(["All", "Places", "POI", "Addresses"])
    web_view = QWebEngineView()
    web_view.setHtml("<html><body>QWebEngineView diagnostic</body></html>", QUrl())
    layout.addWidget(combo)
    layout.addWidget(web_view)
    window.setCentralWidget(panel)
    probe = PopupProbe(combo)
    window._popup_probe = probe
    print_screens()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
