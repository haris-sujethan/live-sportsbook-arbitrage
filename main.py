"""
main.py: Entry point for the Arb Overlay.

Shows a setup dialog on launch (book selection + bet size),
then starts the PyQt5 overlay and background worker thread.
The worker listens on localhost:8765 for data from the Chrome extension.
"""

import sys
from PyQt5.QtWidgets import QApplication
from setup import SetupDialog
from gui import ArbOverlay
from worker import WorkerThread


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Arb Scanner')
    app.setQuitOnLastWindowClosed(True)

    dialog = SetupDialog()
    screen = QApplication.desktop().availableGeometry()
    dialog.adjustSize()
    dialog.move(
        screen.width()  // 2 - dialog.width()  // 2,
        screen.height() // 2 - dialog.height() // 2,
    )

    if dialog.exec_() != SetupDialog.Accepted or not dialog.result_config:
        sys.exit(0)

    config = dialog.result_config   # {'books': [...], 'total_stake': float}

    overlay = ArbOverlay(config)
    overlay.show()

    worker = WorkerThread(config)
    worker.update.connect(overlay.on_update)
    worker.start()

    def on_quit():
        worker.stop()
        worker.quit()
        worker.wait(4000)

    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
