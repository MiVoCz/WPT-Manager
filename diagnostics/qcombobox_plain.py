import sys

from PySide6.QtWidgets import QApplication, QComboBox, QMainWindow

from diagnostics.popup_probe import PopupProbe, print_screens


def main() -> int:
    application = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("QComboBox popup diagnostic — plain Qt")
    window.resize(500, 250)
    combo = QComboBox()
    combo.addItems(["All", "Places", "POI", "Addresses"])
    window.setCentralWidget(combo)
    probe = PopupProbe(combo)
    window._popup_probe = probe
    print_screens()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
