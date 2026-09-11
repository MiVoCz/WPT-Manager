import os
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication

from wpt_manager.database.database import Database
from wpt_manager.gui.main_window import MainWindow
from wpt_manager.gui.photo_preview import PhotoPreview, photo_preview_url
from wpt_manager.models.photo import Photo
from wpt_manager.photos.imagekit import build_imagekit_preview_url


def test_imagekit_transformation_preserves_query():
    url = build_imagekit_preview_url("https://ik.imagekit.io/a.jpg?token=a%2Bb&x=&x=2&tr=q-80#part", 600, 400)
    parts = urlsplit(url)
    assert parts.path == "/a.jpg" and parts.fragment == "part"
    assert parse_qs(parts.query, keep_blank_values=True) == {
        "token": ["a+b"], "x": ["", "2"], "tr": ["q-80:w-600,h-400,c-at_max"],
    }


@pytest.mark.parametrize("source, thumbnail, url, expected", [
    ("imagekit", "https://host/thumb", "https://host/original", "https://host/thumb"),
    ("synology", None, "https://host/photo", "https://host/photo"),
    ("local", None, "file:///C:/photo.jpg", "file:///C:/photo.jpg"),
    ("imagekit", None, None, None),
])
def test_source_priority(source, thumbnail, url, expected):
    assert photo_preview_url(Photo("Photo", source, source_url=url, thumbnail_url=thumbnail)) == expected


def test_imagekit_source_is_transformed():
    url = photo_preview_url(Photo("Photo", "imagekit", source_url="https://host/photo"))
    assert parse_qs(urlsplit(url).query)["tr"] == ["w-600,h-400,c-at_max"]


@pytest.fixture
def preview():
    application = QApplication.instance() or QApplication([])
    widget = PhotoPreview()
    yield widget
    widget.show_photo(None)
    widget.close()
    application.processEvents()


def finish(widget, reply, generation, url, valid=True):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap = QPixmap(40, 20)
    pixmap.fill()
    pixmap.save(buffer, "PNG")
    reply.error.return_value = QNetworkReply.NetworkError.NoError
    reply.readAll.return_value = data if valid else QByteArray(b"not an image")
    widget._finished(reply, generation, url)


def test_stale_response_ignored_and_cache_resize(preview, mock_preview_downloads):
    first = Photo("First", "local", source_url="https://host/first")
    second = Photo("Second", "local", source_url="https://host/second")
    preview.show_photo(first)
    old, generation = preview._reply, preview._generation
    preview.show_photo(second)
    old.abort.assert_called_once()
    finish(preview, old, generation, first.source_url)
    assert preview.text() == "Loading..." and preview._original.isNull()
    finish(preview, preview._reply, preview._generation, second.source_url)
    assert not preview.pixmap().isNull()
    count = mock_preview_downloads.call_count
    preview.resize(320, 220)
    preview.show_photo(second)
    assert mock_preview_downloads.call_count == count
    assert preview.pixmap().width() / preview.pixmap().height() == 2
    preview.show_photo(None)
    assert preview.text() == "No photo selected"


@pytest.mark.parametrize("failure", ["http", "invalid", "timeout"])
def test_download_failure(preview, failure):
    preview.show_photo(Photo("Photo", "local", source_url="https://host/image?token=secret"))
    reply = preview._reply
    if failure == "invalid":
        finish(preview, reply, preview._generation, "url", False)
    else:
        if failure == "timeout":
            preview._timeout()
            reply.abort.assert_called_once()
        reply.error.return_value = QNetworkReply.NetworkError.ContentNotFoundError
        preview._finished(reply, preview._generation, "url")
    assert preview.text() == "Failed to load preview"
    assert "secret" not in preview.text()


def test_no_preview_and_invalid_url(preview):
    preview.show_photo(Photo("Empty", "local"))
    assert preview.text() == "No preview available"
    preview.show_photo(Photo("Invalid", "local", source_url="ftp://host/image"))
    assert preview.text() == "Failed to load preview"


def test_memory_cache_bounded(preview):
    for index in range(33):
        url = f"https://host/{index}"
        preview.show_photo(Photo(str(index), "local", source_url=url))
        finish(preview, preview._reply, preview._generation, url)
    assert len(preview._cache) == 32
    assert "https://host/0" not in preview._cache


def test_synology_record_readable_without_import_ui(preview, tmp_path):
    database = Database(tmp_path / "photos.db")
    database.initialize()
    photo = Photo("Legacy", "synology", source_url="https://host/legacy")
    database.save_photo(photo)
    window = MainWindow(database, icon_catalog=[])
    assert not hasattr(window, "import_synology_button")
    assert not hasattr(window, "import_photos_from_synology")
    assert hasattr(window, "import_imagekit_button")
    saved = database.get_photo(photo.id)
    window.photo_editor.show_photo(saved, [])
    assert window.photo_editor.source_type_edit.text() == "synology"
    assert window.photo_editor.preview_label.text() == "Loading..."
    window.photo_editor.clear([])
    window.close()
