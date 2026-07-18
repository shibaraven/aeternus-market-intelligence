import importlib

import pytest


@pytest.fixture(scope="module")
def app_module():
    return importlib.import_module("app")


@pytest.fixture()
def client(app_module):
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_public_config_never_exposes_api_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret-that-must-not-leak")
    response = client.get("/api/research/config")
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["openai_configured"] is True
    assert payload["model"] == "gpt-5.6-sol"
    assert "test-secret" not in response.get_data(as_text=True)
    assert "api_key" not in payload


def test_demo_mode_completes_without_api_or_market_credentials(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/research/run",
        json={
            "symbol": "AET-DEMO",
            "market": "demo",
            "period": "1y",
            "question": "Assess momentum, risk, and strategy evidence in this synthetic scenario.",
            "demo_mode": True,
            "prefer_gpt": True,
        },
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["gpt_used"] is False
    assert payload["data_mode"] == "synthetic_demo"
    assert len(payload["tool_timeline"]) == 7
    assert len(payload["evidence_catalog"]) >= 30
    assert "SYNTHETIC DEMO" in payload["demo_indicator"]
    assert "research and educational" in payload["disclaimer"]


def test_live_mode_requires_server_side_api_key_before_network(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/api/research/run",
        json={
            "symbol": "7203.T",
            "market": "japan",
            "period": "1y",
            "question": "Assess technical, fundamental, risk, and historical strategy evidence.",
            "demo_mode": False,
        },
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "missing_api_key"


def test_invalid_symbol_and_invalid_json_errors(client):
    invalid_symbol = client.post(
        "/api/research/run",
        json={
            "symbol": "7203.TW",
            "market": "japan",
            "period": "1y",
            "question": "Assess technical, fundamental, risk, and historical strategy evidence.",
        },
    )
    assert invalid_symbol.status_code == 400
    assert invalid_symbol.get_json()["error"]["code"] == "invalid_request"

    invalid_json = client.post(
        "/api/research/run",
        data="not-json",
        content_type="text/plain",
    )
    assert invalid_json.status_code == 400
    assert invalid_json.get_json()["error"]["code"] == "invalid_json"


def test_research_ui_and_existing_routes_remain_available(client):
    homepage = client.get("/")
    html = homepage.get_data(as_text=True)
    assert homepage.status_code == 200
    assert "AI Research" in html
    assert "function openResearchPage" in html
    assert "SYNTHETIC DEMO" in html
    assert client.get("/api/health").status_code == 200
