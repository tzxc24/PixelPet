from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect

from backend.database.engine import initialize_database
from backend.database.store import Store


@pytest.fixture
def engine(tmp_path):
    value = initialize_database(tmp_path / 'preferences.sqlite3')
    yield value
    value.dispose()


def test_preferences_validate_and_survive_restart(engine):
    from backend.preferences import PreferencesService
    preferences = PreferencesService(engine)
    assert preferences.get().name == '小星'
    assert preferences.get().proactive_enabled is False
    preferences.update({'name': '团子', 'volume': 0.4, 'time_format': '12'})
    assert PreferencesService(engine).get().name == '团子'
    assert PreferencesService(engine).get().volume == 0.4
    for change in ({'volume': 2}, {'rate': 0}, {'quiet_start': '25:00'}, {'time_zone': 'Invalid/Zone'}, {'llm_api_key': 'secret'}, {'tts_provider': 'cloud'}):
        with pytest.raises(ValidationError):
            preferences.update(change)
    assert preferences.get().volume == 0.4
    assert len(inspect(engine).get_table_names()) == 5


def test_reminders_defer_expire_and_never_repeat_after_restart(engine):
    from backend.preferences import PreferencesService, ReminderScheduler
    preferences = PreferencesService(engine)
    scheduler = ReminderScheduler(preferences)
    now = datetime(2026, 11, 5, 1, tzinfo=timezone.utc)  # Shanghai 09:00
    reminder = scheduler.create('喝水', now - timedelta(minutes=1))
    assert [r['id'] for r in scheduler.poll(now)] == [reminder['id']]
    assert ReminderScheduler(PreferencesService(engine)).poll(now) == []
    assert scheduler.list()[0]['delivered'] is True
    assert scheduler.delete(reminder['id']) is True
    assert scheduler.delete(reminder['id']) is False
    scheduler.create('过期', now - timedelta(days=2))
    assert scheduler.poll(now) == []
    assert scheduler.list()[0]['status'] == 'expired'
    with pytest.raises(ValidationError):
        scheduler.create('无时区', datetime(2026, 11, 5))


def test_reminders_quiet_hours_and_daily_limit(engine):
    from backend.preferences import PreferencesService, ReminderScheduler
    preferences = PreferencesService(engine)
    preferences.update({'daily_limit': 1})
    scheduler = ReminderScheduler(preferences)
    quiet = datetime(2026, 11, 4, 23, tzinfo=timezone.utc)  # 07:00
    scheduler.create('早餐', quiet)
    scheduler.create('散步', quiet)
    assert scheduler.poll(quiet) == []
    awake = quiet + timedelta(hours=2)
    assert len(scheduler.poll(awake)) == 1
    assert scheduler.poll(awake) == []
    assert sum(r['status'] == 'pending' for r in scheduler.list()) == 1


def test_api_settings_memory_export_clear_and_busy(engine):
    from backend.preferences import PreferencesService, ReminderScheduler
    from backend.api.preferences import router
    app = FastAPI()
    app.state.preferences = PreferencesService(engine)
    app.state.scheduler = ReminderScheduler(app.state.preferences)
    app.state.store = Store(engine)
    app.state.chat = type('Chat', (), {'active': set()})()
    configured = []
    app.state.pet_engine = type('Pet', (), {'configure': lambda self, value: configured.append(value)})()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.patch('/api/pet/settings', json={'name': '团子'}).status_code == 200
        assert configured[-1]['name'] == '团子'
        assert client.patch('/api/pet/settings', json={'volume': 9}).status_code == 422
        store = app.state.store
        store.upsert_memory('basic', '主人叫小明')
        export = client.get('/api/memories/export')
        assert export.status_code == 200
        assert 'attachment' in export.headers['content-disposition']
        assert export.json()['memories'][0]['content'] == '主人叫小明'
        app.state.chat.active.add('busy')
        assert client.delete('/api/memories').status_code == 409
        app.state.chat.active.clear()
        assert client.delete('/api/memories').status_code == 200
        assert store.memories() == []
        assert store.profile()['display_name'] == '主人'
        assert client.get('/api/pet/settings').json()['name'] == '团子'
        assert client.get('/api/notifications/poll').json() == []
        due = datetime.now(timezone.utc) + timedelta(hours=1)
        result = client.post('/api/reminders', json={'text': '测试', 'due_at': due.isoformat()})
        assert result.status_code == 201
        assert client.get('/api/reminders').json()[0]['text'] == '测试'
        assert client.delete('/api/reminders/' + result.json()['id']).status_code == 200


def test_sqlite_backup_restricts_destination_and_preserves_data(tmp_path):
    from scripts.backup import backup_database
    source = tmp_path / 'source.sqlite3'
    with sqlite3.connect(source) as db:
        db.execute('create table sample (value text)')
        db.execute("insert into sample values ('hello')")
    root = tmp_path / 'project'
    target = root / 'output' / 'backups' / 'test.sqlite3'
    assert backup_database(source, target, project_root=root) == target
    with sqlite3.connect(target) as db:
        assert db.execute('select value from sample').fetchone()[0] == 'hello'
    with pytest.raises(FileExistsError):
        backup_database(source, target, project_root=root)
    with pytest.raises(ValueError):
        backup_database(source, tmp_path / 'elsewhere.sqlite3', project_root=root)
