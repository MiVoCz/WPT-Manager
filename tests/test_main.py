from wpt_manager.main import main


def test_main_starts_qt_application(monkeypatch):
    events = []

    class FakeApplication:
        def __init__(self, arguments):
            events.append(("application", arguments))

        def exec(self):
            events.append(("exec",))
            return 0

    class FakeMainWindow:
        def __init__(self):
            events.append(("window",))

        def show(self):
            events.append(("show",))

    monkeypatch.setattr("wpt_manager.main.QApplication", FakeApplication)
    monkeypatch.setattr("wpt_manager.main.MainWindow", FakeMainWindow)

    exit_code = main()

    assert exit_code == 0
    assert [event[0] for event in events] == [
        "application",
        "window",
        "show",
        "exec",
    ]
