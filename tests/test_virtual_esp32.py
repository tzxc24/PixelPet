from tests.test_devices import client
from scripts.virtual_esp32 import DeviceEvent, VirtualESP32


def send(ws, kind, seq=None, payload=None):
    frame = {'version': 1, 'type': kind, 'payload': payload or {}}
    if seq is not None:
        frame['seq'] = seq
    ws.send_json(frame)
    return ws.receive_json()


def test_sequenced_session_rejects_replay_and_resynchronizes():
    with client() as http:
        url = '/api/devices/ws?device_id=virtual-test'
        with http.websocket_connect(url) as ws:
            assert ws.receive_json()['type'] == 'device.connected'
            assert send(ws, 'hello', 1)['seq'] == 1
            ack = send(ws, 'RECORD_START', 2)
            assert ack['pet']['state'] == 'LISTENING'
            replay = send(ws, 'RECORD_STOP', 2)
            assert replay['payload']['code'] == 'invalid_sequence'
            assert replay['payload']['expected_seq'] == 3
            assert send(ws, 'heartbeat')['type'] == 'error'
            assert send(ws, 'RECORD_STOP', 3)['pet']['state'] == 'THINKING'
        with http.websocket_connect(url) as ws:
            ws.receive_json()
            assert send(ws, 'hello', 1)['pet']['state'] == 'IDLE'
            presence = http.get('/api/devices').json()['devices'][0]
            assert presence['connected'] and presence['reconnect_count'] == 1


def test_control_aliases_and_sanitized_error():
    with client() as http, http.websocket_connect('/api/devices/ws') as ws:
        ws.receive_json()
        send(ws, 'hello', 1)
        assert send(ws, 'TOUCH_SHORT', 2)['pet']['state'] == 'HAPPY'
        assert send(ws, 'TOUCH_LONG', 3)['pet']['state'] == 'LISTENING'
        assert send(ws, 'AUDIO_PLAY_START', 4)['pet']['state'] == 'LISTENING'
        assert send(ws, 'TOUCH_END', 5)['pet']['state'] == 'THINKING'
        assert send(ws, 'AUDIO_PLAY_START', 6)['pet']['state'] == 'SPEAKING'
        assert send(ws, 'AUDIO_PLAY_END', 7)['pet']['state'] == 'IDLE'
        assert send(ws, 'DISPLAY_EMOTION', 8, {'emotion': 'sad'})['pet']['state'] == 'IDLE'
        assert send(ws, 'DISPLAY_EMOTION', 9, {'emotion': 'shy'})['pet']['state'] == 'SHY'
        assert send(ws, 'HAPTIC_SHORT', 10)['effects'][0]['payload']['name'] == 'short'
        assert send(ws, 'HAPTIC_DOUBLE', 11)['effects'][0]['payload']['name'] == 'double'
        error = send(ws, 'DISPLAY_EMOTION', 12, {'emotion': 'private-input'})
        assert error == {'version': 1, 'type': 'error', 'seq': 12, 'payload': {'code': 'invalid_event'}}


def test_stale_socket_cannot_disconnect_reconnected_device():
    from tests.test_devices import rig
    _, _, service = rig()
    original = service.connect('virtual-test', now=0)
    assert service.connect('virtual-test', now=1) is None
    assert service.expire(now=31) == ['virtual-test']
    replacement = service.connect('virtual-test', now=32)
    service.disconnect('virtual-test', generation=original)
    assert service.status()[0]['connected']
    service.disconnect('virtual-test', generation=replacement)
    assert not service.status()[0]['connected']


def test_unrelated_device_cannot_release_browser_capture():
    with client() as http:
        http.post('/api/events', json={'type': 'audio.record_start', 'device_id': 'browser-pixelpet'}).raise_for_status()
        with http.websocket_connect('/api/devices/ws?device_id=virtual-unrelated') as ws:
            ws.receive_json()
            send(ws, 'hello', 1)
            assert send(ws, 'TOUCH_END', 2)['pet']['recording']
            assert send(ws, 'RECORD_STOP', 3)['pet']['recording']
            assert send(ws, 'AUDIO_PLAY_END', 4)['pet']['state'] == 'LISTENING'
        assert http.get('/api/events/status').json()['pet']['recording']
        stop = http.post('/api/events', json={'type': 'audio.record_stop', 'device_id': 'browser-pixelpet'}).json()
        assert not stop['pet']['recording'] and stop['pet']['state'] == 'THINKING'


def test_virtual_client_on_real_loopback_reconnects_after_heartbeat_timeout(tmp_path, monkeypatch):
    import socket
    from contextlib import asynccontextmanager
    from threading import Thread
    from time import monotonic, sleep
    import httpx
    import uvicorn
    from backend.core.config import Settings
    from backend.main import create_app

    monkeypatch.delenv('PIXELPET_ACCESS_TOKEN', raising=False)
    app = create_app(database_path=tmp_path / 'device.sqlite3',
                     settings=Settings(_env_file=None, llm_mode='mock', access_token=''))
    lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def short_heartbeat(app):
        async with lifespan(app):
            # This test asserts pulses, so it must not depend on the wall clock
            # entering the default 22:00-08:00 quiet interval.
            app.state.preferences.update({'quiet_start':'00:00','quiet_end':'00:00'})
            app.state.devices.heartbeat_timeout = .8
            yield

    app.router.lifespan_context = short_heartbeat
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        thread = Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()
        device = VirtualESP32(f'ws://127.0.0.1:{port}/api/devices/ws?device_id=virtual-real-test')
        try:
            limit = monotonic() + 5
            while not server.started and monotonic() < limit:
                sleep(.02)
            assert server.started
            device.connect()
            trace = device.demo()
            assert trace['TOUCH_SHORT'] == 'HAPPY'
            assert trace['TOUCH_LONG'] == trace['RECORD_START'] == 'LISTENING'
            assert trace['RECORD_STOP'] == 'THINKING'
            assert trace['AUDIO_PLAY_START'] == 'SPEAKING'
            assert trace['AUDIO_PLAY_END'] == 'IDLE'
            assert trace['DISPLAY_EMOTION'] == 'SHY'
            assert device.state.motor_pulses[-4:] == [70, 60, 60, 60]
            for emotion, display in (
                ('normal', 'IDLE'), ('happy', 'HAPPY'), ('shy', 'SHY'),
                ('sad', 'IDLE'), ('angry', 'ANNOYED'), ('curious', 'SURPRISED'),
                ('thinking', 'THINKING'), ('sleepy', 'SLEEP'), ('surprised', 'SURPRISED'),
            ):
                device.send(DeviceEvent.DISPLAY_EMOTION, emotion=emotion)
                assert (device.state.emotion, device.state.display) == (emotion, display)
            device.watch(1)
            assert device.state.reconnects == 0
            sleep(1)
            presence = httpx.get(f'http://127.0.0.1:{port}/api/devices').json()['devices'][0]
            assert not presence['connected']
            assert device.heartbeat()['pet']['state'] == 'IDLE'
            assert device.state.reconnects == 1
            device.send(DeviceEvent.RECORD_START)
            assert device.state.recording and not device.state.playing
            device.disconnect()
            assert device.state.wifi == 'DISCONNECTED'
            assert not device.state.recording
        finally:
            device.disconnect()
            server.should_exit = True
            thread.join(5)
            assert not thread.is_alive()
