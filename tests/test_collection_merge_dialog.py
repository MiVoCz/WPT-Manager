import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from wpt_manager.database.database import Database
from wpt_manager.gui.collection_merge_dialog import CollectionMergeDialog
from wpt_manager.models.collection import Collection
from wpt_manager.models.collection_merge import ConflictDecision
from wpt_manager.models.waypoint import Waypoint


def create_merge_dialog(tmp_path, selected_target=None):
    application = QApplication.instance() or QApplication([])
    database = Database(tmp_path / "wpt_manager.db")
    database.initialize()
    source = Collection(name="France import")
    target = Collection(name="France 2026")
    database.save_collection(source)
    database.save_collection(target)
    dialog = CollectionMergeDialog(database, selected_target)
    return application, database, source, target, dialog


def select_collections(dialog, source, target):
    dialog.source_combo.setCurrentIndex(
        dialog.source_combo.findData(str(source.id))
    )
    dialog.target_combo.setCurrentIndex(
        dialog.target_combo.findData(str(target.id))
    )


def test_source_and_target_must_be_different(tmp_path):
    application, _, source, target, dialog = create_merge_dialog(tmp_path)

    assert not dialog.analyze_button.isEnabled()
    dialog.source_combo.setCurrentIndex(
        dialog.source_combo.findData(str(source.id))
    )
    dialog.target_combo.setCurrentIndex(
        dialog.target_combo.findData(str(source.id))
    )
    assert not dialog.analyze_button.isEnabled()

    dialog.target_combo.setCurrentIndex(
        dialog.target_combo.findData(str(target.id))
    )
    assert dialog.analyze_button.isEnabled()

    dialog.close()
    application.processEvents()


def test_current_collection_is_preselected_as_target(tmp_path):
    application, _, _, target, dialog = create_merge_dialog(
        tmp_path,
        selected_target=None,
    )
    dialog.close()
    dialog = CollectionMergeDialog(dialog.database, target.id)

    assert dialog.target_combo.currentData() == str(target.id)
    assert dialog.target_combo.currentText() == target.name

    dialog.close()
    application.processEvents()


def test_analyze_is_read_only_and_shows_counts(tmp_path):
    application, database, source, target, dialog = create_merge_dialog(
        tmp_path
    )
    new_waypoint = Waypoint(name="New", latitude=51.0, longitude=14.0)
    duplicate = Waypoint(
        name="Duplicate source",
        latitude=50.0,
        longitude=14.0,
    )
    target_waypoint = Waypoint(
        name="Duplicate target",
        latitude=50.0,
        longitude=14.0,
    )
    database.save_waypoint(new_waypoint, source.id)
    database.save_waypoint(duplicate, source.id)
    database.save_waypoint(target_waypoint, target.id)
    source_before = database.list_waypoints(source.id)
    target_before = database.list_waypoints(target.id)
    select_collections(dialog, source, target)

    assert not dialog.merge_button.isEnabled()
    dialog.analyze_button.click()

    assert database.list_waypoints(source.id) == source_before
    assert database.list_waypoints(target.id) == target_before
    assert "Source: France import" in dialog.summary_label.text()
    assert "Target: France 2026" in dialog.summary_label.text()
    assert "New waypoints: 1" in dialog.summary_label.text()
    assert "Potential duplicates: 1" in dialog.summary_label.text()
    assert dialog.merge_button.isEnabled()
    group = dialog.conflict_decision_groups[duplicate.id]
    assert group.checkedId() == ConflictDecision.KEEP_TARGET.value

    dialog.close()
    application.processEvents()


def test_changing_analysis_input_invalidates_plan(tmp_path):
    application, _, source, target, dialog = create_merge_dialog(tmp_path)
    select_collections(dialog, source, target)
    dialog.analyze_button.click()
    assert dialog.merge_button.isEnabled()

    dialog.distance_spin.setValue(75.0)

    assert dialog.plan is None
    assert not dialog.merge_button.isEnabled()

    dialog.close()
    application.processEvents()


def test_confirmation_summarizes_current_conflict_decisions(tmp_path):
    application, database, source, target, dialog = create_merge_dialog(
        tmp_path
    )
    new_waypoint = Waypoint(name="New", latitude=53.0, longitude=14.0)
    database.save_waypoint(new_waypoint, source.id)
    conflicting_sources = []
    for index, latitude in enumerate((50.0, 51.0, 52.0)):
        source_waypoint = Waypoint(
            name=f"Source {index}",
            latitude=latitude,
            longitude=14.0,
        )
        target_waypoint = Waypoint(
            name=f"Target {index}",
            latitude=latitude,
            longitude=14.0,
        )
        conflicting_sources.append(source_waypoint)
        database.save_waypoint(source_waypoint, source.id)
        database.save_waypoint(target_waypoint, target.id)
    select_collections(dialog, source, target)
    dialog.analyze_button.click()

    decisions = (
        ConflictDecision.KEEP_BOTH,
        ConflictDecision.USE_SOURCE,
        ConflictDecision.KEEP_TARGET,
    )
    for source_waypoint, decision in zip(
        conflicting_sources,
        decisions,
        strict=True,
    ):
        dialog.conflict_decision_groups[source_waypoint.id].button(
            decision.value
        ).setChecked(True)

    confirmation = dialog.confirmation_text()

    assert 'Source Collection:\n"France import"' in confirmation
    assert '↓ Merge into ↓\nTarget Collection:\n"France 2026"' in confirmation
    assert "New waypoints: 1" in confirmation
    assert "Both nearby waypoints kept: 1" in confirmation
    assert "Target waypoints replaced: 1" in confirmation
    assert "Target waypoints kept unchanged: 1" in confirmation
    assert "Potential duplicates" not in confirmation
    assert "Source collection will not be deleted." in confirmation

    dialog.close()
    application.processEvents()


def test_set_all_and_successful_merge(tmp_path, monkeypatch):
    application, database, source, target, dialog = create_merge_dialog(
        tmp_path
    )
    source_waypoint = Waypoint(
        name="Use me",
        latitude=50.0,
        longitude=14.0,
    )
    target_waypoint = Waypoint(
        name="Old target",
        latitude=50.0,
        longitude=14.0,
    )
    database.save_waypoint(source_waypoint, source.id)
    database.save_waypoint(target_waypoint, target.id)
    select_collections(dialog, source, target)
    dialog.analyze_button.click()
    messages = []
    monkeypatch.setattr(dialog, "_confirm_merge", lambda: True)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: messages.append(args[2]),
    )

    dialog.set_all(ConflictDecision.USE_SOURCE)
    dialog.merge_button.click()

    assert dialog.merged_target_id == target.id
    assert database.get_waypoint(target_waypoint.id).name == "Use me"
    assert "Replaced: 1" in messages[0]
    assert "Source Collection was not modified." in messages[0]
    assert database.get_waypoint(source_waypoint.id) == source_waypoint

    dialog.close()
    application.processEvents()
