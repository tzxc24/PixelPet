import pytest
from datetime import datetime, timedelta, timezone
from backend.devices.home import HomeControl
from backend.database.engine import initialize_database
from backend.preferences.service import PreferencesService


@pytest.fixture
def home(tmp_path):
    engine=initialize_database(tmp_path/"home.sqlite")
    yield HomeControl(PreferencesService(engine),"assets/music")
    engine.dispose()


def test_voice_and_persistent_targets(home):
    assert home.voice("desk","开灯")
    assert home.snapshot()["devices"]["desk"]["lamp"]["level"]==100
    assert home.voice("desk","亮度调到百分之五十")
    assert home.snapshot()["devices"]["desk"]["lamp"]["level"]==50
    assert home.voice("desk","如果开灯会怎样") is None
    assert home.voice("desk","十分钟后播放起床旋律并开灯")
    assert len(home.snapshot()["alarms"])==1
    assert home.voice("desk","明天早上七点播放音乐")
    assert home.voice("desk","今天25点播放音乐")=="这个时间不正确，请重新说。"


def test_alarm_device_scope_and_ack(home):
    due=datetime.now(timezone.utc)+timedelta(minutes=1)
    alarm=home.create(dict(device_id="desk",due_at=due,track="wakeup",wake_light=True))
    assert not home.poll("other",due).get("music")
    assert not home.poll("desk",due-timedelta(seconds=1)).get("music")
    result=home.poll("desk",due)
    assert result["music"]["id"]==alarm["id"]
    assert result["lamp"]["mode"]=="fade"
    assert home.claim("other",alarm["id"]) is None
    assert home.claim("desk",alarm["id"])=="wakeup"
    assert home.claim("desk",alarm["id"]) is None
    assert home.playing("desk",alarm["id"])
    assert home.audio("wakeup", alarm["id"]).duration == 10
    home.finish("desk",alarm["id"])
    assert home.snapshot()["alarms"][0]["status"]=="delivered"
    home.finish("desk",alarm["id"])
    assert not home.poll("desk",due).get("music")


def test_music_stop_and_audio(home):
    home.queue("desk","morning")
    item=home.poll("desk")["music"]
    assert home.claim("desk",item["id"])=="morning"
    home.stop("desk")
    assert not home.playing("desk",item["id"])
    home.finish("desk",item["id"])
    for track in ("morning","wakeup","sunbeam"):
        audio=home.audio(track)
        assert audio.sample_rate==24000 and audio.channels==1
        assert 4<audio.duration<10


def test_offline_expiry(home):
    due=datetime.now(timezone.utc)+timedelta(minutes=1)
    home.create(dict(device_id="desk",due_at=due))
    assert not home.poll("desk",due+timedelta(minutes=11)).get("music")
    assert home.snapshot()["alarms"][0]["status"]=="expired"


def test_home_voice_music_protocol(tmp_path):
    from fastapi.testclient import TestClient
    from backend.main import create_app
    from backend.core.config import Settings
    from scripts.virtual_esp32_voice import VirtualESP32Voice
    from test_virtual_voice import TestTransport

    app=create_app(database_path=tmp_path/"voice.sqlite",settings=Settings(llm_mode="mock"))
    async def transcript(*args,**kwargs):
        return {"text":"小心，开灯","elapsed_ms":1}
    with TestClient(app) as http:
        app.state.speech.transcribe=transcript
        http.patch("/api/pet/settings",json={"tts_provider":"mock"}).raise_for_status()
        with http.websocket_connect("/api/devices/voice/ws?device_id=desk") as ws:
            client=VirtualESP32Voice(TestTransport(ws))
            client.send("hello",reminders=True,home_control=True)
            client.control("hello")
            reply,_=client.turn(b"\x03\x00"*8000)
            assert reply["lamp_level"]==100
            assert http.get("/api/devices/voice/status").json()["devices"][0]["home_control"]
            http.post("/api/home/play",json={"device_id":"desk","track":"morning"}).raise_for_status()
            client.send("reminder.poll")
            identity=client.control("reminder.ready")["session_id"]
            client.send("reminder.play",session_id=identity)
            start=client.control("playback.start")
            assert start["music"] is True
            size=0
            while size<start["byte_count"]:
                frame=client.socket.recv()
                size+=len(frame)-20
            client.control("playback.end")
            client.send("music.check",session_id=identity)
            assert client.control("music.check")["music_continue"]
            http.post("/api/home/stop",json={"device_id":"desk"}).raise_for_status()
            client.send("music.check",session_id=identity)
            assert not client.control("music.check")["music_continue"]
            client.send("reminder.ack",session_id=identity)
            client.control("reminder.ack")


def test_voice_alarm_call_me_at_five(home):
    assert '5点0分' in home.voice('desk', '五点叫我')
    assert '17点0分' in home.voice('desk', '明天下午五点叫醒我')
    assert '起床旋律' in home.voice('desk', '一分钟之后叫我。')
    assert home.voice('desk', '一分钟之后提醒我喝水。') is None
    assert home.voice('desk', '放一段音乐。')
    assert home.snapshot()['devices']['desk']['music']['track'] == 'morning'
    alarms = home.snapshot()['alarms']
    assert all(item['track'] == 'wakeup' and item['device_id'] == 'desk' for item in alarms)
    assert all(datetime.fromisoformat(item['due_at'].replace('Z', '+00:00')) > datetime.now(timezone.utc)
               for item in alarms)
