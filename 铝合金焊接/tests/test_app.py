from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "离线铝合金焊接工艺推荐智能体"
    app.button[0].click().run(timeout=15)
    assert not app.exception
    assert len(app.tabs) == 4
