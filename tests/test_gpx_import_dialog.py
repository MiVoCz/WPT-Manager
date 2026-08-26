import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.gpx_import_dialog import GpxImportDialog
from wpt_manager.io.exceptions import GpxReaderError
from wpt_manager.models.collection import Collection
from wpt_manager.models.collection_merge import ConflictDecision
from wpt_manager.models.waypoint import Waypoint


TEST_DATA = Path(__file__).parent / "data" / "mapy_export.gpx"


def test_create_new_collection_mode_imports_collection(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    dialog = GpxImportDialog(database, TEST_DATA)
    messages = []
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    assert dialog.create_radio.isChecked()
    assert dialog.name_edit.text() == "mapy_export"
    dialog.name_edit.setText("France import")
    dialog.description_edit.setText("Imported places")
    dialog.import_button.click()

    collections = database.list_collections()
    assert len(collections) == 1
    assert dialog.created_collection_id == collections[0].id
    assert collections[0].name == "France import"
    assert collections[0].description == "Imported places"
    assert collections[0].source == "mapy.com"
    assert collections[0].source_file == "mapy_export.gpx"
    assert len(database.list_waypoints(collections[0].id)) == 3
    assert messages == ['Collection "France import" was imported.']

    dialog.close()
    application.processEvents()


def test_merge_mode_analyzes_and_imports_into_target(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    target = Collection(name="France 2026")
    database.save_collection(target)
    existing = Waypoint(
        name="Old Pont du Gard",
        latitude=43.947070,
        longitude=4.535600,
    )
    database.save_waypoint(existing, target.id)
    dialog = GpxImportDialog(database, TEST_DATA, target.id)
    messages = []
    monkeypatch.setattr(dialog, "_confirm_import", lambda: True)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    dialog.merge_radio.setChecked(True)
    assert dialog.target_combo.currentData() == str(target.id)
    assert not dialog.import_button.isEnabled()
    dialog.analyze_button.click()

    assert "New waypoints: 2" in dialog.summary_label.text()
    assert "Potential duplicates: 1" in dialog.summary_label.text()
    assert database.list_collections() == [target]
    assert database.list_waypoints(target.id) == [existing]
    conflict_id = dialog.plan.conflicts[0].source.id
    dialog.conflicts.decision_groups[conflict_id].button(
        ConflictDecision.USE_SOURCE.value
    ).setChecked(True)
    confirmation = dialog.confirmation_text()
    assert "Target Collection: France 2026" in confirmation
    assert "New waypoints: 2" in confirmation
    assert "Target waypoints replaced: 1" in confirmation
    assert "Import file:\nmapy_export.gpx" in confirmation

    dialog.import_button.click()

    assert database.list_collections() == [target]
    assert dialog.merged_target_id == target.id
    assert dialog.merge_result is not None
    assert dialog.merge_result.added_count == 2
    assert dialog.merge_result.replaced_count == 1
    assert len(database.list_waypoints(target.id)) == 3
    assert database.get_waypoint(existing.id).name == "Pont du Gard"
    assert "Import completed." in messages[0]

    dialog.close()
    application.processEvents()


def test_invalid_gpx_cannot_modify_existing_collection(tmp_path):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    target = Collection(name="Existing")
    database.save_collection(target)
    existing = Waypoint(name="Existing point", latitude=50.0, longitude=14.0)
    database.save_waypoint(existing, target.id)
    gpx_file = tmp_path / "invalid_merge.gpx"
    gpx_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        '<wpt lat="nan" lon="14"><name>Invalid import</name></wpt>'
        "</gpx>",
        encoding="utf-8",
    )

    with pytest.raises(GpxReaderError, match="Invalid import"):
        GpxImportDialog(database, gpx_file, target.id)

    assert database.list_collections() == [target]
    assert database.list_waypoints(target.id) == [existing]
    application.processEvents()
