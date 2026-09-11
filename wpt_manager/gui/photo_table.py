from uuid import UUID

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

from wpt_manager.models.adventure import Adventure
from wpt_manager.models.photo import Photo
from wpt_manager.models.track import Track

PHOTO_ID_ROLE = Qt.ItemDataRole.UserRole
PHOTO_SORT_ROLE = Qt.ItemDataRole.UserRole + 1
PHOTO_TRACK_ROLE = Qt.ItemDataRole.UserRole + 2
PHOTO_ADVENTURES_ROLE = Qt.ItemDataRole.UserRole + 3


class PhotoTableModel(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__(0, 5)
        self.setHorizontalHeaderLabels(
            ["Name", "Date", "Track", "Adventure", "Source"]
        )

    def set_photos(
        self,
        photos: list[Photo],
        tracks: dict[UUID, Track],
        memberships: dict[UUID, list[Adventure]],
    ) -> None:
        self.removeRows(0, self.rowCount())
        for photo in photos:
            track = tracks.get(photo.track_uuid) if photo.track_uuid else None
            adventures = memberships.get(photo.track_uuid, []) if track else []
            date_value = photo.taken_at
            row = [
                QStandardItem(photo.name),
                QStandardItem(date_value.strftime("%Y-%m-%d %H:%M") if date_value else "-"),
                QStandardItem(track.name if track else "-"),
                QStandardItem(", ".join(item.name for item in adventures) or "-"),
                QStandardItem(photo.source_type.title()),
            ]
            adventure_ids = {item.uuid for item in adventures}
            for item in row:
                item.setEditable(False)
                item.setData(photo.id, PHOTO_ID_ROLE)
                item.setData(photo.track_uuid, PHOTO_TRACK_ROLE)
                item.setData(adventure_ids, PHOTO_ADVENTURES_ROLE)
            row[0].setData(photo.name.casefold(), PHOTO_SORT_ROLE)
            row[1].setData(
                date_value.timestamp() if date_value is not None else float("-inf"),
                PHOTO_SORT_ROLE,
            )
            row[2].setData(row[2].text().casefold(), PHOTO_SORT_ROLE)
            row[3].setData(row[3].text().casefold(), PHOTO_SORT_ROLE)
            row[4].setData(photo.source_type.casefold(), PHOTO_SORT_ROLE)
            self.appendRow(row)


class PhotoFilterProxyModel(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.search_text = ""
        self.track_filter: UUID | str | None = None
        self.adventure_filter: UUID | str | None = None
        self.setSortRole(PHOTO_SORT_ROLE)
        self.setDynamicSortFilter(True)

    def set_filters(
        self,
        *,
        search: str | None = None,
        track: UUID | str | None = None,
        adventure: UUID | str | None = None,
    ) -> None:
        if search is not None:
            self.search_text = search.casefold()
        self.track_filter = track
        self.adventure_filter = adventure
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, row: int, parent) -> bool:
        model = self.sourceModel()
        name = model.index(row, 0, parent).data() or ""
        if self.search_text not in name.casefold():
            return False
        index = model.index(row, 0, parent)
        track_uuid = index.data(PHOTO_TRACK_ROLE)
        adventure_ids = index.data(PHOTO_ADVENTURES_ROLE) or set()
        if self.track_filter == "standalone" and track_uuid is not None:
            return False
        if self.track_filter not in {None, "standalone"} and str(track_uuid) != str(self.track_filter):
            return False
        if self.adventure_filter == "standalone" and adventure_ids:
            return False
        if self.adventure_filter not in {None, "standalone"} and not any(
            str(item) == str(self.adventure_filter) for item in adventure_ids
        ):
            return False
        return True
