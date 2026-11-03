"""Start the NeuroChess desktop application."""

import sys

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


class NeuroChessApplication(QApplication):
    """Route application-level macOS Quit through the durable close handshake."""
    window=None

    def event(self,event):
        if event.type()==QEvent.Type.Quit and self.window is not None and not self.window._allow_close:
            self.window.close();return True
        return super().event(event)


def main() -> int:
    """Show the start window and return Qt's exit code."""
    app = NeuroChessApplication(sys.argv)
    app.setApplicationName("NeuroChess")
    app.setOrganizationName("NeuroChess")
    app.setQuitOnLastWindowClosed(True)
    window = MainWindow()
    app.window=window
    window.show()
    result = app.exec()
    # Dispose the scene, renderers and queued animations while Qt still exists.
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return result


if __name__ == "__main__":
    sys.exit(main())
