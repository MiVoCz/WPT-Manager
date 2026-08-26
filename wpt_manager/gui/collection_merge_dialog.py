from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.collection_merge import (
    merge_collections,
    prepare_collection_merge,
)
from wpt_manager.database.database import Database
from wpt_manager.gui.merge_conflicts_widget import MergeConflictsWidget
from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.models.collection_merge import (
    ConflictDecision,
    MergePlan,
)


class CollectionMergeDialog(QDialog):
    def __init__(
        self,
        database: Database,
        selected_target_id: UUID | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        install_native_title_bar_theming()
        self.database = database
        self.plan: MergePlan | None = None
        self.merged_target_id: UUID | None = None

        self.setWindowTitle("Merge Collections")
        self.resize(850, 700)

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.source_combo.addItem("Select Collection...", None)
        self.target_combo.addItem("Select Collection...", None)
        for collection in database.list_collections():
            self.source_combo.addItem(collection.name, str(collection.id))
            self.target_combo.addItem(collection.name, str(collection.id))

        self.direction_label = QLabel("↓ Merge into ↓")
        self.direction_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(1.0, 1000.0)
        self.distance_spin.setValue(50.0)
        self.distance_spin.setSuffix(" m")

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.setEnabled(False)
        self.merge_button = QPushButton("Merge")
        self.merge_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancel")

        self.summary_label = QLabel()
        self.summary_label.setVisible(False)

        self.conflicts = MergeConflictsWidget()
        self.conflict_decision_groups = self.conflicts.decision_groups

        selection_layout = QVBoxLayout()
        selection_layout.addWidget(QLabel("Source Collection"))
        selection_layout.addWidget(self.source_combo)
        selection_layout.addWidget(self.direction_label)
        selection_layout.addWidget(QLabel("Target Collection"))
        selection_layout.addWidget(self.target_combo)

        distance_layout = QFormLayout()
        distance_layout.addRow("Duplicate distance:", self.distance_spin)

        action_layout = QHBoxLayout()
        action_layout.addWidget(self.analyze_button)
        action_layout.addStretch()
        action_layout.addWidget(self.cancel_button)
        action_layout.addWidget(self.merge_button)

        layout = QVBoxLayout(self)
        layout.addLayout(selection_layout)
        layout.addLayout(distance_layout)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.conflicts, 1)
        layout.addLayout(action_layout)

        self.source_combo.currentIndexChanged.connect(self.invalidate_plan)
        self.target_combo.currentIndexChanged.connect(self.invalidate_plan)
        self.distance_spin.valueChanged.connect(self.invalidate_plan)
        self.analyze_button.clicked.connect(self.analyze)
        self.merge_button.clicked.connect(self.perform_merge)
        self.cancel_button.clicked.connect(self.reject)

        if selected_target_id is not None:
            target_index = self.target_combo.findData(str(selected_target_id))
            if target_index >= 0:
                self.target_combo.setCurrentIndex(target_index)
        self.update_analyze_button()

    def invalidate_plan(self) -> None:
        self.plan = None
        self.summary_label.clear()
        self.summary_label.setVisible(False)
        self.merge_button.setEnabled(False)
        self.conflicts.clear()
        self.update_analyze_button()

    def update_analyze_button(self) -> None:
        source_id = self._selected_id(self.source_combo)
        target_id = self._selected_id(self.target_combo)
        self.analyze_button.setEnabled(
            source_id is not None
            and target_id is not None
            and source_id != target_id
        )

    def analyze(self) -> None:
        source_id = self._selected_id(self.source_combo)
        target_id = self._selected_id(self.target_combo)
        if source_id is None or target_id is None or source_id == target_id:
            return

        try:
            plan = prepare_collection_merge(
                self.database,
                source_id,
                target_id,
                self.distance_spin.value(),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Merge analysis failed",
                f"The Collections could not be analyzed:\n{exc}",
            )
            return

        self.plan = plan
        self.summary_label.setText(
            f"Source: {plan.source_collection.name}\n"
            f"Target: {plan.target_collection.name}\n\n"
            f"New waypoints: {len(plan.new_waypoints)}\n"
            f"Potential duplicates: {len(plan.conflicts)}"
        )
        self.summary_label.setVisible(True)
        self.conflicts.set_conflicts(plan.conflicts)
        self.merge_button.setEnabled(True)

    @staticmethod
    def _selected_id(combo: QComboBox) -> UUID | None:
        value = combo.currentData()
        return UUID(value) if value is not None else None

    def set_all(self, decision: ConflictDecision) -> None:
        self.conflicts.set_all(decision)

    def conflict_decisions(self) -> dict[UUID, ConflictDecision]:
        return self.conflicts.decisions()

    def perform_merge(self) -> None:
        if self.plan is None:
            return
        if not self._confirm_merge():
            return

        try:
            result = merge_collections(
                self.database,
                self.plan.source_collection.id,
                self.plan.target_collection.id,
                self.conflict_decisions(),
                self.plan.duplicate_threshold_m,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Merge failed",
                f"The Collections could not be merged:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Merge completed",
            "Merge completed.\n\n"
            f"Added: {result.added_count}\n"
            f"Replaced: {result.replaced_count}\n"
            f"Skipped: {result.skipped_count}\n"
            f"Kept both: {result.kept_both_count}\n\n"
            "Source Collection was not modified.",
        )
        self.merged_target_id = self.plan.target_collection.id
        self.accept()

    def _confirm_merge(self) -> bool:
        if self.plan is None:
            return False
        message = QMessageBox(self)
        message.setWindowTitle("Confirm merge")
        message.setText(self.confirmation_text())
        merge_button = message.addButton(
            "Merge",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message.addButton(QMessageBox.StandardButton.Cancel)
        message.exec()
        return message.clickedButton() is merge_button

    def confirmation_text(self) -> str:
        if self.plan is None:
            return ""

        decisions = self.conflict_decisions()
        kept_both = sum(
            decision is ConflictDecision.KEEP_BOTH
            for decision in decisions.values()
        )
        replaced = sum(
            decision is ConflictDecision.USE_SOURCE
            for decision in decisions.values()
        )
        kept_target = sum(
            decision is ConflictDecision.KEEP_TARGET
            for decision in decisions.values()
        )
        return (
            f'Source Collection:\n"{self.plan.source_collection.name}"\n'
            "↓ Merge into ↓\n"
            f'Target Collection:\n"{self.plan.target_collection.name}"\n\n'
            f"New waypoints: {len(self.plan.new_waypoints)}\n"
            f"Both nearby waypoints kept: {kept_both}\n"
            f"Target waypoints replaced: {replaced}\n"
            f"Target waypoints kept unchanged: {kept_target}\n\n"
            "Source collection will not be deleted."
        )
