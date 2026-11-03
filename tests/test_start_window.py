"""Phase-one shell regressions, adapted for the requested left-aligned menu."""
import pytest


def test_start_window_has_correct_title_and_dark_surface(window):
    assert window.windowTitle() == 'NeuroChess'
    assert window.title_label.text() == 'NeuroChess'
    assert window.isVisible()
    image = window.centralWidget().grab().toImage()
    for x, y in [(5, 5), (image.width()-6, image.height()-6)]:
        color = image.pixelColor(x, y)
        assert max(color.red(), color.green(), color.blue()) < 60
        assert color.blue() > color.red()


@pytest.mark.parametrize('size', [(640, 400), (1200, 800)])
def test_resizing_preserves_brand_and_navigation(window, app, size):
    window.resize(*size)
    for _ in range(4): app.processEvents()
    assert window.size().toTuple() == size
    assert window.title_label.isVisible()
    assert len(window.menu_page.menu_buttons) == 5
    assert window.menu_page.horizontalScrollBar().maximum() == 0
