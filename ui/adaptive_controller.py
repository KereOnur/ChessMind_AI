"""Adaptive jobs use the immutable model returned by the last game commit."""
from ai import adaptive
from ui.amateur_controller import AmateurController
from ui.grandmaster_controller import GrandmasterThread


class AdaptiveThread(GrandmasterThread):
    def __init__(self, *args):
        super().__init__(*args)
        self.setObjectName("NeuroChess Adaptive Grandmaster")

    def run(self):
        config, weights = self.config
        try:
            result = adaptive.search(self.board, self.remaining, weights=weights,
                                     config=config, cancel=self.cancel_event)
            self.completed.emit(self.job, result, None)
        except Exception as exc:
            self.completed.emit(self.job, None, str(exc))


class AdaptiveController(AmateurController):
    play_kind = 'adaptive_ai'
    thread_type = AdaptiveThread
    config_type = staticmethod(lambda: adaptive.DEFAULT)

    def eligible(self):
        if not super().eligible() or not self.window.storage:
            return False
        current = self.window.storage.current
        state = current.learning if current else None
        return state is not None and state.revision == self.page.session.revision

    def job_config(self):
        return self.config, self.window.storage.current.learning.weights
