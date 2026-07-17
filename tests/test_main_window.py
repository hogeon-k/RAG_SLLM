from PySide6.QtCore import Qt

from app.config.settings import Settings
from app.views.main_window import MainWindow


def test_main_window_creation(qtbot, tmp_path) -> None:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
    )
    settings.ensure_directories()

    window = MainWindow(settings)
    qtbot.addWidget(window)

    assert window.windowTitle() == "업무 RAG 규정 검색"
    assert window.sidebar.count() == 4
    assert window.stack.count() == 4
    assert window.stack.currentIndex() == 0


def test_sidebar_switches_stacked_widget(qtbot, tmp_path) -> None:
    settings = Settings(
        app_env="test",
        data_dir=tmp_path / "data",
        log_level="INFO",
        ollama_host="http://127.0.0.1:11434",
    )
    settings.ensure_directories()

    window = MainWindow(settings)
    qtbot.addWidget(window)

    item = window.sidebar.item(2)
    window.sidebar.setCurrentItem(item)
    qtbot.mouseClick(window.sidebar.viewport(), Qt.MouseButton.LeftButton)

    assert window.stack.currentIndex() == 2
