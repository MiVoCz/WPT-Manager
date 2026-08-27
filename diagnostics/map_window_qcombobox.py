import sys
from tempfile import TemporaryDirectory

from PySide6.QtWidgets import QApplication

from diagnostics.popup_probe import PopupProbe, print_screens
from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    with TemporaryDirectory(prefix="wpt-manager-popup-") as directory:
        database = Database(f"{directory}/wpt_manager.db")
        database.initialize()
        main_window = MainWindow(database, icon_catalog=[])
        main_window.show()
        main_window.open_map()
        map_window = main_window.map_window
        if map_window is None:
            raise RuntimeError("MapWindow was not created.")
        probe = PopupProbe(map_window.search_type_combo)
        map_window._popup_probe = probe
        print_screens()
        return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
