from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wpt_manager.models.collection_merge import (
    ConflictDecision,
    MergeConflict,
)
from wpt_manager.models.waypoint import Waypoint


class MergeConflictsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.decision_groups: dict[UUID, QButtonGroup] = {}

        self.set_all_widget = QWidget()
        set_all_layout = QHBoxLayout(self.set_all_widget)
        set_all_layout.setContentsMargins(0, 0, 0, 0)
        set_all_layout.addWidget(QLabel("Set all:"))
        for decision, label in (
            (ConflictDecision.KEEP_TARGET, "Keep target"),
            (ConflictDecision.USE_SOURCE, "Use source"),
            (ConflictDecision.KEEP_BOTH, "Keep both"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, value=decision: self.set_all(value)
            )
            set_all_layout.addWidget(button)
        set_all_layout.addStretch()
        self.set_all_widget.setVisible(False)

        self.conflicts_widget = QWidget()
        self.conflicts_layout = QVBoxLayout(self.conflicts_widget)
        self.conflicts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.conflicts_widget)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.set_all_widget)
        layout.addWidget(self.scroll, 1)

    def set_conflicts(self, conflicts: tuple[MergeConflict, ...]) -> None:
        self.clear()
        self.set_all_widget.setVisible(bool(conflicts))
        for conflict in conflicts:
            panel = QGroupBox(
                f"Potential duplicate — {conflict.distance_m:.1f} m"
            )
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
            self.decision_groups[conflict.source.id] = group
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

    def clear(self) -> None:
        self.decision_groups.clear()
        self.set_all_widget.setVisible(False)
        while self.conflicts_layout.count():
            item = self.conflicts_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def set_all(self, decision: ConflictDecision) -> None:
        for group in self.decision_groups.values():
            button = group.button(decision.value)
            if button is not None:
                button.setChecked(True)

    def decisions(self) -> dict[UUID, ConflictDecision]:
        return {
            source_id: ConflictDecision(group.checkedId())
            for source_id, group in self.decision_groups.items()
        }
