def test_import_fastapi_app():
    from arion_agents.api import app

    assert app.title == "arion_agents API"
