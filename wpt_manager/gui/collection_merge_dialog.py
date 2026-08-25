from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.database.collection_merge import (
    merge_collections,
    prepare_collection_merge,
)
from wpt_manager.database.database import Database
from wpt_manager.gui.theme import install_native_title_bar_theming
from wpt_manager.models.collection_merge import (
    ConflictDecision,
    MergeConflict,
    MergePlan,
)
from wpt_manager.models.waypoint import Waypoint


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
        self.conflict_decision_groups: dict[UUID, QButtonGroup] = {}

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

        self.set_all_widget = QWidget()
        set_all_layout = QHBoxLayout(self.set_all_widget)
        set_all_layout.setContentsMargins(0, 0, 0, 0)
        set_all_layout.addWidget(QLabel("Set all:"))
        self.set_all_buttons: dict[ConflictDecision, QPushButton] = {}
        for decision, label in (
            (ConflictDecision.KEEP_TARGET, "Keep target"),
            (ConflictDecision.USE_SOURCE, "Use source"),
            (ConflictDecision.KEEP_BOTH, "Keep both"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, value=decision: self.set_all(value)
            )
            self.set_all_buttons[decision] = button
            set_all_layout.addWidget(button)
        set_all_layout.addStretch()
        self.set_all_widget.setVisible(False)

        self.conflicts_widget = QWidget()
        self.conflicts_layout = QVBoxLayout(self.conflicts_widget)
        self.conflicts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.conflicts_scroll = QScrollArea()
        self.conflicts_scroll.setWidgetResizable(True)
        self.conflicts_scroll.setWidget(self.conflicts_widget)

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
        layout.addWidget(self.set_all_widget)
        layout.addWidget(self.conflicts_scroll, 1)
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
        self.set_all_widget.setVisible(False)
        self.merge_button.setEnabled(False)
        self._clear_conflicts()
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
        self._show_conflicts(plan.conflicts)
        self.set_all_widget.setVisible(bool(plan.conflicts))
        self.merge_button.setEnabled(True)

    @staticmethod
    def _selected_id(combo: QComboBox) -> UUID | None:
        value = combo.currentData()
        return UUID(value) if value is not None else None

    def _show_conflicts(
        self,
        conflicts: tuple[MergeConflict, ...],
    ) -> None:
        self._clear_conflicts()
        for conflict in conflicts:
            panel = QGroupBox(f"Potential duplicate — {conflict.distance_m:.1f} m")
            panel_layout = QVBoxLayout(panel)

            waypoints_layout = QHBoxLayout()
            waypoints_layout.addWidget(
                self._waypoint_panel("Source waypoint", conflict.source)
            )
            waypoints_layout.addWidget(
                self._waypoint_panel("Target waypoint", conflict.target)
            )
            panel_layout.addLayout(waypoints_layout)

            decisions_layout = QHBoxLayout()
            group = QButtonGroup(panel)
            for decision, label in (
                (ConflictDecision.KEEP_TARGET, "Keep target"),
                (ConflictDecision.USE_SOURCE, "Use source"),
                (ConflictDecision.KEEP_BOTH, "Keep both"),
            ):
                radio = QRadioButton(label)
                group.addButton(radio, decision.value)
                decisions_layout.addWidget(radio)
                if decision is ConflictDecision.KEEP_TARGET:
                    radio.setChecked(True)
            panel_layout.addLayout(decisions_layout)
            self.conflict_decision_groups[conflict.source.id] = group
            self.conflicts_layout.addWidget(panel)

    @staticmethod
    def _waypoint_panel(title: str, waypoint: Waypoint) -> QGroupBox:
        panel = QGroupBox(title)
        form = QFormLayout(panel)
        values = (
            ("Name", waypoint.name),
            ("Coordinates", f"{waypoint.latitude}, {waypoint.longitude}"),
            ("Icon", waypoint.icon),
            ("Color", waypoint.color),
            ("Background", waypoint.background),
            ("Note", waypoint.note),
            ("Comment", waypoint.comment),
        )
        for label, value in values:
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            form.addRow(label, value_label)
        return panel

    def _clear_conflicts(self) -> None:
        self.conflict_decision_groups.clear()
        while self.conflicts_layout.count():
            item = self.conflicts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_all(self, decision: ConflictDecision) -> None:
        for group in self.conflict_decision_groups.values():
            button = group.button(decision.value)
            if button is not None:
                button.setChecked(True)

    def conflict_decisions(self) -> dict[UUID, ConflictDecision]:
        return {
            source_id: ConflictDecision(group.checkedId())
            for source_id, group in self.conflict_decision_groups.items()
        }

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
