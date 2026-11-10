from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from backend.events import Event, EventBus
from backend.pet import PetEngine
from backend.devices import DeviceService, PinConfig
from backend.api.devices import router


def rig():
    bus = EventBus(capacity=4)
    pet = PetEngine(bus)
    return bus, pet, DeviceService(bus, pet)


def test_bounded_audit_excludes_arbitrary_payload():
    bus, _, _ = rig()
    for i in range(8):
        bus.publish(Event(type='device.error', payload={'text': 'SECRET', 'audio': 'PRIVATE', 'code': 'timeout'}))
    assert len(bus.history()) == 4
    assert 'SECRET' not in str(bus.history())
    assert 'PRIVATE' not in str(bus.history())


def test_recording_blocks_speech_haptic_and_duplicate_events():
    bus, pet, _ = rig()
    event = Event(type='touch.long_press')
    assert pet.handle_event(event)
    assert pet.snapshot()['state'] == 'LISTENING'
    assert pet.handle_event(event) == []
    assert pet.handle_event(Event(type='haptic.pattern', payload={'name':'short'})) == []
    assert pet.handle_event(Event(type='audio.speak_start')) == []
    pet.handle_event(Event(type='touch.touch_up'))
    assert pet.snapshot()['state'] == 'THINKING'
    pet.handle_event(Event(type='audio.speak_start'))
    assert pet.snapshot()['state'] == 'SPEAKING'
    assert pet.handle_event(Event(type='audio.record_start')) == []
    pet.handle_event(Event(type='audio.speak_end'))
    assert pet.snapshot()['state'] == 'IDLE'


def test_touch_debounce_long_release_and_mute():
    _, pet, _ = rig()
    pet.handle_event(Event(type='touch.touch_down'), now=0)
    assert pet.handle_event(Event(type='touch.touch_up'), now=.01) == []
    pet.handle_event(Event(type='clock.tick'), now=.9)
    assert not pet.snapshot()['recording']
    pet.handle_event(Event(type='touch.touch_down'), now=1)
    pet.handle_event(Event(type='clock.tick'), now=1.9)
    assert pet.snapshot()['recording']
    pet.handle_event(Event(type='touch.touch_up'), now=2)
    assert not pet.snapshot()['recording']
    pet.configure({'quiet_mode':True})
    effects = pet.handle_event(Event(type='touch.double_tap'), now=3)
    assert pet.snapshot()['state'] == 'SHY'
    assert not any(x['type'].startswith('haptic') for x in effects)


@pytest.mark.parametrize('name', ['short','double','long'])
def test_haptics_bounded(name):
    _, pet, _ = rig()
    pet.configure({'haptic_strength':99})
    effects=pet.handle_event(Event(type='haptic.pattern',payload={'name':name}))
    assert effects[0]['payload']['strength'] == 1
    assert effects[0]['payload']['simulated'] is True


def test_pin_config_refuses_unapproved_conflicting_reserved_pins():
    assert PinConfig().status == 'HW_PENDING'
    for pins, approved in [({'touch':4},False),({'touch':4,'motor':4},True),({'touch':26},True),({'touch':99},True)]:
        with pytest.raises(ValueError):
            PinConfig(pins=pins, hardware_approved=approved)
    assert PinConfig(pins={'touch':4},hardware_approved=True).pins['touch'] == 4


def test_heartbeat_timeout_and_reconnect():
    _, _, devices = rig()
    devices.connect('mock-1',now=0)
    devices.heartbeat('mock-1',now=4)
    assert devices.expire(now=10) == []
    assert devices.expire(now=40) == ['mock-1']
    devices.connect('mock-1',now=41)
    assert devices.status()[0]['connected']


def client():
    bus,pet,devices=rig()
    app=FastAPI()
    app.state.event_bus=bus
    app.state.pet_engine=pet
    app.state.devices=devices
    app.include_router(router)
    return TestClient(app)


def test_websocket_business_protocol_lifecycle():
    with client() as c:
        for _ in range(2):
            with c.websocket_connect('/api/devices/ws?device_id=mock-1') as ws:
                assert ws.receive_json()['type']=='device.connected'
                for kind in ['hello','heartbeat','audio.record_start','audio.record_stop','response']:
                    ws.send_json({'version':1,'type':kind,'payload':{}})
                    ack=ws.receive_json()
                    assert ack['type']=='ack'
                    assert ack['payload']['received']==kind
            assert not c.get('/api/devices').json()['devices'][0]['connected']
        assert c.post('/api/events',json={'type':'touch.tap'}).status_code==200
        assert c.post('/api/events',json={'type':'made.up'}).status_code==422

def test_event_bus_subscribers_receive_typed_event_but_audit_remains_metadata():
    bus,_,_=rig()
    received=[]
    unsubscribe=bus.subscribe(received.append)
    bus.publish(Event(type='touch.tap'))
    unsubscribe()
    bus.publish(Event(type='touch.tap'))
    assert len(received)==1
    assert isinstance(received[0],Event)


