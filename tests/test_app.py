"""Stage-one acceptance tests use disposable databases under the D-drive tmp folder."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from backend.main import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(database_path=tmp_path / "pet.sqlite3")


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def test_health_and_schema(client, app):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "mode": "simulator", "phase": 1}
    assert set(inspect(app.state.engine).get_table_names()) == {
        "user_profile", "conversations", "messages", "memories", "pet_settings"
    }


def test_database_survives_restart(tmp_path):
    path = tmp_path / "persistent.sqlite3"
    first = create_app(database_path=path)
    with TestClient(first):
        with first.state.engine.begin() as conn:
            conn.execute(text("INSERT INTO user_profile (id, display_name) VALUES ('owner', '主人')"))
    second = create_app(database_path=path)
    with TestClient(second):
        with second.state.engine.connect() as conn:
            assert conn.execute(text("SELECT display_name FROM user_profile WHERE id='owner'")).scalar() == "主人"


def test_health_does_not_expose_database_errors(client, app, monkeypatch):
    def unavailable():
        raise OperationalError("secret path", {}, Exception("private detail"))
    monkeypatch.setattr(app.state.engine, "connect", unavailable)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"
    assert "private" not in response.text


def test_static_assets(client):
    assert "小星" in client.get("/").text
    for path in ("/static/css/style.css", "/static/js/pet.js", "/static/js/app.js"):
        assert client.get(path).status_code == 200


def test_initial_state(client):
    state = client.get("/api/pet/state").json()
    assert state["state"] == "IDLE"
    assert state["emotion"] == "normal"
    assert state["recording"] is False
    assert state["wifi_connected"] is False
    assert state["ble_connected"] is False


@pytest.mark.parametrize("event,state,emotion", [
    ("touch_start", "HAPPY", "happy"),
    ("touch_end", "IDLE", "normal"),
    ("audio_start", "LISTENING", "curious"),
    ("audio_end", "THINKING", "thinking"),
    ("audio_play", "SPEAKING", "happy"),
    ("wifi_connected", "IDLE", "normal"),
    ("ble_connected", "IDLE", "normal"),
])
def test_hardware_events(client, event, state, emotion):
    response = client.post("/api/simulator/events", json={"event": event})
    assert response.status_code == 200
    assert response.json()["state"] == state
    assert response.json()["emotion"] == emotion
    assert response.json()["last_event"] == event


def test_recording_and_connectivity(client):
    assert client.post("/api/simulator/events", json={"event": "audio_start"}).json()["recording"]
    assert not client.post("/api/simulator/events", json={"event": "audio_end"}).json()["recording"]
    client.post("/api/simulator/events", json={"event": "wifi_connected"})
    state = client.post("/api/simulator/events", json={"event": "ble_connected"}).json()
    assert state["wifi_connected"] and state["ble_connected"]


@pytest.mark.parametrize("state", ["IDLE", "HAPPY", "LISTENING", "THINKING", "SPEAKING", "SHY", "SLEEP", "SURPRISED"])
def test_preview(client, state):
    response = client.post("/api/simulator/preview", json={"state": state})
    assert response.status_code == 200
    assert response.json()["state"] == state


@pytest.mark.parametrize("path,payload", [
    ("events", {"event": "gpio_write"}), ("events", {}),
    ("events", {"event": "touch_start", "pin": 5}),
    ("preview", {"state": "INVALID"}),
])
def test_invalid_input_rejected(client, path, payload):
    assert client.post(f"/api/simulator/{path}", json=payload).status_code == 422


def test_apps_do_not_share_pet_state(client, tmp_path):
    client.post("/api/simulator/events", json={"event": "audio_start"})
    with TestClient(create_app(database_path=tmp_path / "other.sqlite3")) as other:
        assert other.get("/api/pet/state").json()["recording"] is False


def test_foreign_keys_enabled(client, app):
    with app.state.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
