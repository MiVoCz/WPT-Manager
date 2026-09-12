import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from wpt_manager.database.database import Database
from wpt_manager.gui import main_window as gui
from wpt_manager.gui.adventure_selection_dialog import AdventureSelectionDialog
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track


@pytest.fixture
def window(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = Database(tmp_path / "data.db")
    db.initialize()
    widget = gui.MainWindow(db, icon_catalog=[])
    yield widget
    widget.close()
    app.processEvents()


@pytest.mark.parametrize("for_import", [False, True])
def test_duplicate_names_use_uuid_in_dialog_and_workflow(window, tmp_path, monkeypatch, for_import):
    db = window.database
    adventures = [Adventure("Italy"), Adventure("Italy")]
    for adventure in adventures:
        db.save_adventure(adventure)
    ordered = db.list_adventures()
    target = ordered[1].uuid
    def select_second(dialog):
        combo = dialog.adventure_combo
        assert combo.count() == (4 if for_import else 2)
        first, second = [combo.findData(str(adventure.uuid)) for adventure in ordered]
        assert first >= 0 and second > first
        assert combo.itemText(first) != combo.itemText(second)
        assert all("Italy" in combo.itemText(row) for row in (first, second))
        combo.setCurrentIndex(second)
        assert dialog.selected_destination == target
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(AdventureSelectionDialog, "exec", select_second)
    if for_import:
        path = tmp_path / "track.gpx"
        path.write_text('<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
                        '<trkpt lat="0" lon="0"/></trkseg></trk></gpx>', encoding="utf-8")
        monkeypatch.setattr(gui.QFileDialog, "getOpenFileNames", lambda *args: ([str(path)], ""))
        window.import_track_gpx_file()
        track = db.list_tracks()[0]
    else:
        track = Track("Track", "file.gpx")
        db.save_track(track)
        window.load_tracks()
        window._select_track(track.id)
        window.add_selected_tracks_to_adventure_dialog()
    assert [track.id for track in db.list_adventure_tracks(target)] == [track.id]
    assert db.list_adventure_tracks(ordered[0].uuid) == []


def test_metadata_read_only_in_both_track_tables(window):
    db = window.database
    track = Track("Track", "file.gpx")
    adventure = Adventure("Trip")
    db.save_track(track)
    db.save_adventure(adventure)
    db.add_track_to_adventure(adventure.uuid, track.id)
    window.load_tracks()
    window.load_adventures()
    window.adventure_list.setCurrentRow(0)
    for model in (window.track_model, window.adventure_editor.track_model):
        for column in range(1, 5):
            flags = model.item(0, column).flags()
            assert flags & Qt.ItemFlag.ItemIsEnabled
            assert flags & Qt.ItemFlag.ItemIsSelectable
            assert not flags & Qt.ItemFlag.ItemIsEditable
        item = model.item(0, 0)
        assert item.flags() & Qt.ItemFlag.ItemIsUserCheckable
        assert item.flags() & Qt.ItemFlag.ItemIsEnabled
        assert not item.flags() & Qt.ItemFlag.ItemIsEditable
        item.setCheckState(Qt.CheckState.Checked)
        assert window.get_track_visibility(track.id)
        item.setCheckState(Qt.CheckState.Unchecked)
        assert not window.get_track_visibility(track.id)
