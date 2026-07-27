"""Entry point: QApplication, login loop, window icon (§1, §16)."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog

from configgen.appinfo import APP_NAME
from configgen.core.auth import AuthStore
from configgen.paths import icon_path, schemas_dir, users_db_path
from configgen.ui.login_window import LoginWindow
from configgen.ui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)

    icon_file = icon_path()
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))

    store = AuthStore(users_db_path())

    # The login loop: LoginWindow itself re-prompts on a wrong password or
    # a locked account (the user never leaves the dialog for that) — this
    # loop only runs again if the dialog is dismissed without succeeding,
    # which for a modal exec() means the user closed it, so there's no
    # session to start.
    login = LoginWindow(store)
    if login.exec() != QDialog.DialogCode.Accepted:
        return 0

    window = MainWindow(login.authenticated_user, store, schemas_dir())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
