from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config.settings import load_settings
from app.utils.logging_config import configure_logging
from app.views.main_window import MainWindow


def main() -> int:
    settings = load_settings()
    logger = configure_logging(settings.logs_dir, settings.log_level)
    logger.info("Application starting")

    app = QApplication(sys.argv)
    window = MainWindow(settings)
    window.show()
    exit_code = app.exec()

    logger.info("Application stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

