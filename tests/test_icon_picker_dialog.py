import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from wpt_manager.gui.icon_picker_dialog import IconPickerDialog
from wpt_manager.io.icon_catalog import load_icon_catalog


def test_icon_picker_groups_filters_and_selects_icon(tmp_path):
    application = QApplication.instance() or QApplication([])
    icon_directory = tmp_path / "icons"
    first_group = icon_directory / "Alpha"
    second_group = icon_directory / "Beta"
    first_group.mkdir(parents=True)
    second_group.mkdir()
    first_icon = first_group / "mx_first.svg"
    second_icon = second_group / "mx_second.svg"
    first_icon.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
        '<rect width="24" height="24"/></svg>',
        encoding="utf-8",
    )
    second_icon.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="16">'
        '<rect width="32" height="16"/></svg>',
        encoding="utf-8",
    )
    dialog = IconPickerDialog(load_icon_catalog(icon_directory))

    assert dialog.group_list.count() == 2
    assert dialog.group_list.item(0).text() == "Alpha"
    assert dialog.group_list.item(1).text() == "Beta"
    assert dialog.icon_list.count() == 1
    assert dialog.icon_list.item(0).text() == "first"
    assert dialog.icon_list.item(0).data(
        Qt.ItemDataRole.UserRole
    ) == "first"
    assert not dialog.icon_list.item(0).icon().isNull()
    assert not dialog.select_button.isEnabled()

    dialog.group_list.setCurrentRow(1)
    assert dialog.icon_list.count() == 1
    assert dialog.icon_list.item(0).text() == "second"

    dialog.icon_list.setCurrentRow(0)
    assert dialog.select_button.isEnabled()
    dialog.icon_list.itemDoubleClicked.emit(dialog.icon_list.item(0))

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_icon_name == "second"

    dialog.close()
    application.processEvents()


def test_empty_icon_picker_has_empty_state():
    application = QApplication.instance() or QApplication([])

    dialog = IconPickerDialog([])

    assert dialog.group_list.count() == 0
    assert dialog.icon_list.count() == 0
    assert not dialog.empty_label.isHidden()
    assert not dialog.select_button.isEnabled()

    dialog.close()
    application.processEvents()


def test_icon_picker_searches_all_groups_case_insensitively(tmp_path):
    application = QApplication.instance() or QApplication([])
    icon_directory = tmp_path / "icons"
    first_group = icon_directory / "Alpha"
    second_group = icon_directory / "Beta"
    first_group.mkdir(parents=True)
    second_group.mkdir()
    (first_group / "mx_Castle.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>',
        encoding="utf-8",
    )
    (first_group / "mx_fuel.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>',
        encoding="utf-8",
    )
    (second_group / "mx_castle_ruins.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>',
        encoding="utf-8",
    )
    dialog = IconPickerDialog(load_icon_catalog(icon_directory))
    dialog.group_list.setCurrentRow(1)

    dialog.search_edit.setText("CASTLE")

    assert dialog.icon_list.count() == 2
    assert [
        dialog.icon_list.item(index).data(Qt.ItemDataRole.UserRole)
        for index in range(dialog.icon_list.count())
    ] == ["Castle", "castle_ruins"]
    assert [
        dialog.icon_list.item(index).data(Qt.ItemDataRole.UserRole + 1)
        for index in range(dialog.icon_list.count())
    ] == ["Alpha", "Beta"]
    assert dialog.icon_list.item(0).text() == "Castle\nAlpha"
    assert dialog.icon_list.item(1).text() == "castle_ruins\nBeta"

    dialog.icon_list.setCurrentRow(1)
    assert dialog.select_button.isEnabled()
    dialog.search_edit.clear()

    assert dialog.icon_list.count() == 1
    assert dialog.icon_list.item(0).text() == "castle_ruins"
    assert not dialog.select_button.isEnabled()

    dialog.search_edit.setText("castle")
    dialog.icon_list.setCurrentRow(1)
    dialog.select_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_icon_name == "castle_ruins"

    dialog.close()
    application.processEvents()
