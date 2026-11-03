"""Application shell: connect presentation pages to in-memory navigation."""
import sys
import time

from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QAction, QFontDatabase, QKeySequence
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from ui.navigation import NavigationController, Page
from ui.board.page import BoardPreviewPage
from ui.rule_test.page import RuleTestPage
from ui.pages import ColorPage, MainMenuPage, OpponentPage, SummaryPage
from ui.theme import STYLE


class MainWindow(QMainWindow):
    """Keep phase-one window behavior while adding the setup flow and isolated board preview."""
    def __init__(self,*,enable_storage=True,storage_path=None,startup_prompt=True,clock_now=None,amateur_config=None,grandmaster_config=None,adaptive_config=None,review_budget=None):
        super().__init__()
        self._clock_now=clock_now or time.monotonic
        self.amateur=None;self.grandmaster=None;self.adaptive=None;self.storage=None;self.review_center=None;self._allow_close=not enable_storage;self._pending_rule_session=None
        self.setWindowTitle('NeuroChess')
        self.setWindowFlag(Qt.WindowType.WindowFullscreenButtonHint, True)
        self.resize(1280, 850)
        self.setMinimumSize(420, 300)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
        self.setStyleSheet(STYLE)
        self.navigation = NavigationController(self)
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self.menu_page = MainMenuPage(enable_storage=enable_storage)
        self.opponent_page = OpponentPage()
        self.color_page = ColorPage()
        self.summary_page = SummaryPage()
        self.preview_page = BoardPreviewPage()
        self.rule_page = RuleTestPage()
        self.pages = {Page.MENU: self.menu_page, Page.OPPONENTS: self.opponent_page,
                      Page.COLOR: self.color_page, Page.SUMMARY: self.summary_page, Page.PREVIEW: self.preview_page, Page.RULE_TEST: self.rule_page}
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.title_label = self.menu_page.title_label

        controller = self.navigation
        self.menu_page.new_game_requested.connect(controller.new_game)
        self.menu_page.quit_requested.connect(self.close)
        self.opponent_page.back_requested.connect(controller.back)
        self.opponent_page.opponent_chosen.connect(controller.choose_opponent)
        self.color_page.back_requested.connect(controller.back)
        self.color_page.color_chosen.connect(controller.choose_color)
        self.color_page.continue_requested.connect(controller.show_summary)
        self.summary_page.back_requested.connect(controller.back)
        self.summary_page.home_requested.connect(controller.home)
        self.summary_page.preview_requested.connect(controller.open_preview)
        self.preview_page.back_requested.connect(controller.back)
        self.preview_page.home_requested.connect(controller.home)
        if not enable_storage:
            # Explicit isolation for the historical phase 1–4 regression harness.
            self.summary_page.rule_test_requested.connect(controller.open_rule_test)
            self.rule_page.back_requested.connect(controller.back)
            self.rule_page.home_requested.connect(controller.home)
            self.menu_page.resume_requested.connect(lambda:self.menu_page.show_unavailable('Spiel fortsetzen'))
        controller.selection_changed.connect(self.refresh_selection)
        controller.page_changed.connect(self.show_page)
        self.refresh_selection()
        self.show_page(Page.MENU)
        self._add_window_actions()
        if enable_storage:
            from database.store import DEFAULT_PATH
            from ui.persistence import PersistenceCoordinator
            self.rule_page.persistence_enabled=True
            self.storage=PersistenceCoordinator(self,storage_path or DEFAULT_PATH,startup_prompt=startup_prompt)
            self.summary_page.rule_test_requested.connect(self.storage.begin_new)
            self.summary_page.amateur_requested.connect(self.storage.begin_amateur)
            self.summary_page.grandmaster_requested.connect(self.storage.begin_grandmaster)
            self.summary_page.adaptive_requested.connect(self.storage.begin_adaptive)
            self.rule_page.back_requested.connect(lambda:self.storage.save_leave('summary'))
            self.rule_page.home_requested.connect(lambda:self.storage.save_leave('menu'))
            self.menu_page.resume_requested.connect(self.storage.request_resume)
            from ui.review_center import Center, Statistics
            self.review_center=Center(self, review_budget) if review_budget else Center(self)
            self.statistics_page=Statistics(self)
            self.menu_page.review_requested.connect(self.review_center.open_center)
            self.menu_page.statistics_requested.connect(self.statistics_page.open_statistics)
        from ui.amateur_controller import AmateurController
        self.amateur=AmateurController(self,amateur_config)
        from ui.grandmaster_controller import GrandmasterController
        self.grandmaster=GrandmasterController(self,grandmaster_config)
        from ui.adaptive_controller import AdaptiveController
        self.adaptive=AdaptiveController(self,adaptive_config)

    def show_page(self, page):
        if self.stack.currentWidget() is self.rule_page:
            self.rule_page.leave()
        if page == Page.RULE_TEST:
            session=self._pending_rule_session;self._pending_rule_session=None
            self.rule_page.configure(self.navigation.setup,session=session)
        if self.stack.currentWidget() is self.preview_page:
            self.preview_page.leave()
        if page == Page.PREVIEW:
            self.preview_page.configure(self.navigation.setup)
        self.stack.setCurrentWidget(self.pages[page])
        if page == Page.RULE_TEST:
            self.rule_page.back_button.setFocus()
        elif page == Page.PREVIEW:
            self.preview_page.back_button.setFocus()
        elif page == Page.OPPONENTS:
            self.opponent_page.back_button.setFocus()
        elif page == Page.COLOR:
            self.color_page.back_button.setFocus()
        elif page == Page.SUMMARY:
            self.summary_page.back_button.setFocus()
        else:
            self.menu_page.menu_buttons['Neues Spiel'].setFocus()

    def install_rule_session(self,setup,session):
        self.navigation.setup=setup;self.navigation.selection_changed.emit()
        self._pending_rule_session=session
        self.navigation.open_rule_test()

    def refresh_selection(self):
        setup = self.navigation.setup
        self.opponent_page.refresh(setup)
        self.color_page.refresh(setup)
        self.summary_page.refresh(setup)

    def _add_window_actions(self):
        fullscreen = QAction('Vollbild umschalten', self)
        fullscreen.setShortcut(QKeySequence('Ctrl+Meta+F' if sys.platform == 'darwin' else 'F11'))
        fullscreen.triggered.connect(self.toggle_fullscreen)
        self.addAction(fullscreen)
        escape = QAction('Vollbild verlassen', self)
        escape.setShortcut(QKeySequence('Esc'))
        escape.triggered.connect(self.leave_fullscreen)
        self.addAction(escape)
        quit_action = QAction('NeuroChess beenden', self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def closeEvent(self, event):
        if self.storage is None and self.amateur is not None and (not self.amateur.prepare_close() or not self.grandmaster.prepare_close() or not self.adaptive.prepare_close()):
            event.ignore();QTimer.singleShot(10,self.close);return
        if self.storage is not None and not self._allow_close:
            event.ignore();self.storage.request_close();return
        self.rule_page.leave()
        self.preview_page.leave()
        super().closeEvent(event)
