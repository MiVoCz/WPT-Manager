from pathlib import Path
from uuid import UUID

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.collection_merge import (
    MergePlanChangedError,
    merge_waypoints_into_collection,
    prepare_waypoint_merge,
)
from wpt_manager.database.database import Database
from wpt_manager.gui.merge_conflicts_widget import MergeConflictsWidget
from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.io.gpx_importer import import_waypoints
from wpt_manager.io.gpx_reader import load_gpx
from wpt_manager.models.collection_merge import (
    ConflictDecision,
    MergeResult,
    WaypointMergePlan,
)


class GpxImportDialog(QDialog):
    def __init__(
        self,
        database: Database,
        path: str | Path,
        selected_target_id: UUID | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.database = database
        self.path = Path(path)
        self.source_waypoints = load_gpx(self.path)
        self.plan: WaypointMergePlan | None = None
        self.created_collection_id: UUID | None = None
        self.merged_target_id: UUID | None = None
        self.merge_result: MergeResult | None = None

        self.setWindowTitle("Import GPX")
        self.resize(850, 700)

        self.create_radio = QRadioButton("Create new Collection")
        self.merge_radio = QRadioButton("Merge into existing Collection")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.create_radio)
        self.mode_group.addButton(self.merge_radio)
        self.create_radio.setChecked(True)

        self.name_edit = QLineEdit(self.path.stem)
        self.description_edit = QLineEdit()
        self.create_widget = QWidget()
        create_form = QFormLayout(self.create_widget)
        create_form.addRow("Collection name:", self.name_edit)
        create_form.addRow("Description:", self.description_edit)

        self.target_combo = QComboBox()
        self.target_combo.addItem("Select Collection...", None)
        for collection in database.list_collections():
            self.target_combo.addItem(collection.name, str(collection.id))
        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(1.0, 1000.0)
        self.distance_spin.setValue(50.0)
        self.distance_spin.setSuffix(" m")
        self.analyze_button = QPushButton("Analyze")
        self.summary_label = QLabel()
        self.summary_label.setVisible(False)
        self.conflicts = MergeConflictsWidget()

        self.merge_widget = QWidget()
        merge_layout = QVBoxLayout(self.merge_widget)
        merge_form = QFormLayout()
        merge_form.addRow("Target Collection:", self.target_combo)
        merge_form.addRow("Duplicate distance:", self.distance_spin)
        merge_layout.addLayout(merge_form)
        merge_layout.addWidget(self.analyze_button)
        merge_layout.addWidget(self.summary_label)
        merge_layout.addWidget(self.conflicts, 1)

        self.import_button = QPushButton("Import")
        self.cancel_button = QPushButton("Cancel")
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.import_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.create_radio)
        layout.addWidget(self.merge_radio)
        layout.addWidget(self.create_widget)
        layout.addWidget(self.merge_widget, 1)
        layout.addLayout(actions)

        self.create_radio.toggled.connect(self.update_mode)
        self.name_edit.textChanged.connect(self.update_buttons)
        self.target_combo.currentIndexChanged.connect(self.invalidate_plan)
        self.distance_spin.valueChanged.connect(self.invalidate_plan)
        self.analyze_button.clicked.connect(self.analyze)
        self.import_button.clicked.connect(self.perform_import)
        self.cancel_button.clicked.connect(self.reject)

        if selected_target_id is not None:
            index = self.target_combo.findData(str(selected_target_id))
            if index >= 0:
                self.target_combo.setCurrentIndex(index)
        self.update_mode()

    def update_mode(self) -> None:
        create_mode = self.create_radio.isChecked()
        self.create_widget.setVisible(create_mode)
        self.merge_widget.setVisible(not create_mode)
        self.update_buttons()

    def update_buttons(self) -> None:
        if self.create_radio.isChecked():
            self.import_button.setEnabled(bool(self.name_edit.text().strip()))
            return
        target_selected = self._target_id() is not None
        self.analyze_button.setEnabled(target_selected)
        self.import_button.setEnabled(self.plan is not None)

    def invalidate_plan(self) -> None:
        self.plan = None
        self.summary_label.clear()
        self.summary_label.setVisible(False)
        self.conflicts.clear()
        self.update_buttons()

    def analyze(self) -> None:
        target_id = self._target_id()
        if target_id is None:
            return
        try:
            plan = prepare_waypoint_merge(
                self.source_waypoints,
                self.database.list_waypoints(target_id),
                self.distance_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import analysis failed",
                f"The GPX import could not be analyzed:\n{exc}",
            )
            return

        self.plan = plan
        self.summary_label.setText(
            f"New waypoints: {len(plan.new_waypoints)}\n"
            f"Potential duplicates: {len(plan.conflicts)}"
        )
        self.summary_label.setVisible(True)
        self.conflicts.set_conflicts(plan.conflicts)
        self.update_buttons()

    def perform_import(self) -> None:
        if self.create_radio.isChecked():
            self._create_collection()
        else:
            self._merge_into_collection()

    def _create_collection(self) -> None:
        try:
            collection = import_waypoints(
                self.database,
                self.source_waypoints,
                self.name_edit.text().strip(),
                self.path.name,
                self.description_edit.text(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import GPX failed",
                f"The GPX file could not be imported:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Import GPX",
            f'Collection "{collection.name}" was imported.',
        )
        self.created_collection_id = collection.id
        self.accept()

    def _merge_into_collection(self) -> None:
        target_id = self._target_id()
        if self.plan is None or target_id is None:
            return
        if not self._confirm_import():
            return
        try:
            result = merge_waypoints_into_collection(
                self.database,
                self.source_waypoints,
                target_id,
                self.conflicts.decisions(),
                self.plan.duplicate_threshold_m,
                analyzed_plan=self.plan,
            )
        except MergePlanChangedError as exc:
            self.invalidate_plan()
            QMessageBox.critical(self, "Import GPX failed", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Import GPX failed",
                f"The GPX file could not be imported:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Import completed",
            "Import completed.\n\n"
            f"Added: {result.added_count}\n"
            f"Replaced: {result.replaced_count}\n"
            f"Skipped: {result.skipped_count}\n"
            f"Kept both: {result.kept_both_count}",
        )
        self.merge_result = result
        self.merged_target_id = target_id
        self.accept()

    def confirmation_text(self) -> str:
        if self.plan is None:
            return ""
        decisions = tuple(self.conflicts.decisions().values())
        kept_both = sum(
            decision is ConflictDecision.KEEP_BOTH for decision in decisions
        )
        replaced = sum(
            decision is ConflictDecision.USE_SOURCE for decision in decisions
        )
        kept_target = sum(
            decision is ConflictDecision.KEEP_TARGET for decision in decisions
        )
        return (
            f"Target Collection: {self.target_combo.currentText()}\n\n"
            f"New waypoints: {len(self.plan.new_waypoints)}\n"
            f"Both nearby waypoints kept: {kept_both}\n"
            f"Target waypoints replaced: {replaced}\n"
            f"Target waypoints kept unchanged: {kept_target}\n\n"
            f"Import file:\n{self.path.name}"
        )

    def _confirm_import(self) -> bool:
        message = QMessageBox(self)
        message.setWindowTitle("Confirm import")
        message.setText(self.confirmation_text())
        import_button = message.addButton(
            "Import",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        return message.clickedButton() is import_button

    def _target_id(self) -> UUID | None:
        value = self.target_combo.currentData()
        return UUID(value) if value is not None else None
