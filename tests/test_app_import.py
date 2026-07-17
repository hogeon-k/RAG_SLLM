from app.config.settings import load_settings
from app.main import main
from app.views.main_window import MainWindow


def test_core_imports() -> None:
    assert callable(main)
    assert MainWindow.MENU_LABELS == ("질의응답", "문서 관리", "질문 이력", "시스템 설정")


def test_settings_create_directories(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "app_data"))

    settings = load_settings()

    assert settings.data_dir.exists()
    assert settings.uploads_dir.exists()
    assert settings.vector_db_dir.exists()
    assert settings.database_dir.exists()

