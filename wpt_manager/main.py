import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow


DATABASE_PATH = Path("data") / "wpt_manager.db"


def main() -> int:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    database = Database(DATABASE_PATH)
    database.initialize()

    application = QApplication(sys.argv)
    window = MainWindow(database)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
