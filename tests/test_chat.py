"""Phase-two user journeys exercise real SQLite through the HTTP API."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app


def make_app(path, **kwargs):
    return create_app(database_path=path, settings=Settings(llm_mode="mock"), **kwargs)


@pytest.fixture
def chat_client(tmp_path):
    with TestClient(make_app(tmp_path / "chat.sqlite3")) as client:
        yield client


def chat(client, text, conversation_id=None, **extra):
    body = {"message": text, **extra}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_mock_context_and_persistence(tmp_path):
    path = tmp_path / "chat.sqlite3"
    with TestClient(make_app(path)) as client:
        result = chat(client, "我叫小林")
        cid = result["conversation_id"]
        second = chat(client, "你还记得我的名字吗？", cid)
        assert "小林" in second["reply"]
        assert second["mode"] == "mock"
        assert len(client.get(f"/api/conversations/{cid}/messages").json()) == 4
    with TestClient(make_app(path)) as client:
        messages = client.get(f"/api/conversations/{cid}/messages").json()
        assert messages[0]["content"] == "我叫小林"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["emotion"] in ["normal", "happy", "curious"]


def test_memory_cross_conversation_and_profile(chat_client):
    first = chat(chat_client, "请记住，我最近正在做一个 ESP32 AI 桌宠。")
    memories = chat_client.get("/api/memories").json()
    assert any("ESP32" in m["content"] for m in memories)
    assert memories[0]["importance"] >= .9
    assert memories[0]["source"]
    second = chat(chat_client, "你还记得我最近在做什么吗？")
    assert second["conversation_id"] != first["conversation_id"]
    assert "ESP32" in second["reply"]
    chat(chat_client, "我叫小林")
    assert chat_client.get("/api/profile").json()["display_name"] == "小林"


def test_memory_crud_dedup_and_merge(chat_client):
    body={"category":"preference","content":"我喜欢喝茉莉花茶","importance":.8}
    first=chat_client.post("/api/memories",json=body)
    assert first.status_code == 200
    mid=first.json()["id"]
    assert chat_client.post("/api/memories",json=body).json()["id"] == mid
    changed=chat_client.patch(f"/api/memories/{mid}",json={"content":"我更喜欢喝绿茶","importance":.95})
    assert changed.status_code == 200
    assert changed.json()["importance"] == .95
    assert "绿茶" in chat_client.get("/api/memories",params={"q":"绿茶"}).text
    assert chat_client.delete(f"/api/memories/{mid}").status_code == 200
    assert chat_client.get("/api/memories").json() == []


def test_sensitive_content_is_not_long_term_memory(chat_client):
    chat(chat_client, "请记住我的密码是 ABCsecret123，银行卡号是 6222021234567890123")
    assert chat_client.get("/api/memories").json() == []
    assert chat_client.post("/api/memories",json={"category":"explicit","content":"支付密码 123456"}).status_code == 422


def test_casual_chat_is_not_memory(chat_client):
    chat(chat_client, "你好，今天怎么样？")
    assert chat_client.get("/api/memories").json() == []


def test_clear_delete_and_history(chat_client):
    result=chat(chat_client, "请记住我喜欢像素画")
    cid=result["conversation_id"]
    assert len(chat_client.get("/api/conversations").json()) == 1
    assert chat_client.delete(f"/api/conversations/{cid}/messages").status_code == 200
    assert chat_client.get(f"/api/conversations/{cid}/messages").json() == []
    chat(chat_client,"你好",cid)
    assert chat_client.delete(f"/api/conversations/{cid}").status_code == 200
    assert chat_client.get(f"/api/conversations/{cid}/messages").status_code == 404
    assert len(chat_client.get("/api/memories").json()) == 1


def test_streaming_events_and_emotion(chat_client):
    response=chat_client.post("/api/chat/stream",json={"message":"好开心啊！"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events=[]
    for block in response.text.split("\n\n"):
        lines=block.splitlines()
        if len(lines)==2:
            events.append((lines[0].removeprefix("event: "),json.loads(lines[1].removeprefix("data: "))))
    assert events[0][0] == "meta"
    assert any(name=="delta" for name,_ in events)
    done=events[-1][1]
    assert events[-1][0] == "done"
    assert done["emotion"] == "happy"
    assert done["state"] == "HAPPY"
    assert ''.join(data["text"] for name,data in events if name=="delta") == done["reply"]


def test_invalid_and_missing_ids(chat_client):
    assert chat_client.post("/api/chat",json={"message":"  "}).status_code == 422
    assert chat_client.post("/api/chat",json={"message":"hi","conversation_id":"absent"}).status_code == 404
    assert chat_client.delete("/api/memories/9999").status_code == 404


def test_memory_replacement_by_stable_fact(chat_client):
    chat(chat_client,"我叫小林")
    chat(chat_client,"我叫小明")
    names=[m for m in chat_client.get("/api/memories").json() if m["memory_key"]=="name"]
    assert len(names)==1 and "小明" in names[0]["content"]


def test_status_and_frontend_do_not_expose_secret(tmp_path):
    settings=Settings(llm_mode="mock",llm_api_key="test-secret-no-leak")
    with TestClient(create_app(database_path=tmp_path/"secret.sqlite3",settings=settings)) as client:
        for path in ["/", "/api/status", "/api/conversations", "/api/memories", "/static/js/app.js"]:
            assert "test-secret-no-leak" not in client.get(path).text


def test_negative_preference_replaces_old_fact(chat_client):
    chat(chat_client,'我喜欢咖啡')
    chat(chat_client,'我不喜欢咖啡')
    rows=chat_client.get('/api/memories').json()
    assert len(rows)==1 and '不喜欢' in rows[0]['content']


@pytest.mark.parametrize('message',['不要记住我叫小林','请记住，如果我叫小林，你应该怎么回应？','假设我在北京工作','我不想让你记住我喜欢咖啡'])
def test_refusal_and_hypothetical_are_not_facts(chat_client,message):
    chat(chat_client,message)
    assert chat_client.get('/api/memories').json()==[]


def test_model_grounding_respects_polarity():
    from backend.memory.logic import grounded
    assert not grounded('我喜欢咖啡','我不喜欢咖啡')
    assert not grounded('我在北京工作','我不在北京工作')
    assert not grounded('我不喜欢咖啡','我喜欢咖啡，但不喜欢茶')
    assert grounded('我在北京工作','我在北京工作，但不喜欢咖啡')


def test_context_has_json_assistant_examples_and_is_bounded(tmp_path):
    app=make_app(tmp_path/'context.db')
    with TestClient(app) as client:
        result=chat(client,'你好')
        context=app.state.store.context(result['conversation_id'])
        assert json.loads(context[-1]['content'])['reply']==result['reply']
        assert len(context)<=20
        assert sum(len(row['content']) for row in context)<=12000


def test_memory_delete_updates_profile_and_restart_retrieval(tmp_path):
    path=tmp_path/'memory-restart.db'
    with TestClient(make_app(path)) as client:
        chat(client,'我叫小林')
    with TestClient(make_app(path)) as client:
        assert '小林' in chat(client,'你还记得我的名字吗？')['reply']
        mid=client.get('/api/memories').json()[0]['id']
        assert client.delete(f'/api/memories/{mid}').status_code==200
        assert client.get('/api/profile').json()['display_name']=='主人'
        assert '小林' not in chat(client,'你还记得我的名字吗？')['reply']


def test_model_memory_cannot_self_confirm_or_erase_confirmation(tmp_path):
    app=make_app(tmp_path/'confirmation.db')
    with TestClient(app):
        store=app.state.store
        row=store.upsert_memory('project','我在开发像素桌宠',.99,'model:session:1')
        assert row['confirmed'] is False
        row=store.upsert_memory('project','我在开发像素桌宠',.99,'manual',memory_id=row['id'],confirmed=True)
        assert row['confirmed'] is True
        row=store.upsert_memory('project','我在开发像素桌宠',.99,'model:session:2')
        assert row['confirmed'] is True and row['confidence']==1.0


def test_memory_age_decay_is_configurable():
    from datetime import datetime,timezone,timedelta
    from backend.memory.logic import rank
    recent=datetime.now(timezone.utc)
    rows=[{'id':1,'content':'项目A','category':'project','memory_key':'a','importance':1.0,'updated_at':(recent-timedelta(days=365)).isoformat()}, {'id':2,'content':'项目B','category':'project','memory_key':'b','importance':.8,'updated_at':recent.isoformat()}]
    assert rank(rows,'项目',decay_days=1)[0]['id']==2
    assert rank(rows,'项目',decay_days=0)[0]['id']==1
