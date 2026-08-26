import sys
import logging

from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.paths import DATABASE_PATH


def main() -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    database = Database(DATABASE_PATH)
    database.initialize()

    application = QApplication(sys.argv)
    window = MainWindow(database)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
