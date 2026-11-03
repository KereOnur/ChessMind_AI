"""Run widget checks without using the user's desktop."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    window = MainWindow(enable_storage=False)
    window.show()
    for _ in range(4):
        app.processEvents()
    yield window
    window.close()
    app.processEvents()
