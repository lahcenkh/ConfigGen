"""Entry point: QApplication, login loop, window icon (§1, §16)."""

from __future__ import annotations

import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from configgen.appinfo import APP_NAME, __version__
from configgen.core.auth import AuthStore
from configgen.logging_setup import configure_logging
from configgen.paths import icon_path, schemas_dir, users_db_path
from configgen.ui import theme
from configgen.ui.login_window import LoginWindow
from configgen.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    log_file = configure_logging()
    logger.info("%s v%s starting (log file: %s)", APP_NAME, __version__, log_file)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    # Dark by default: there's no logged-in user yet to read a per-user
    # dark-mode preference from (that's keyed by username, §15), and the
    # login screen is the one surface every user sees regardless of their
    # eventual preference. MainWindow re-applies the real per-user choice
    # right after login, overriding this.
    app.setStyleSheet(theme.stylesheet(theme.DARK))

    icon_file = icon_path()
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))

    store = AuthStore(users_db_path())
    schemas_path = schemas_dir()

    # The login loop: LoginWindow itself re-prompts on a wrong password or
    # a locked account (the user never leaves the dialog for that) — this
    # loop only runs again if the dialog is dismissed without succeeding
    # (the user closed it, so there's no session to start) or if the
    # signed-in user clicks Log Out in the sidebar, which closes MainWindow
    # (ending this iteration's app.exec()) and sets `logout_requested` so
    # the loop reopens LoginWindow instead of returning.
    while True:
        login = LoginWindow(store)
        if login.exec() != QDialog.DialogCode.Accepted:
            logger.info("login dialog closed without signing in; exiting")
            return 0

        logger.info("user '%s' signed in", login.authenticated_user.username)
        window = MainWindow(login.authenticated_user, store, schemas_path)
        window.show()
        app.exec()
        if not window.logout_requested:
            logger.info("main window closed; exiting")
            return 0
        logger.info("user '%s' logged out; returning to login", login.authenticated_user.username)


if __name__ == "__main__":
    sys.exit(main())
