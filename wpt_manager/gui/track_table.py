from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel

from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track


TRACK_ID_ROLE = Qt.ItemDataRole.UserRole
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
ADVENTURE_IDS_ROLE = Qt.ItemDataRole.UserRole + 2


class TrackTableModel(QStandardItemModel):
    visibility_changed = Signal(object, bool)

    def __init__(self) -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(
            ["Visible", "Name", "Date", "Distance", "Adventure"]
        )
        self.itemChanged.connect(self._item_changed)
        self._loading = False

    def set_tracks(
        self,
        tracks: list[Track],
        memberships: dict[UUID, list[Adventure]],
        visible_ids: set[UUID],
    ) -> None:
        self._loading = True
        self.removeRows(0, self.rowCount())
        for track in tracks:
            adventures = memberships.get(track.id, [])
            visible = QStandardItem()
            visible.setCheckable(True)
            visible.setCheckState(
                Qt.CheckState.Checked
                if track.id in visible_ids else Qt.CheckState.Unchecked
            )
            visible.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            date_value = track.start_time or track.created_at
            name = QStandardItem(track.name)
            date = QStandardItem(date_value.strftime("%Y-%m-%d %H:%M"))
            distance = QStandardItem(f"{track.distance_m / 1000:.1f} km")
            adventure = QStandardItem(
                ", ".join(item.name for item in adventures) or "-"
            )
            row = [visible, name, date, distance, adventure]
            for item in row[1:]:
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            adventure_ids = {item.uuid for item in adventures}
            for item in row:
                item.setData(track.id, TRACK_ID_ROLE)
                item.setData(adventure_ids, ADVENTURE_IDS_ROLE)
            name.setData(track.name.casefold(), SORT_ROLE)
            date.setData(date_value, SORT_ROLE)
            distance.setData(track.distance_m, SORT_ROLE)
            adventure.setData(adventure.text().casefold(), SORT_ROLE)
            self.appendRow(row)
        self._loading = False

    def _item_changed(self, item: QStandardItem) -> None:
        if not self._loading and item.column() == 0:
            self.visibility_changed.emit(
                item.data(TRACK_ID_ROLE),
                item.checkState() == Qt.CheckState.Checked,
            )


class TrackFilterProxyModel(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.search_text = ""
        self.adventure_filter: UUID | str | None = None
        self.setSortRole(SORT_ROLE)
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str) -> None:
        self.search_text = text.casefold()
        self._refilter()

    def set_adventure_filter(self, value: UUID | str | None) -> None:
        self.adventure_filter = value
        self._refilter()

    def _refilter(self) -> None:
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row: int, parent) -> bool:
        model = self.sourceModel()
        name = model.index(row, 1, parent).data() or ""
        if self.search_text not in name.casefold():
            return False
        adventure_ids = model.index(row, 0, parent).data(
            ADVENTURE_IDS_ROLE
        ) or set()
        if self.adventure_filter == "standalone":
            return not adventure_ids
        if self.adventure_filter is not None:
            return any(
                str(adventure_id) == str(self.adventure_filter)
                for adventure_id in adventure_ids
            )
        return True
