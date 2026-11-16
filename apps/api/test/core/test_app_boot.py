"""The API composition root must import before any user request is served."""


def test_api_application_imports():
    from app.main import app

    assert app.title
    assert any(getattr(route, "path", None) == "/health" for route in app.routes)
