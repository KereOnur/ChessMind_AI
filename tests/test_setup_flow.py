"""Verify real widget clicks, all setups, back navigation, guards and layout."""
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPushButton

from ui.navigation import NavigationController, OPPONENTS, Opponent, Page, PlayerColor
from ui.widgets import ASSETS, Artwork


def click(button, app):
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    for _ in range(4): app.processEvents()


def test_menu_has_exactly_five_requested_functions_and_art_on_right(window):
    menu = window.menu_page
    assert list(menu.menu_buttons) == ['Neues Spiel', 'Spiel fortsetzen', 'Statistiken', 'KI-Testzentrum', 'Beenden']
    assert len(menu.findChildren(QPushButton)) == 5
    assert window.navigation.page == Page.MENU
    assert menu.left.geometry().right() < menu.hero.geometry().left()
    assert menu.hero_art.renderer.isValid()


@pytest.mark.parametrize('feature', ['Spiel fortsetzen', 'Statistiken', 'KI-Testzentrum'])
def test_unavailable_features_show_notice_without_navigating(window, app, feature):
    click(window.menu_page.menu_buttons[feature], app)
    assert window.menu_page.notice.text() == f'{feature}: Noch nicht verfügbar.'
    assert window.navigation.page == Page.MENU
    assert window.stack.currentWidget() is window.menu_page


@pytest.mark.parametrize('opponent', list(Opponent))
@pytest.mark.parametrize('color', list(PlayerColor))
def test_all_six_setups_reach_correct_summary(window, app, opponent, color):
    click(window.menu_page.menu_buttons['Neues Spiel'], app)
    assert window.navigation.page == Page.OPPONENTS
    for value, card in window.opponent_page.opponent_cards.items():
        assert card.accessibleName() == OPPONENTS[value].title
        assert card.accessibleDescription() == OPPONENTS[value].description
    click(window.opponent_page.opponent_cards[opponent], app)
    assert window.navigation.page == Page.COLOR
    assert not window.color_page.continue_button.isEnabled()
    click(window.color_page.color_cards[color], app)
    assert window.color_page.continue_button.isEnabled()
    click(window.color_page.continue_button, app)
    assert window.navigation.page == Page.SUMMARY
    assert window.summary_page.values['Gegner'].text() == OPPONENTS[opponent].title
    assert window.summary_page.values['Spielerfarbe'].text() == color.value
    assert window.summary_page.values['Zeitkontrolle'].text() == 'Rapid 15+10'
    assert any(l.text() == 'Alle drei KI-Gegner sind spielbar. Der lokale Regeltest bleibt erhalten.' for l in window.summary_page.findChildren(QLabel))


def test_back_home_and_opponent_changes_preserve_color(window, app):
    click(window.menu_page.menu_buttons['Neues Spiel'], app)
    click(window.opponent_page.opponent_cards[Opponent.ADAPTIVE], app)
    click(window.color_page.color_cards[PlayerColor.BLACK], app)
    click(window.color_page.continue_button, app)
    click(window.summary_page.back_button, app)
    assert window.navigation.page == Page.COLOR
    assert window.color_page.color_cards[PlayerColor.BLACK].property('selected')
    click(window.color_page.back_button, app)
    assert window.navigation.page == Page.OPPONENTS
    assert window.opponent_page.opponent_cards[Opponent.ADAPTIVE].property('selected')
    click(window.opponent_page.back_button, app)
    assert window.navigation.page == Page.MENU
    click(window.menu_page.menu_buttons['Neues Spiel'], app)
    click(window.opponent_page.opponent_cards[Opponent.AMATEUR], app)
    assert window.color_page.color_cards[PlayerColor.BLACK].property('selected')
    click(window.color_page.continue_button, app)
    assert window.summary_page.values['Gegner'].text() == 'Amateur'
    assert window.summary_page.values['Spielerfarbe'].text() == 'Schwarz'
    click(window.summary_page.home_button, app)
    assert window.navigation.page == Page.MENU
    assert window.navigation.setup.player_color == PlayerColor.BLACK


def test_incomplete_setup_cannot_skip_to_summary(app):
    nav = NavigationController()
    with pytest.raises(ValueError): nav.show_summary()
    with pytest.raises(ValueError): nav.choose_color(PlayerColor.WHITE)
    assert nav.page == Page.MENU
    assert nav.setup.player_color is None
    nav.choose_opponent(Opponent.GRANDMASTER)
    with pytest.raises(ValueError): nav.show_summary()
    assert nav.page == Page.COLOR


@pytest.mark.parametrize('size', [(420, 300), (768, 600), (1440, 900)])
@pytest.mark.parametrize('page', [Page.MENU, Page.OPPONENTS, Page.COLOR, Page.SUMMARY])
def test_pages_fit_width_and_keep_wrapped_text_readable(window, app, size, page):
    window.resize(*size)
    if page != Page.MENU: window.navigation.new_game()
    if page in (Page.COLOR, Page.SUMMARY): window.navigation.choose_opponent(Opponent.ADAPTIVE)
    if page == Page.SUMMARY:
        window.navigation.choose_color(PlayerColor.BLACK)
        window.navigation.show_summary()
    for _ in range(6): app.processEvents()
    current = window.stack.currentWidget()
    assert current.horizontalScrollBar().maximum() == 0
    assert current.body.width() <= current.viewport().width()
    if size == (420, 300):
        assert current.verticalScrollBar().maximum() > 0
    for text in current.findChildren(QLabel):
        if not text.isVisibleTo(current): continue
        position = text.mapTo(current.body, QPoint(0, 0))
        assert position.x() >= 0, text.text()
        assert position.x() + text.width() <= current.body.width() + 1, text.text()
        needed = text.heightForWidth(text.width())
        assert needed <= text.height() + 1, (text.text(), text.height(), needed)


def test_keyboard_can_activate_new_game(window, app):
    button = window.menu_page.menu_buttons['Neues Spiel']
    button.setFocus()
    QTest.keyClick(button, Qt.Key.Key_Space)
    app.processEvents()
    assert window.navigation.page == Page.OPPONENTS


def test_quit_button_is_reachable_by_scrolling_and_closes(window, app):
    window.resize(420, 300)
    for _ in range(4): app.processEvents()
    button = window.menu_page.menu_buttons['Beenden']
    window.menu_page.ensureWidgetVisible(button)
    app.processEvents()
    click(button, app)
    assert not window.isVisible()


def test_all_art_is_local_static_valid_and_distinct(window):
    paths = sorted(ASSETS.glob('*.svg'))
    assert len(paths) == 6
    assert len({p.read_text() for p in paths}) == 6
    for path in paths:
        svg = QSvgRenderer(str(path))
        assert svg.isValid(), path.name
        assert not svg.animated()
        source = path.read_text()
        assert '<image' not in source
        assert 'href=' not in source
    assert all(not art.renderer.animated() for art in window.findChildren(Artwork))
