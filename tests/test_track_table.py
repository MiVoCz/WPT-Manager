import os
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from wpt_manager.gui.track_table import TrackFilterProxyModel, TrackTableModel
from wpt_manager.models.adventure import Adventure
from wpt_manager.models.track import Track


def _names(proxy):
    return [proxy.index(row, 1).data() for row in range(proxy.rowCount())]


def test_track_catalog_search_adventure_and_standalone_filters():
    application = QApplication.instance() or QApplication([])
    italy = Adventure("Italy")
    alps = Adventure("Alps")
    standalone = Track("Garda solo", "a.gpx")
    one = Track("Garda day", "b.gpx")
    multiple = Track("Alpine stage", "c.gpx")
    model = TrackTableModel()
    proxy = TrackFilterProxyModel()
    proxy.setSourceModel(model)
    model.set_tracks(
        [standalone, one, multiple],
        {one.id: [italy], multiple.id: [italy, alps]}, set(),
    )
    assert set(_names(proxy)) == {"Garda solo", "Garda day", "Alpine stage"}
    proxy.set_adventure_filter("standalone")
    assert _names(proxy) == ["Garda solo"]
    proxy.set_search_text("GARDA")
    assert _names(proxy) == ["Garda solo"]
    proxy.set_adventure_filter(italy.uuid)
    assert _names(proxy) == ["Garda day"]
    proxy.set_search_text("")
    assert set(_names(proxy)) == {"Garda day", "Alpine stage"}
    application.processEvents()


def test_track_catalog_sorts_name_date_and_distance_by_raw_values():
    application = QApplication.instance() or QApplication([])
    first = Track(
        "zulu", "a.gpx", distance_m=900,
        start_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    second = Track(
        "Alpha", "b.gpx", distance_m=12_000,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    model = TrackTableModel()
    proxy = TrackFilterProxyModel()
    proxy.setSourceModel(model)
    model.set_tracks([first, second], {}, set())
    proxy.sort(1, Qt.SortOrder.AscendingOrder)
    assert _names(proxy) == ["Alpha", "zulu"]
    proxy.sort(2, Qt.SortOrder.DescendingOrder)
    assert _names(proxy) == ["Alpha", "zulu"]
    proxy.sort(3, Qt.SortOrder.AscendingOrder)
    assert _names(proxy) == ["zulu", "Alpha"]
    application.processEvents()
