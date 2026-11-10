import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app


@pytest.fixture
def local_client(tmp_path):
    app = create_app(tmp_path / 'security.sqlite3', settings=Settings(llm_mode='mock', access_token=''))
    with TestClient(app, base_url='http://localhost') as client:
        yield client


@pytest.mark.parametrize('value', ['abc', '-1', '1.0', '+2'])
def test_reject_malformed_length(local_client, value):
    response = local_client.post('/api/events', content=b'{}', headers={'Content-Length': value})
    assert response.status_code == 400


def test_reject_rebinding_host_and_cross_origin(local_client):
    assert local_client.get('/api/pet/settings', headers={'Host': 'evil.example', 'Origin': 'http://evil.example'}).status_code == 403
    assert local_client.get('/api/pet/settings', headers={'Origin': 'http://evil.example'}).status_code == 403
    assert local_client.get('/api/pet/settings', headers={'Origin': 'https://localhost'}).status_code == 403
    assert local_client.get('/api/pet/settings', headers={'Origin': 'http://localhost'}).status_code == 200
    assert local_client.get('/api/pet/settings', headers={'Host': '[::1]:8000', 'Origin': 'http://[::1]:8000'}).status_code == 200


def test_auth_errors_do_not_expose_tokens(tmp_path):
    secret = 'private-test-access-key'
    app = create_app(tmp_path / 'auth.sqlite3', settings=Settings(llm_mode='mock', access_token=secret))
    with TestClient(app, base_url='http://localhost') as client:
        assert client.get('/api/pet/settings').status_code == 401
        response = client.get('/api/pet/settings', headers={'Authorization': 'Bearer wrong-private-key'})
        assert response.status_code == 401
        assert secret not in response.text and 'wrong-private-key' not in response.text
        assert client.get('/api/pet/settings', headers={'Authorization': 'Bearer ' + secret}).status_code == 200


def test_remote_peer_requires_configured_token():
    from backend.access import access_error
    scope = {'type': 'http', 'scheme': 'http', 'client': ('192.0.2.10', 123), 'headers': [(b'host', b'localhost')]}
    assert access_error(scope, '')[0] == 401
    assert access_error(scope, 'token')[0] == 401
    scope['headers'].append((b'authorization', b'Bearer token'))
    assert access_error(scope, 'token') is None


def test_explicit_lan_host_requires_token_and_rejects_unlisted_hosts(tmp_path):
    from backend.access import access_error
    allowed = ('localhost', '127.0.0.1', '::1', '192.168.1.20', 'pixelpet.local')
    scope = {'type': 'http', 'scheme': 'http', 'client': ('127.0.0.1', 123), 'headers': [(b'host', b'192.168.1.20:8000')]}
    assert access_error(scope, '', allowed)[0] == 401
    assert access_error(scope, 'lan-key', allowed)[0] == 401
    scope['headers'].append((b'authorization', b'Bearer lan-key'))
    assert access_error(scope, 'lan-key', allowed) is None
    scope['headers'][0] = (b'host', b'unlisted.local:8000')
    assert access_error(scope, 'lan-key', allowed)[0] == 403
    app = create_app(tmp_path / 'lan.sqlite3', settings=Settings(llm_mode='mock', access_token='lan-key', allowed_hosts=','.join(allowed)))
    with TestClient(app, base_url='http://192.168.1.20:8000') as client:
        assert client.get('/api/pet/settings').status_code == 401
        assert client.get('/api/pet/settings', headers={'Authorization': 'Bearer lan-key'}).status_code == 200
        with client.websocket_connect('/api/devices/ws', headers={'Authorization': 'Bearer lan-key'}) as socket:
            assert socket.receive_json()['type'] == 'device.connected'


@pytest.mark.parametrize('value', ['*', '*.local', 'http://localhost', 'localhost:8000', '192.168.0.0/16'])
def test_host_config_rejects_patterns_and_url_syntax(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Settings(allowed_hosts=value)


def test_mock_device_uses_environment_bearer_and_rejects_url_credentials():
    from scripts.mock_device import connection_options
    options = connection_options('ws://192.168.1.20:8000/api/devices/ws?device_id=mock', {'PIXELPET_ACCESS_TOKEN': 'private-key'})
    assert options['additional_headers'] == {'Authorization': 'Bearer private-key'}
    with pytest.raises(ValueError):
        connection_options('ws://localhost/api/devices/ws?token=private-key', {})


def test_limit_actual_streamed_body_without_content_length():
    from backend.access import LocalAccessMiddleware
    called = []
    async def endpoint(scope, receive, send):
        called.append(True)
    async def run():
        chunks = iter([{'type': 'http.request', 'body': b'x' * (6 * 1024 * 1024), 'more_body': True}, {'type': 'http.request', 'body': b'x' * (6 * 1024 * 1024), 'more_body': False}])
        async def receive():
            return next(chunks)
        sent = []
        async def send(value):
            sent.append(value)
        await LocalAccessMiddleware(endpoint, token='')({'type': 'http', 'path': '/api/events', 'scheme': 'http', 'client': ('127.0.0.1', 123), 'headers': [(b'host', b'localhost'), (b'transfer-encoding', b'chunked')]}, receive, send)
        assert sent[0]['status'] == 413
        assert called == []
    asyncio.run(run())


def test_saved_model_applied_on_startup_only_after_settings_saved(tmp_path):
    class Provider:
        mode = 'mock'
        model = 'environment-model'
        async def close(self):
            pass
    path = tmp_path / 'model.sqlite3'
    settings = Settings(llm_mode='mock', access_token='')
    first = Provider()
    with TestClient(create_app(path, settings=settings, provider=first), base_url='http://localhost') as client:
        assert first.model == 'environment-model'
        assert client.get('/api/pet/settings').status_code == 200
        assert first.model == 'environment-model'
        assert client.patch('/api/pet/settings', json={'llm_model': 'saved-model'}).status_code == 200
    second = Provider()
    with TestClient(create_app(path, settings=settings, provider=second), base_url='http://localhost'):
        assert second.model == 'saved-model'


def test_proactive_greetings_share_caps_and_survive_restart(tmp_path):
    from backend.database.engine import initialize_database
    from backend.preferences import PreferencesService, ReminderScheduler
    engine = initialize_database(tmp_path / 'proactive.sqlite3')
    try:
        service = PreferencesService(engine)
        scheduler = ReminderScheduler(service)
        now = datetime(2026, 11, 5, 1, tzinfo=timezone.utc)  # Shanghai 09:00
        assert scheduler.poll(now) == []
        service.update({'proactive_enabled': True, 'daily_limit': 2})
        first = scheduler.poll(now)
        assert len(first) == 1 and first[0]['type'] == 'proactive'
        assert ReminderScheduler(PreferencesService(engine)).poll(now + timedelta(minutes=1)) == []
        assert len(scheduler.poll(now + timedelta(hours=5))) == 1
        assert scheduler.poll(now + timedelta(hours=10)) == []
        assert service.is_quiet(now + timedelta(hours=14)) is True
        assert scheduler.poll(now + timedelta(hours=14)) == []
        service.update({'proactive_enabled': False})
        assert scheduler.poll(now + timedelta(days=1)) == []
    finally:
        engine.dispose()
