from datetime import datetime, timedelta, timezone

from backend.preferences.scheduler import ReminderScheduler, parse_voice_reminder


def test_voice_reminder_parses_duration_and_content():
    assert parse_voice_reminder('五分钟之后提醒我喝水。') == (5, '喝水')
    assert parse_voice_reminder('小星，12分钟后叫我。') == (12, '')
    assert parse_voice_reminder('明天九点开会') is None
    assert parse_voice_reminder('如果五分钟后提醒我会怎样') is None
    assert parse_voice_reminder('五分钟后提醒我吗？') is None


def test_voice_reminder_waits_for_its_device_and_ack(tmp_path):
    from backend.preferences.service import PreferencesService
    from backend.database.engine import initialize_database
    engine = initialize_database(tmp_path / "reminder.sqlite3")
    scheduler = ReminderScheduler(PreferencesService(engine))
    now = datetime.now(timezone.utc)
    item = scheduler.create('喝水', now + timedelta(minutes=5), device_id='desk')
    assert scheduler.next_device_reminder('desk', now) is None
    due = now + timedelta(minutes=5)
    assert scheduler.poll(due) == []
    assert scheduler.next_device_reminder('other', due) is None
    assert scheduler.next_device_reminder('desk', due)['id'] == item['id']
    assert not scheduler.ack_device_reminder('other', item['id'], due)
    assert scheduler.ack_device_reminder('desk', item['id'], due)
    assert scheduler.next_device_reminder('desk', due) is None



def test_voice_socket_creates_and_delivers_reminder(tmp_path):
    from fastapi.testclient import TestClient
    from backend.core.config import Settings
    from backend.main import create_app
    from scripts.virtual_esp32_voice import VirtualESP32Voice
    from test_virtual_voice import TestTransport

    app = create_app(database_path=tmp_path / 'voice.sqlite3', settings=Settings(llm_mode='mock'))

    async def transcript(*args, **kwargs):
        return {'text': '五分钟之后提醒我喝水', 'elapsed_ms': 1}

    with TestClient(app) as http:
        app.state.speech.transcribe = transcript
        http.patch('/api/pet/settings', json={'tts_provider': 'mock'}).raise_for_status()
        with http.websocket_connect('/api/devices/voice/ws?device_id=reminder-test') as ws:
            transport = TestTransport(ws)
            client = VirtualESP32Voice(transport)
            client.send('hello', reminders=True)
            client.control('hello')
            reply, _ = client.turn(b'\\x03\\x00' * 8000)
            assert reply['text'] == '好，5分钟后提醒你。'
            item, = app.state.scheduler.list()
            assert item['text'] == '喝水' and item['device_id'] == 'reminder-test'
            client.send('reminder.poll')
            client.control('reminder.none')

            def make_due(state):
                state['items'][0]['due_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            app.state.scheduler._mutate(make_due)

            client.send('reminder.poll')
            rid = client.control('reminder.ready')['session_id']
            client.send('reminder.play', session_id=rid)
            playback = client.control('playback.start')
            assert playback['session_id'] == rid
            count = 0
            while count < playback['byte_count']:
                frame = transport.recv()
                assert isinstance(frame, bytes)
                count += len(frame) - 20
            assert count == playback['byte_count']
            client.control('playback.end')
            assert app.state.scheduler.list()[0]['status'] == 'pending'
            client.send('reminder.ack', session_id=rid)
            client.control('reminder.ack')
            assert app.state.scheduler.list()[0]['status'] == 'delivered'
