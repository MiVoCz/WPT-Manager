from wpt_manager.main import main


def test_main(capsys):
    main()

    captured = capsys.readouterr()

    assert captured.out == "WPT-Manager\n"