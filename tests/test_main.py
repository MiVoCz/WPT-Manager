from wpt_manager.main import main


def test_main_initializes_database_and_starts_qt_application(
    tmp_path,
    monkeypatch,
):
    events = []

    class FakeDatabase:
        def __init__(self, path):
            events.append(("database", path))

        def initialize(self):
            events.append(("initialize",))

    class FakeApplication:
        def __init__(self, arguments):
            events.append(("application", arguments))

        def exec(self):
            events.append(("exec",))
            return 0

    class FakeMainWindow:
        def __init__(self, database):
            events.append(("window", database))

        def show(self):
            events.append(("show",))

    database_path = tmp_path / "data" / "wpt_manager.db"
    monkeypatch.setattr("wpt_manager.main.DATABASE_PATH", database_path)
    monkeypatch.setattr("wpt_manager.main.Database", FakeDatabase)
    monkeypatch.setattr("wpt_manager.main.QApplication", FakeApplication)
    monkeypatch.setattr("wpt_manager.main.MainWindow", FakeMainWindow)

    exit_code = main()

    assert exit_code == 0
    assert database_path.parent.exists()
    assert [event[0] for event in events] == [
        "database",
        "initialize",
        "application",
        "window",
        "show",
        "exec",
    ]