def test_invalid_large_event_payload_is_rejected():
    with pytest.raises(ValueError):
        Event(type='touch.tap',payload={'text':'a'*17000})


def test_disconnected_physical_device_cannot_start_speaking():
    _,pet,devices=rig()
    assert pet.handle_event(Event(type='audio.speak_start',device_id='esp32-real'))==[]
    devices.connect('esp32-real')
    assert pet.handle_event(Event(type='audio.speak_start',device_id='esp32-real'))
    devices.disconnect('esp32-real')
    assert not pet.snapshot()['speaking']

@pytest.mark.parametrize('payload',[{'duration_ms':'bad'},{'strength':'bad'},{'strength':float('nan')},{'strength':float('inf')}])
def test_haptic_numeric_payload_validation(payload):
    with pytest.raises(ValueError):
        Event(type='haptic.pulse',payload=payload)


def test_haptics_alias_disables_effects():
    _,pet,_=rig()
    pet.configure({'haptics':False})
    assert pet.handle_event(Event(type='haptic.pattern',payload={'name':'long'}))==[]


def test_websocket_requires_configured_token():
    c=client()
    c.app.state.access_token='test-only-token'
    with c:
        with pytest.raises(Exception):
            with c.websocket_connect('/api/devices/ws?device_id=mock-1') as ws:
                ws.receive_json()
        with c.websocket_connect('/api/devices/ws?device_id=mock-1',headers={'Authorization':'Bearer test-only-token'}) as ws:
            assert ws.receive_json()['type']=='device.connected'


def test_websocket_binary_audio_is_explicitly_unsupported():
    from starlette.websockets import WebSocketDisconnect
    with client() as c:
        with c.websocket_connect('/api/devices/ws?device_id=mock-1') as ws:
            ws.receive_json()
            ws.send_bytes(b'not-opus')
            with pytest.raises(WebSocketDisconnect) as error:
                ws.receive_json()
            assert error.value.code==1003

def test_raw_release_waits_for_classified_gesture_without_double_haptic():
    _,pet,_=rig()
    pet.handle_event(Event(type='touch.touch_down'),now=0)
    assert pet.handle_event(Event(type='touch.touch_up'),now=.15)==[]
    effects=pet.handle_event(Event(type='touch.tap'),now=.16)
    assert len([e for e in effects if e['type']=='haptic.pattern'])==1
    assert pet.snapshot()['state']=='HAPPY'


def test_debounced_release_cancels_hold_instead_of_ghost_recording():
    _,pet,_=rig()
    pet.handle_event(Event(type='touch.touch_down'),now=0)
    pet.handle_event(Event(type='touch.touch_up'),now=.01)
    pet.handle_event(Event(type='clock.tick'),now=1)
    assert not pet.snapshot()['recording']


def test_runtime_preferences_quiet_changes_apply_without_settings_patch():
    class Preferences:
        quiet=False
        def is_quiet(self): return self.quiet
    _,pet,_=rig()
    pet.preferences=Preferences()
    assert pet.handle_event(Event(type='haptic.pattern'))
    pet.preferences.quiet=True
    assert pet.handle_event(Event(type='haptic.pattern'))==[]


def test_duplicate_event_is_atomic_between_threads():
    from concurrent.futures import ThreadPoolExecutor
    _,pet,_=rig()
    event=Event(type='haptic.pattern')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:pet.handle_event(event),range(32)))
    assert len([r for r in results if r])==1


@pytest.mark.parametrize('headers',[{'Host':'evil.example'},{'Origin':'https://evil.example'},{'Authorization':'Bearer invalid'}])
def test_websocket_rejects_untrusted_host_origin_or_token(headers):
    from starlette.websockets import WebSocketDisconnect
    c=client()
    c.app.state.access_token='test-only-token'
    with c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/api/devices/ws',headers=headers) as ws:
                ws.receive_json()


def test_websocket_query_token_is_not_accepted():
    from starlette.websockets import WebSocketDisconnect
    c=client()
    c.app.state.access_token='test-only-token'
    with c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/api/devices/ws?token=test-only-token') as ws:
                ws.receive_json()

def test_websocket_denies_remote_peer_without_configured_token():
    from starlette.websockets import WebSocketDisconnect
    app=client().app
    with TestClient(app,base_url='http://127.0.0.1',client=('192.168.1.20',12345)) as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/api/devices/ws') as ws:
                ws.receive_json()


@pytest.mark.parametrize('headers',[{'Host':'evil.example'},{'Origin':'http://evil.example'},{'Origin':'https://testserver'}])
def test_websocket_valid_token_does_not_bypass_host_origin_guards(headers):
    from starlette.websockets import WebSocketDisconnect
    c=client()
    c.app.state.access_token='test-only-token'
    headers={'Authorization':'Bearer test-only-token',**headers}
    with c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/api/devices/ws',headers=headers) as ws:
                ws.receive_json()
