from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton

from configgen.appinfo import APP_NAME, __version__
from configgen.ui.about import AboutDialog


def test_shows_app_name_and_version(qtbot):
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    assert APP_NAME in dialog.windowTitle()
    texts = [dialog.layout().itemAt(i).widget().text() for i in range(dialog.layout().count())]
    assert any(__version__ in t for t in texts)


def test_close_button_accepts_dialog(qtbot):
    dialog = AboutDialog()
    qtbot.addWidget(dialog)
    close_button = dialog.findChild(QPushButton)
    qtbot.mouseClick(close_button, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Accepted
